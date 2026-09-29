#include "AudioIO.h"

#include <M5EchoBase.h>
#include <Wire.h>
#include <esp_heap_caps.h>
#include <math.h>
#include <string.h>

AudioIO audioIO;

static M5EchoBase echobase;

static_assert(PLAY_RING_INTERNAL % 2 == 0, "кольцевой буфер должен быть чётным: в нём 16-битные сэмплы");
static_assert(MIC_RAW_BYTES % 4 == 0, "кадр микрофона — стерео 16 бит");

// Плавные фронты сигнала (2.5 мс). Без них маленький динамик щёлкает на каждом «бип».
static constexpr uint32_t TONE_EDGE_SAMPLES = 40;

static void txEntry(void* arg) { static_cast<AudioIO*>(arg)->txLoop(); }
static void rxEntry(void* arg) { static_cast<AudioIO*>(arg)->rxLoop(); }

// ── Инициализация ───────────────────────────────────────────────────────────
bool AudioIO::begin() {
    if (!echobase.init(AUDIO_SAMPLE_RATE, PIN_I2C_SDA, PIN_I2C_SCL,
                       PIN_I2S_DI, PIN_I2S_WS, PIN_I2S_DO, PIN_I2S_BCK, Wire)) {
        return false;
    }

    echobase.setSpeakerVolume(_volume);
    // 24 дБ загоняли громкую речь в клиппинг (пики упирались в 32767),
    // а обрезанный сигнал распознаётся заметно хуже.
    echobase.setMicGain(ES8311_MIC_GAIN_18DB);
    // Усилитель держим включённым всегда: в паузах в него уходит цифровая
    // тишина, поэтому фона нет, а переключение mute щёлкало бы на каждой фразе.
    echobase.setMute(false);

    const bool psram = psramFound();
    if (psram) {
        _ringCapacity = PLAY_RING_PSRAM;
        _ring = (uint8_t*)heap_caps_malloc(_ringCapacity, MALLOC_CAP_SPIRAM);
    }
    if (!_ring) {
        _ringCapacity = PLAY_RING_INTERNAL;
        _ring = (uint8_t*)malloc(_ringCapacity);
    }

    _mono   = (int16_t*)malloc(PLAY_BLOCK_SAMPLES * sizeof(int16_t));
    _stereo = (int16_t*)malloc(PLAY_BLOCK_SAMPLES * 2 * sizeof(int16_t));

    _writeLock  = xSemaphoreCreateMutex();
    _toneQueue  = xQueueCreate(12, sizeof(ToneRequest));
    _freeQueue  = xQueueCreate(MIC_CHUNK_SLOTS, sizeof(uint8_t*));
    _readyQueue = xQueueCreate(MIC_CHUNK_SLOTS, sizeof(uint8_t*));

    bool slotsOk = _freeQueue && _readyQueue;
    for (int i = 0; i < MIC_CHUNK_SLOTS && slotsOk; i++) {
        _micSlots[i] = (uint8_t*)malloc(MIC_CHUNK_BYTES);
        if (!_micSlots[i]) { slotsOk = false; break; }
        xQueueSend(_freeQueue, &_micSlots[i], 0);
    }

    if (!_ring || !_mono || !_stereo || !_writeLock || !_toneQueue || !slotsOk) {
        return false;   // памяти не хватило — звук не поднимаем, остальное работает
    }

    memset(_mono, 0, PLAY_BLOCK_SAMPLES * sizeof(int16_t));
    _ready = true;

    xTaskCreatePinnedToCore(txEntry, "audio_tx", STACK_AUDIO, this, PRIO_AUDIO_TX, nullptr, 1);
    xTaskCreatePinnedToCore(rxEntry, "audio_rx", STACK_AUDIO, this, PRIO_AUDIO_RX, nullptr, 1);
    return true;
}

// ── Кольцевой буфер речи ────────────────────────────────────────────────────
size_t AudioIO::ringUsed() const {
    const size_t head = _ringHead;
    const size_t tail = _ringTail;
    return (head >= tail) ? (head - tail) : (_ringCapacity - tail + head);
}

size_t AudioIO::queuedBytes() const {
    return _ring ? ringUsed() : 0;
}

size_t AudioIO::enqueue(const uint8_t* pcm, size_t bytes) {
    if (!_ready || !pcm || bytes == 0) return 0;

    xSemaphoreTake(_writeLock, portMAX_DELAY);

    const size_t head = _ringHead;
    size_t accepted = _ringCapacity - ringUsed() - 1;
    if (accepted > bytes) accepted = bytes;
    accepted &= ~(size_t)1;   // сэмпл пополам не рвём

    if (accepted) {
        size_t first = _ringCapacity - head;
        if (first > accepted) first = accepted;
        memcpy(_ring + head, pcm, first);
        if (first < accepted) memcpy(_ring, pcm + first, accepted - first);
        // Индекс публикуем только после того, как данные легли в память:
        // иначе задача вывода вправе прочитать ещё не записанный кусок.
        __atomic_thread_fence(__ATOMIC_RELEASE);
        _ringHead = (head + accepted) % _ringCapacity;
    }

    xSemaphoreGive(_writeLock);

    if (accepted < bytes) _droppedPlay += bytes - accepted;
    return accepted;
}

// Читает только задача audio_tx, поэтому блокировка не нужна.
size_t AudioIO::popRing(int16_t* dst, size_t maxSamples) {
    size_t take = ringUsed() & ~(size_t)1;
    const size_t want = maxSamples * sizeof(int16_t);
    if (take > want) take = want;
    if (take == 0) return 0;

    __atomic_thread_fence(__ATOMIC_ACQUIRE);   // парная к записи в enqueue

    const size_t tail = _ringTail;
    size_t first = _ringCapacity - tail;
    if (first > take) first = take;
    memcpy(dst, _ring + tail, first);
    if (first < take) memcpy((uint8_t*)dst + first, _ring, take - first);
    __atomic_thread_fence(__ATOMIC_RELEASE);   // место освобождаем после чтения
    _ringTail = (tail + take) % _ringCapacity;
    return take / sizeof(int16_t);
}

void AudioIO::stopPlayback() {
    _flushRequest = true;         // очередь чистит сама задача вывода
    _playLevel = 0.0f;
    // Беззнаковое вычитание с переполнением здесь корректно: разность
    // millis() - _lastOutputMs всё равно окажется больше порога.
    _lastOutputMs = millis() - PLAY_TAIL_MS - 1;
    _lastSpeechMs = _lastOutputMs;
}

bool AudioIO::isPlaying() const {
    if (!_ready) return false;
    if (_flushRequest) return false;
    return ringUsed() > 0 || (millis() - _lastOutputMs) < PLAY_TAIL_MS;
}

bool AudioIO::isSpeaking() const {
    if (!_ready) return false;
    if (_flushRequest) return false;
    return ringUsed() > 0 || (millis() - _lastSpeechMs) < PLAY_TAIL_MS;
}

void AudioIO::setVolume(uint8_t percent) {
    _volume = percent > 100 ? 100 : percent;
    _volumeDirty = true;
}

// ── Сигналы ─────────────────────────────────────────────────────────────────
void AudioIO::queueTone(uint16_t freq, uint16_t ms, uint16_t amplitude) {
    if (!_toneQueue) return;
    ToneRequest req{freq, (uint16_t)((AUDIO_SAMPLE_RATE * (uint32_t)ms) / 1000), amplitude};
    xQueueSend(_toneQueue, &req, 0);
}

void AudioIO::playChime(Chime chime) {
    switch (chime) {
        case Chime::BOOT:   queueTone(880, 70, 5000);  queueTone(1175, 70, 5000); queueTone(1568, 110, 5000); break;
        case Chime::OK:     queueTone(1320, 60, 5000); queueTone(1760, 90, 5000); break;
        case Chime::ERROR:  queueTone(440, 120, 5000); queueTone(330, 160, 5000); break;
        case Chime::LISTEN: queueTone(1568, 50, 4000); break;
        case Chime::NOTIFY: queueTone(1046, 60, 5000); queueTone(1318, 60, 5000); queueTone(1568, 90, 5000); break;
        case Chime::PARTY:
            queueTone(1046, 60, 5000); queueTone(1318, 60, 5000);
            queueTone(1568, 60, 5000); queueTone(2093, 120, 5000);
            break;
        case Chime::TICK:   queueTone(1400, 40, 3500); break;
    }
}

static constexpr float TWO_PI_F = 6.28318530718f;
static constexpr float EDGE_SCALE = 1.0f / (float)TONE_EDGE_SAMPLES;

// Сигналы подмешиваются прямо в блок речи: питомца можно «пикнуть», не обрывая фразу.
void AudioIO::renderTones(int16_t* block, size_t samples) {
    for (size_t i = 0; i < samples; i++) {
        if (_toneLeft == 0) {
            ToneRequest req;
            if (xQueueReceive(_toneQueue, &req, 0) != pdTRUE) return;
            if (req.samples == 0) continue;
            _toneStep  = TWO_PI_F * (float)req.freq / (float)AUDIO_SAMPLE_RATE;
            _tonePhase = 0.0f;
            _toneLeft = _toneTotal = req.samples;
            _toneAmp = req.amplitude;
        }

        const uint32_t played = _toneTotal - _toneLeft;
        const uint32_t edge = played < _toneLeft ? played : _toneLeft;
        const float envelope = edge < TONE_EDGE_SAMPLES ? (float)edge * EDGE_SCALE : 1.0f;

        const float value = sinf(_tonePhase) * (float)_toneAmp * envelope;
        int32_t mixed = (int32_t)block[i] + (int32_t)value;
        if (mixed > 32767) mixed = 32767;
        if (mixed < -32768) mixed = -32768;
        block[i] = (int16_t)mixed;

        _tonePhase += _toneStep;
        if (_tonePhase > TWO_PI_F) _tonePhase -= TWO_PI_F;
        _toneLeft--;
    }
}

// ── Задача вывода ───────────────────────────────────────────────────────────
void AudioIO::txLoop() {
    const size_t block = PLAY_BLOCK_SAMPLES;

    while (true) {
        if (_flushRequest) {
            _flushRequest = false;
            _ringTail = _ringHead;
        }
        if (_volumeDirty) {
            _volumeDirty = false;
            echobase.setSpeakerVolume(_volume);
        }

        const size_t got = popRing(_mono, block);

        // Речь кончилась посреди блока — доводим сигнал до нуля линейно.
        // Резкий обрыв (например, по кнопке «перебить») иначе даёт щелчок.
        if (got < block) {
            const int16_t from = got ? _mono[got - 1] : _lastSample;
            const size_t fade = block - got;
            for (size_t i = 0; i < fade; i++) {
                _mono[got + i] = (int16_t)(from * (1.0f - (float)(i + 1) / (float)fade));
            }
        }
        _lastSample = _mono[block - 1];

        renderTones(_mono, block);

        uint32_t sum = 0;
        for (size_t i = 0; i < block; i++) {
            const int16_t sample = _mono[i];
            _stereo[i * 2]     = sample;
            _stereo[i * 2 + 1] = sample;
            sum += (uint32_t)abs(sample);
        }

        const float level = (float)(sum / block) / 8000.0f;
        _playLevel = fminf(1.0f, level * 0.6f + _playLevel * 0.4f);
        // Цифровая тишина за «речь» не считается, иначе микрофон не включится.
        if (sum > block * 40) {
            const uint32_t stamp = millis();
            _lastOutputMs = stamp;
            if (got > 0) _lastSpeechMs = stamp;   // сигнал речью не считаем
        }

        // clear_dma_buffer=false — принципиально. С true драйвер обнулял ещё не
        // проигранные DMA-буферы после каждых 16 мс, и речь рассыпалась.
        echobase.play((const uint8_t*)_stereo, block * 2 * sizeof(int16_t), false);
    }
}

// ── Задача записи ───────────────────────────────────────────────────────────
void AudioIO::rxLoop() {
    static uint8_t raw[MIC_RAW_BYTES];
    static int16_t mono[MIC_RAW_BYTES / 4];
    constexpr int FRAMES = MIC_RAW_BYTES / 4;
    constexpr size_t MONO_BYTES = FRAMES * sizeof(int16_t);

    while (true) {
        // Читаем всегда, даже пока говорим. Если этого не делать, приёмный DMA
        // переполняется и первые кадры после ответа содержат собственный голос.
        if (!echobase.record(raw, sizeof(raw))) {
            vTaskDelay(pdMS_TO_TICKS(5));
            continue;
        }

        const int16_t* src = (const int16_t*)raw;
        uint64_t energy = 0;
        for (int i = 0; i < FRAMES; i++) {
            const int32_t m = ((int32_t)src[i * 2] + src[i * 2 + 1]) / 2;
            mono[i] = (int16_t)m;
            energy += (uint64_t)(m * m);
        }

        const uint32_t now = millis();
        const bool wantAudio = _recording && !_micMuted &&
                               ringUsed() == 0 &&
                               (now - _lastOutputMs) > MIC_RESUME_DELAY_MS;

        const float rms = sqrtf((float)(energy / FRAMES));
        _micLevel = wantAudio ? fminf(1.0f, rms / 6000.0f) * 0.4f + _micLevel * 0.6f
                              : _micLevel * 0.8f;

        if (!wantAudio) {
            _fillUsed = 0;   // недособранный кадр выбрасываем целиком
            continue;
        }

        size_t offset = 0;
        while (offset < MONO_BYTES) {
            if (!_fillSlot) {
                if (xQueueReceive(_freeQueue, &_fillSlot, 0) != pdTRUE) {
                    // Свободных слотов нет — жертвуем самым старым кадром:
                    // для распознавания задержка вреднее, чем пропуск 32 мс.
                    if (xQueueReceive(_readyQueue, &_fillSlot, 0) != pdTRUE) break;
                    _droppedMic++;
                }
                _fillUsed = 0;
            }

            const size_t room = MIC_CHUNK_BYTES - _fillUsed;
            const size_t left = MONO_BYTES - offset;
            const size_t take = left < room ? left : room;
            memcpy(_fillSlot + _fillUsed, (const uint8_t*)mono + offset, take);
            _fillUsed += take;
            offset += take;

            if (_fillUsed >= MIC_CHUNK_BYTES) {
                xQueueSend(_readyQueue, &_fillSlot, 0);
                _fillSlot = nullptr;
                _fillUsed = 0;
            }
        }
    }
}

void AudioIO::setMicMuted(bool muted) {
    _micMuted = muted;
    if (muted) _micLevel = 0.0f;
}

const uint8_t* AudioIO::takeChunk(size_t& bytes) {
    if (_inFlight || !_readyQueue) return nullptr;
    uint8_t* slot = nullptr;
    if (xQueueReceive(_readyQueue, &slot, 0) != pdTRUE) return nullptr;
    _inFlight = slot;
    bytes = MIC_CHUNK_BYTES;
    return slot;
}

void AudioIO::releaseChunk() {
    if (!_inFlight) return;
    xQueueSend(_freeQueue, &_inFlight, 0);
    _inFlight = nullptr;
}
