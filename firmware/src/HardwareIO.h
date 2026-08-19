#pragma once
#include <M5Unified.h>

class HardwareIO {
public:
    HardwareIO();

    void init();
    void update(); // Called from Core 1

    // IMU Data
    float getPitch() const { return pitch; }
    float getRoll() const { return roll; }
    int getOrientation() const { return orientation; }
    bool isShaking() const { return shaking; }
    int getShakeCount() const { return shakeCount; }

    // Audio
    void playTone(int freq, int duration);
    void playAudioStream(const uint8_t* payload, size_t length);
    void stopAudioPlayback();
    
    // Mic recording
    bool isRecording() const { return recording; }
    void startRecording();
    void stopRecording();
    uint8_t* getRecordBuffer() { return recordBuffer; }
    size_t getRecordSize() const { return recordIndex; }
    void resetRecordBuffer() { recordIndex = 0; }
    bool hasAudioChunk() const { return recordIndex >= RECORD_BUFFER_SIZE; }

private:
    float pitch, roll, yaw;
    float ax, ay, az;
    int orientation; // 0, 1, 2, 3
    bool shaking;
    int shakeCount;
    unsigned long lastShakeTime;
    unsigned long lastShakeDetectTime;

    // Mic 
    static constexpr size_t RECORD_BUFFER_SIZE = 4096; // 4KB chunks for streaming
    uint8_t* recordBuffer;
    size_t recordIndex;
    bool recording;
    
    void updateIMU();
    void checkButtons();
};

extern HardwareIO hardwareIO;
