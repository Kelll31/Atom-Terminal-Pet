#include "HardwareIO.h"
#include "PetState.h"
#include <M5EchoBase.h>
#include <Wire.h>
#include <esp_heap_caps.h>
#include <math.h>

M5EchoBase echobase;
HardwareIO hardwareIO;

// Размер кольцевого буфера воспроизведения: ~2 секунды звука 16 кГц/16 бит.
// В PSRAM берём с запасом, без PSRAM — скромнее, чтобы не съесть кучу.
static constexpr size_t PLAY_BUFFER_PSRAM    = 128 * 1024;
static constexpr size_t PLAY_BUFFER_INTERNAL = 32 * 1024;
// Сколько моно-сэмплов отдаём в I2S за один заход (256 сэмплов = 16 мс)
static constexpr size_t PLAY_BLOCK_SAMPLES = 256;

HardwareIO::HardwareIO()
    : pitch(0), roll(0), yaw(0), ax(0), ay(0), az(0),
      orientation(0), shaking(false), tapped(false), faceDown(false), moving(false),
      shakeCount(0), lastShakeTime(0), lastShakeDetectTime(0), lastMotionTime(0),
      lastMagnitude(1.0f),
      recordBuffer(nullptr), recordIndex(0), recording(false), micMuted(false), micLevel(0.0f),
      playBuffer(nullptr), playCapacity(0), playHead(0), playTail(0),
      playMux(portMUX_INITIALIZER_UNLOCKED), audioTask(nullptr),
      audioReady(false), playbackLevel(0.0f), lastPlayTime(0), psramAvailable(false) {}

// ── Задача воспроизведения ──────────────────────────────────────────────────
static void audioTaskEntry(void* arg) {
    static_cast<HardwareIO*>(arg)->audioTaskLoop();
}

void HardwareIO::audioTaskLoop() {
    const size_t blockBytes = PLAY_BLOCK_SAMPLES * 2;          // моно 16 бит
    uint8_t* mono   = (uint8_t*)malloc(blockBytes);
    uint8_t* stereo = (uint8_t*)malloc(blockBytes * 2);
    if (!mono || !stereo) {
        vTaskDelete(nullptr);
        return;
    }

    while (true) {
        size_t available = getQueuedAudio();
        if (available < blockBytes) {
            // Буфер пуст — отдаём процессор, уровень звука плавно гасим
            playbackLevel = playbackLevel * 0.7f;
            vTaskDelay(pdMS_TO_TICKS(5));
            continue;
        }

        // Кольцевой буфер с одним писателем и одним читателем — блокировки не нужны,
        // достаточно менять индекс после копирования.
        size_t tail = playTail;
        size_t firstPart = playCapacity - tail;
        if (firstPart > blockBytes) firstPart = blockBytes;
        memcpy(mono, playBuffer + tail, firstPart);
        if (firstPart < blockBytes) {
            memcpy(mono + firstPart, playBuffer, blockBytes - firstPart);
        }
        playTail = (tail + blockBytes) % playCapacity;

        // Моно -> стерео + оценка громкости для анимации рта
        const int16_t* src = (const int16_t*)mono;
        int16_t* dst = (int16_t*)stereo;
        uint32_t sum = 0;
        for (size_t i = 0; i < PLAY_BLOCK_SAMPLES; i++) {
            int16_t sample = src[i];
            dst[i * 2]     = sample;
            dst[i * 2 + 1] = sample;
            sum += abs(sample);
        }
        float level = (float)(sum / PLAY_BLOCK_SAMPLES) / 8000.0f;
        playbackLevel = fminf(1.0f, level * 0.6f + playbackLevel * 0.4f);
        lastPlayTime = millis();

        echobase.play(stereo, blockBytes * 2, true);
    }
}

// ── Инициализация ───────────────────────────────────────────────────────────
void HardwareIO::init() {
    // ES8311 + I2S на пинах базы Atomic Echo Base (одинаковы для AtomS3 и AtomS3R)
    audioReady = echobase.init(16000, 38, 39, 7, 6, 5, 8, Wire);
    if (audioReady) {
        echobase.setSpeakerVolume(80);
        echobase.setMicGain(ES8311_MIC_GAIN_24DB);
        echobase.setMute(false);
    }

    recordBuffer = (uint8_t*)malloc(RECORD_BUFFER_SIZE);

    psramAvailable = psramFound();
    playCapacity = psramAvailable ? PLAY_BUFFER_PSRAM : PLAY_BUFFER_INTERNAL;
    playBuffer = psramAvailable
        ? (uint8_t*)heap_caps_malloc(playCapacity, MALLOC_CAP_SPIRAM)
        : (uint8_t*)malloc(playCapacity);
    if (!playBuffer) {
        playCapacity = PLAY_BUFFER_INTERNAL;
        playBuffer = (uint8_t*)malloc(playCapacity);
    }

    M5.Imu.init();
    M5.BtnA.setHoldThresh(700);

    if (audioReady && playBuffer) {
        xTaskCreatePinnedToCore(audioTaskEntry, "audioTask", 4096, this, 5, &audioTask, 1);
    }
}

// ── Динамик ─────────────────────────────────────────────────────────────────
size_t HardwareIO::getQueuedAudio() const {
    size_t head = playHead;
    size_t tail = playTail;
    return (head >= tail) ? (head - tail) : (playCapacity - tail + head);
}

size_t HardwareIO::enqueueAudio(const uint8_t* pcm, size_t length) {
    if (!playBuffer || !pcm || length == 0) return 0;

    size_t free_space = playCapacity - getQueuedAudio() - 1;
    size_t accepted = length > free_space ? free_space : length;
    if (accepted == 0) return 0;

    size_t head = playHead;
    size_t firstPart = playCapacity - head;
    if (firstPart > accepted) firstPart = accepted;
    memcpy(playBuffer + head, pcm, firstPart);
    if (firstPart < accepted) {
        memcpy(playBuffer, pcm + firstPart, accepted - firstPart);
    }
    playHead = (head + accepted) % playCapacity;

    lastPlayTime = millis();
    return accepted;
}

void HardwareIO::stopAudioPlayback() {
    portENTER_CRITICAL(&playMux);
    playTail = playHead;
    portEXIT_CRITICAL(&playMux);
    playbackLevel = 0.0f;

    // Дозаполняем I2S тишиной, иначе DMA повторяет последний кусок
    static uint8_t silence[1024] = {0};
    if (audioReady) echobase.play(silence, sizeof(silence), true);
}

bool HardwareIO::isPlaying() const {
    return getQueuedAudio() > 0 || (millis() - lastPlayTime < 250);
}

void HardwareIO::playTone(int freq, int durationMs, int volume) {
    if (!audioReady || freq <= 0 || durationMs <= 0) return;

    int samples = (16000 * durationMs) / 1000;
    size_t bytes = samples * 4;  // стерео 16 бит
    uint8_t* buf = (uint8_t*)malloc(bytes);
    if (!buf) return;

    int16_t* p = (int16_t*)buf;
    float step = 2.0f * PI * freq / 16000.0f;
    for (int i = 0; i < samples; i++) {
        // Синус мягче меандра и не режет слух на маленьком динамике
        float envelope = 1.0f;
        if (i < 160) envelope = i / 160.0f;
        if (i > samples - 160) envelope = (samples - i) / 160.0f;
        int16_t value = (int16_t)(sinf(step * i) * volume * envelope);
        p[i * 2] = value;
        p[i * 2 + 1] = value;
    }
    echobase.play(buf, bytes, true);
    free(buf);
    lastPlayTime = millis();
}

void HardwareIO::playChime(Chime chime) {
    switch (chime) {
        case Chime::BOOT:   playTone(880, 70); playTone(1175, 70); playTone(1568, 110); break;
        case Chime::OK:     playTone(1320, 60); playTone(1760, 90); break;
        case Chime::ERROR:  playTone(440, 120); playTone(330, 160); break;
        case Chime::LISTEN: playTone(1568, 50); break;
        case Chime::NOTIFY: playTone(1046, 60); playTone(1318, 60); playTone(1568, 90); break;
        case Chime::PARTY:
            playTone(1046, 60); playTone(1318, 60); playTone(1568, 60); playTone(2093, 120);
            break;
    }
}

// ── Микрофон ────────────────────────────────────────────────────────────────
void HardwareIO::startRecording() {
    if (!recording) {
        recording = true;
        recordIndex = 0;
    }
}

void HardwareIO::stopRecording() {
    recording = false;
    recordIndex = 0;
}

void HardwareIO::setMicMuted(bool muted) {
    micMuted = muted;
    if (muted) recordIndex = 0;
}

// ── Основной цикл ───────────────────────────────────────────────────────────
void HardwareIO::update() {
    M5.update();
    updateIMU();

    // Пока говорим — микрофон не пишем, иначе слышим сами себя
    if (recording && !micMuted && !isPlaying()) {
        uint8_t rawBuf[1024];  // 256 стереокадров
        if (echobase.record(rawBuf, sizeof(rawBuf))) {
            const int16_t* src = (const int16_t*)rawBuf;
            int16_t* dst = (int16_t*)&recordBuffer[recordIndex];
            const int frames = sizeof(rawBuf) / 4;
            uint32_t sum = 0;

            for (int i = 0; i < frames; i++) {
                int16_t mixed = (int16_t)(((int32_t)src[i * 2] + src[i * 2 + 1]) / 2);
                dst[i] = mixed;
                sum += abs(mixed);
            }
            micLevel = fminf(1.0f, ((float)(sum / frames) / 6000.0f) * 0.5f + micLevel * 0.5f);

            size_t monoBytes = frames * 2;
            if (recordIndex + monoBytes <= RECORD_BUFFER_SIZE) {
                recordIndex += monoBytes;
            }
        }
    } else if (micLevel > 0.01f) {
        micLevel *= 0.8f;
    }
}

ButtonEvent HardwareIO::pollButton() {
    if (M5.BtnA.pressedFor(3000))     return ButtonEvent::LONG_HOLD;
    if (M5.BtnA.wasHold())            return ButtonEvent::HOLD;
    if (M5.BtnA.wasDoubleClicked())   return ButtonEvent::DOUBLE_CLICK;
    if (M5.BtnA.wasSingleClicked())   return ButtonEvent::CLICK;
    return ButtonEvent::NONE;
}

// ── IMU ─────────────────────────────────────────────────────────────────────
void HardwareIO::updateIMU() {
    if (!M5.Imu.update()) return;

    M5.Imu.getAccel(&ax, &ay, &az);

    pitch = atan2f(-ax, sqrtf(ay * ay + az * az)) * 180.0f / PI;
    roll  = atan2f(ay, az) * 180.0f / PI;

    unsigned long now = millis();
    float magnitude = sqrtf(ax * ax + ay * ay + az * az);
    float delta = fabsf(magnitude - lastMagnitude);
    lastMagnitude = magnitude;

    moving = delta > 0.06f;
    if (moving) lastMotionTime = now;

    faceDown = (az < -0.75f);

    // Автоповорот экрана по вектору силы тяжести
    int newOrient = orientation;
    if (ay > 0.65f)       newOrient = 0;
    else if (ay < -0.65f) newOrient = 2;
    else if (ax > 0.65f)  newOrient = 1;
    else if (ax < -0.65f) newOrient = 3;

    if (newOrient != orientation) {
        orientation = newOrient;
        M5.Display.setRotation(orientation);
    }

    // Постукивание по корпусу — короткий резкий всплеск
    if (delta > 0.55f && delta < 1.4f && now - lastShakeDetectTime > 250) {
        tapped = true;
    }

    // Тряска — сильные всплески подряд
    if (magnitude > 2.0f && now - lastShakeDetectTime > 320) {
        shakeCount++;
        lastShakeDetectTime = now;
        lastShakeTime = now;
        shaking = true;
    }

    if (shaking && now - lastShakeTime > 2500) {
        shaking = false;
        shakeCount = 0;
    }
}
