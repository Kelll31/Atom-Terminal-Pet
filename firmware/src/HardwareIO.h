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
    bool isShaking() const { return shaking; }

    // Audio
    void playTone(int freq, int duration);
    void playAudioStream(const uint8_t* payload, size_t length);
    
    // Mic recording
    bool isRecording() const { return recording; }
    void startRecording();
    void stopRecording();
    uint8_t* getRecordBuffer() { return recordBuffer; }
    size_t getRecordSize() const { return recordIndex; }
    void resetRecordBuffer() { recordIndex = 0; }

private:
    float pitch, roll, yaw;
    bool shaking;
    unsigned long lastShakeTime;

    // Mic 
    static constexpr size_t RECORD_BUFFER_SIZE = 16000 * 2 * 3; // 3 sec, 16kHz, 16-bit
    uint8_t* recordBuffer;
    size_t recordIndex;
    bool recording;
    
    void updateIMU();
    void checkButtons();
};

extern HardwareIO hardwareIO;
