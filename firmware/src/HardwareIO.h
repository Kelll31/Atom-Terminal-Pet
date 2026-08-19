#pragma once
#include <M5Unified.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

// Событие кнопки под экраном
enum class ButtonEvent {
    NONE,
    CLICK,        // короткое нажатие — погладить
    DOUBLE_CLICK, // сменить экран
    HOLD,         // удержание — вкл/выкл микрофон
    LONG_HOLD     // долгое удержание — экран настроек/перезагрузка
};

enum class Chime {
    BOOT,
    OK,
    ERROR,
    LISTEN,
    NOTIFY,
    PARTY
};

/**
 * Всё железо в одном месте: кодек ES8311 (микрофон + динамик), IMU, кнопка.
 *
 * Воспроизведение построено на кольцевом буфере и отдельной задаче FreeRTOS:
 * приём данных (USB/Wi-Fi) больше не ждёт, пока I2S проиграет очередной кусок.
 * Раньше блокирующая запись в I2S прямо из основного цикла приводила к
 * переполнению приёмного буфера USB — звук рассыпался на отдельные «пики».
 */
class HardwareIO {
public:
    HardwareIO();

    void init();
    void update();  // вызывать из основного цикла

    // ── IMU ────────────────────────────────────────────────────────────────
    float getPitch() const { return pitch; }
    float getRoll() const { return roll; }
    int   getOrientation() const { return orientation; }
    bool  isShaking() const { return shaking; }
    int   getShakeCount() const { return shakeCount; }
    void  clearShake() { shaking = false; shakeCount = 0; }
    bool  wasTapped() const { return tapped; }
    void  clearTap() { tapped = false; }
    bool  isFaceDown() const { return faceDown; }
    bool  isMoving() const { return moving; }
    unsigned long getLastMotionTime() const { return lastMotionTime; }

    // ── Кнопка ─────────────────────────────────────────────────────────────
    ButtonEvent pollButton();

    // ── Динамик ────────────────────────────────────────────────────────────
    void playTone(int freq, int durationMs, int volume = 5000);
    void playChime(Chime chime);
    // Кладёт PCM 16 кГц/16 бит/моно в кольцевой буфер. Возвращает принятые байты.
    size_t enqueueAudio(const uint8_t* pcm, size_t length);
    void   stopAudioPlayback();
    bool   isPlaying() const;
    float  getPlaybackLevel() const { return playbackLevel; }  // 0..1 — для анимации рта
    unsigned long getLastPlayTime() const { return lastPlayTime; }
    size_t getQueuedAudio() const;

    // ── Микрофон ───────────────────────────────────────────────────────────
    bool isRecording() const { return recording && !micMuted; }
    void startRecording();
    void stopRecording();
    void setMicMuted(bool muted);
    bool isMicMuted() const { return micMuted; }
    float getMicLevel() const { return micLevel; }  // 0..1
    uint8_t* getRecordBuffer() { return recordBuffer; }
    size_t getRecordSize() const { return recordIndex; }
    void resetRecordBuffer() { recordIndex = 0; }
    bool hasAudioChunk() const { return recordIndex >= RECORD_BUFFER_SIZE; }

    // ── Состояние железа ───────────────────────────────────────────────────
    bool isAudioReady() const { return audioReady; }
    bool hasPsram() const { return psramAvailable; }

    // Задача воспроизведения (вызывается из статической обёртки)
    void audioTaskLoop();

private:
    // IMU
    float pitch, roll, yaw;
    float ax, ay, az;
    int orientation;
    bool shaking;
    bool tapped;
    bool faceDown;
    bool moving;
    int  shakeCount;
    unsigned long lastShakeTime;
    unsigned long lastShakeDetectTime;
    unsigned long lastMotionTime;
    float lastMagnitude;

    // Микрофон
    static constexpr size_t RECORD_BUFFER_SIZE = 4096;
    uint8_t* recordBuffer;
    size_t   recordIndex;
    bool     recording;
    bool     micMuted;
    float    micLevel;

    // Воспроизведение (кольцевой буфер)
    uint8_t* playBuffer;
    size_t   playCapacity;
    volatile size_t playHead;   // куда пишем
    volatile size_t playTail;   // откуда читаем
    portMUX_TYPE playMux;
    TaskHandle_t audioTask;
    volatile bool audioReady;
    volatile float playbackLevel;
    volatile unsigned long lastPlayTime;
    bool psramAvailable;

    void updateIMU();
};

extern HardwareIO hardwareIO;
