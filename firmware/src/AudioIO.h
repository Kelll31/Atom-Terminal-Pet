#pragma once
#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>
#include "Config.h"

enum class Chime : uint8_t {
    BOOT,
    OK,
    ERROR,
    LISTEN,
    NOTIFY,
    PARTY,
    TICK
};

/**
 * Звук питомца: микрофон и динамик Atomic Echo Base (кодек ES8311).
 *
 * Главное правило класса — **к I2S прикасаются только две его задачи**:
 *   • audio_tx постоянно пишет в динамик (речь из кольцевого буфера, а когда
 *     речи нет — цифровую тишину). Никто больше i2s_write не вызывает;
 *   • audio_rx постоянно читает микрофон, даже во время речи, — иначе приёмный
 *     DMA переполняется и после ответа питомец «слышит» собственный хвост.
 *
 * Что это чинит по сравнению с прошлой версией:
 *   1. Пропала гонка за I2S. Раньше сигналы (playChime) и остановка речи писали
 *      в тот же порт из основного цикла, пока туда же писала задача звука, —
 *      блоки перемешивались. Теперь сигналы подмешиваются внутри audio_tx.
 *   2. Пропал i2s_zero_dma_buffer после каждого 16-мс блока: он обнулял ещё не
 *      проигранные данные, и речь звучала рвано.
 *   3. Пропало переполнение буфера записи: раньше кадр писался в память до
 *      проверки границ и при заполненном буфере затирал 512 байт кучи.
 *   4. Обрыв речи больше не щёлкает — последний блок гасится линейно.
 */
class AudioIO {
public:
    bool begin();

    // ── Динамик ────────────────────────────────────────────────────────────
    // PCM 16 кГц / 16 бит / моно. Не блокирует; возвращает принятые байты
    // (меньше запрошенного — значит буфер полон и остаток отброшен).
    size_t enqueue(const uint8_t* pcm, size_t bytes);
    void   stopPlayback();          // мгновенно оборвать речь без щелчка
    // isPlaying — в динамик вообще что-то идёт (речь или сигнал): по нему
    // закрывается микрофон. isSpeaking — идёт именно речь: по нему питомец
    // открывает рот и понимает, что его перебивают. Разделены, потому что
    // короткий «бип» на нажатие кнопки не должен переводить его в режим ответа.
    bool   isPlaying() const;
    bool   isSpeaking() const;
    size_t queuedBytes() const;
    float  playbackLevel() const { return _playLevel; }   // 0..1 — анимация рта
    uint32_t lastOutputMs() const { return _lastOutputMs; }
    void   setVolume(uint8_t percent);                    // 0..100
    uint8_t getVolume() const { return _volume; }
    void   playChime(Chime chime);                        // не блокирует

    // ── Микрофон ───────────────────────────────────────────────────────────
    void  startRecording() { _recording = true; }
    void  stopRecording()  { _recording = false; }
    bool  isRecording() const { return _recording && !_micMuted; }
    void  setMicMuted(bool muted);
    bool  isMicMuted() const { return _micMuted; }
    float micLevel() const { return _micLevel; }          // 0..1

    // Готовый кадр микрофона (MIC_CHUNK_BYTES). nullptr — пока нечего слать.
    // После отправки обязательно вернуть слот через releaseChunk().
    const uint8_t* takeChunk(size_t& bytes);
    void releaseChunk();

    // ── Диагностика ────────────────────────────────────────────────────────
    bool     isReady() const { return _ready; }
    uint32_t droppedPlayBytes() const { return _droppedPlay; }
    uint32_t droppedMicChunks() const { return _droppedMic; }

    // Точки входа задач (публичные только ради статических обёрток).
    void txLoop();
    void rxLoop();

private:
    // ── Воспроизведение ────────────────────────────────────────────────────
    uint8_t* _ring = nullptr;
    size_t   _ringCapacity = 0;
    volatile size_t _ringHead = 0;      // пишет отправитель
    volatile size_t _ringTail = 0;      // читает задача audio_tx
    SemaphoreHandle_t _writeLock = nullptr;   // отправителей может быть двое: Wi-Fi и USB
    volatile bool _flushRequest = false;      // «оборвать речь» — выполняет audio_tx

    int16_t* _mono = nullptr;           // рабочие буферы задачи audio_tx
    int16_t* _stereo = nullptr;
    int16_t  _lastSample = 0;           // для затухания при обрыве

    volatile float    _playLevel = 0.0f;
    volatile uint32_t _lastOutputMs = 0;   // когда в динамик ушёл ненулевой блок
    volatile uint32_t _lastSpeechMs = 0;   // ...и когда этот блок был именно речью
    volatile uint32_t _droppedPlay = 0;

    // ── Сигналы (подмешиваются в поток речи) ───────────────────────────────
    struct ToneRequest {
        uint16_t freq;
        uint16_t samples;
        uint16_t amplitude;
    };
    QueueHandle_t _toneQueue = nullptr;
    float    _tonePhase = 0.0f;
    float    _toneStep = 0.0f;
    uint32_t _toneLeft = 0;
    uint32_t _toneTotal = 0;
    uint16_t _toneAmp = 0;

    // ── Микрофон ───────────────────────────────────────────────────────────
    uint8_t* _micSlots[MIC_CHUNK_SLOTS] = {nullptr};
    QueueHandle_t _freeQueue = nullptr;
    QueueHandle_t _readyQueue = nullptr;
    uint8_t* _fillSlot = nullptr;
    size_t   _fillUsed = 0;
    uint8_t* _inFlight = nullptr;

    volatile bool  _recording = false;
    volatile bool  _micMuted = false;
    volatile float _micLevel = 0.0f;
    volatile uint32_t _droppedMic = 0;

    // ── Общее ──────────────────────────────────────────────────────────────
    volatile bool _ready = false;
    volatile uint8_t _volume = 80;
    volatile bool _volumeDirty = false;

    size_t ringUsed() const;
    size_t popRing(int16_t* dst, size_t maxSamples);
    void   renderTones(int16_t* block, size_t samples);
    void   queueTone(uint16_t freq, uint16_t ms, uint16_t amplitude);
};

extern AudioIO audioIO;
