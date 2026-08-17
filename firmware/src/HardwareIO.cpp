#include "HardwareIO.h"
#include "PetState.h"

HardwareIO hardwareIO;

HardwareIO::HardwareIO() {
    pitch = 0; roll = 0; yaw = 0;
    shaking = false;
    lastShakeTime = 0;
    
    recordBuffer = nullptr;
    recordIndex = 0;
    recording = false;
}

void HardwareIO::init() {
    auto spk_cfg = M5.Speaker.config();
    spk_cfg.sample_rate = 16000;
    M5.Speaker.config(spk_cfg);
    M5.Speaker.begin();

    auto mic_cfg = M5.Mic.config();
    mic_cfg.sample_rate = 16000;
    M5.Mic.config(mic_cfg);
    M5.Mic.begin();

    recordBuffer = (uint8_t*)malloc(RECORD_BUFFER_SIZE);
    M5.Imu.init();
}

void HardwareIO::playTone(int freq, int duration) {
    M5.Speaker.tone(freq, duration);
}

void HardwareIO::playAudioStream(const uint8_t* payload, size_t length) {
    M5.Speaker.playRaw((const int16_t*)payload, length / 2, 16000, true);
}

void HardwareIO::startRecording() {
    if (!recording) {
        recording = true;
        recordIndex = 0;
        petState.setEmotion(PetEmotion::LISTENING, "Listening...");
    }
}

void HardwareIO::stopRecording() {
    if (recording) {
        recording = false;
        petState.setEmotion(PetEmotion::THINKING, "Thinking...");
    }
}

void HardwareIO::update() {
    M5.update(); // Update M5 components (buttons)
    
    updateIMU();
    checkButtons();
    
    // Handle mic recording continuously if active
    if (recording) {
        if (M5.Mic.record(&recordBuffer[recordIndex], 1024, 16000)) {
            recordIndex += 1024;
            if (recordIndex >= RECORD_BUFFER_SIZE - 1024) {
                stopRecording(); // Buffer full
            }
        }
    }
}

void HardwareIO::updateIMU() {
    float ax, ay, az;
    if (M5.Imu.update()) {
        M5.Imu.getAccel(&ax, &ay, &az);
        
        // Simple tilt calculation (pitch and roll)
        pitch = atan2(-ax, sqrt(ay * ay + az * az)) * 180.0 / PI;
        roll = atan2(ay, az) * 180.0 / PI;

        // Shake detection (magnitude of acceleration)
        float magnitude = sqrt(ax*ax + ay*ay + az*az);
        if (magnitude > 2.0) { // arbitrary threshold for shaking > 2G
            if (!shaking && (millis() - lastShakeTime > 2000)) {
                shaking = true;
                petState.setEmotion(PetEmotion::DIZZY, "Dizzy!");
                lastShakeTime = millis();
            }
        }
    }
    
    // Clear shake state after a while
    if (shaking && (millis() - lastShakeTime > 3000)) {
        shaking = false;
    }
}

void HardwareIO::checkButtons() {
    // Single click (short)
    if (M5.BtnA.wasClicked()) {
        petState.addAttention(20);
        petState.setEmotion(PetEmotion::LOVE, "Pat pat!");
        playTone(1500, 100);
    }
    
    // Long press
    if (M5.BtnA.wasPressed()) {
        // Will be held. Wait to see if it becomes a long press, but for now we start recording immediately
        // In a real implementation we might wait 500ms before starting.
        // For simplicity, handled in main loop or here.
        startRecording();
    }
    
    if (M5.BtnA.wasReleased()) {
        if (recording) {
            stopRecording();
            // Flag to main loop to send data is needed, or handled via getters
        }
    }
}
