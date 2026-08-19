#include "HardwareIO.h"
#include "PetState.h"
#include <M5EchoBase.h>

extern HardwareIO hardwareIO;
M5EchoBase echobase;

HardwareIO hardwareIO;

HardwareIO::HardwareIO() {
    pitch = 0; roll = 0; yaw = 0;
    ax = 0; ay = 0; az = 0;
    orientation = 0;
    shaking = false;
    shakeCount = 0;
    lastShakeTime = 0;
    lastShakeDetectTime = 0;
    
    recordBuffer = nullptr;
    recordIndex = 0;
    recording = false;
    playing = false;
    lastPlayCallTime = 0;
}

#include <Wire.h>

void HardwareIO::init() {
    // Initialize ES8311 Codec over I2C and I2S using official library
    // For AtomS3 + Atomic Echo Base
    // sample_rate=16000, i2c_sda=38, i2c_scl=39, i2s_di=7, i2s_ws=6, i2s_do=5, i2s_bck=8
    if (!echobase.init(16000, 38, 39, 7, 6, 5, 8, Wire)) {
        Serial.println("Failed to initialize EchoBase!");
    }
    
    // Configure ES8311 volumes (75% to prevent NS4150B amp clipping/distortion)
    echobase.setSpeakerVolume(75); 
    echobase.setMicGain(ES8311_MIC_GAIN_18DB); // Give the mic some good gain
    echobase.setMute(false);

    recordBuffer = (uint8_t*)malloc(RECORD_BUFFER_SIZE);
    M5.Imu.init();
}

void HardwareIO::playTone(int freq, int duration) {
    if (freq <= 0 || duration <= 0) return;
    int samples = (16000 * duration) / 1000;
    size_t bytes = samples * 4; // 16-bit Stereo
    uint8_t* toneBuf = (uint8_t*)malloc(bytes);
    if (!toneBuf) return;
    int halfPeriod = 16000 / freq / 2;
    if (halfPeriod == 0) halfPeriod = 1;
    int16_t* p = (int16_t*)toneBuf;
    for (int i=0; i<samples; i++) {
        int16_t val = ((i / halfPeriod) % 2 == 0) ? 6000 : -6000;
        p[i * 2]     = val; // Left
        p[i * 2 + 1] = val; // Right
    }
    // Use blocking=true so all bytes are guaranteed written to I2S DMA.
    // Non-blocking mode silently drops audio when DMA buffer is busy (causes chipmunk/no audio).
    echobase.play(toneBuf, bytes, true);
    free(toneBuf);
}

void HardwareIO::playAudioStream(const uint8_t* payload, size_t length) {
    if (!payload || length == 0) return;

    size_t monoSamples = length / 2;
    size_t stereoBytes = monoSamples * 4; // 16-bit Stereo
    
    uint8_t* stereoBuf = (uint8_t*)malloc(stereoBytes);
    if (!stereoBuf) return;
    
    const int16_t* src = (const int16_t*)payload;
    int16_t* dst = (int16_t*)stereoBuf;
    for (size_t i = 0; i < monoSamples; i++) {
        dst[i * 2]     = src[i]; // Left
        dst[i * 2 + 1] = src[i]; // Right
    }
    lastPlayCallTime = millis(); // Track for echo prevention in loop()
    playing = true;
    // blocking=true: waits until all bytes fit in I2S DMA. Ensures no audio is dropped.
    // Each 4096-byte mono chunk = 128ms at 16kHz. Blocking time per call ~18ms (DMA overlap drain).
    echobase.play(stereoBuf, stereoBytes, true);
    playing = false;
    free(stereoBuf);
}

void HardwareIO::stopAudioPlayback() {
    // 8192 bytes of silence ensures the 32-bit stereo DMA buffer is fully flushed
    static const uint8_t silence[8192] = {0};
    echobase.play(silence, sizeof(silence), true);
    playing = false; // Reset playback state
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
    if (recording && petState.getEmotion() != PetEmotion::TALKING) {
        uint8_t rawBuf[1024]; // 256 stereo frames × 4 bytes = 1024 bytes
        if (echobase.record(rawBuf, 1024)) {
            int16_t* src = (int16_t*)rawBuf;
            int16_t* dst = (int16_t*)&recordBuffer[recordIndex];
            int samples = 1024 / 4; // 256 stereo frames
            for (int i = 0; i < samples; i++) {
                int16_t left = src[i * 2];
                int16_t right = src[i * 2 + 1];
                dst[i] = (left + right) / 2;
            }
            size_t monoBytes = samples * 2; // 512 bytes of 16-bit mono
            if (recordIndex + monoBytes <= RECORD_BUFFER_SIZE) {
                recordIndex += monoBytes;
            }
        }
    }
}

void HardwareIO::updateIMU() {
    if (M5.Imu.update()) {
        M5.Imu.getAccel(&ax, &ay, &az);
        
        // Tilt calculation (pitch and roll)
        pitch = atan2(-ax, sqrt(ay * ay + az * az)) * 180.0 / PI;
        roll = atan2(ay, az) * 180.0 / PI;

        // Auto display orientation based on accelerometer gravity vector
        int newOrient = orientation;
        if (ay > 0.65f) {
            newOrient = 0; // Normal upright (0 deg)
        } else if (ay < -0.65f) {
            newOrient = 2; // Upside down (180 deg)
        } else if (ax > 0.65f) {
            newOrient = 1; // Rotated 90 deg clockwise
        } else if (ax < -0.65f) {
            newOrient = 3; // Rotated 270 deg counter-clockwise
        }

        if (newOrient != orientation) {
            orientation = newOrient;
            M5.Display.setRotation(orientation);
            if (orientation == 2) {
                petState.setEmotion(PetEmotion::DIZZY, "Upside down!");
            }
        }

        // Multi-level Shake Detection
        float magnitude = sqrt(ax*ax + ay*ay + az*az);
        unsigned long now = millis();

        if (magnitude > 2.2f) { // Acceleration > 2.2G
            if (now - lastShakeDetectTime > 350) { // Debounce
                shakeCount++;
                lastShakeDetectTime = now;
                lastShakeTime = now;
                shaking = true;

                if (shakeCount == 1) {
                    petState.setEmotion(PetEmotion::HAPPY, "Whoa!");
                    playTone(1200, 60);
                } else if (shakeCount == 3) {
                    petState.setEmotion(PetEmotion::DIZZY, "Dizzy!");
                    playTone(800, 80);
                    playTone(600, 80);
                } else if (shakeCount >= 5) {
                    // Super shake: Party / Fortune Teller / Dice Roll Mini-Game!
                    int outcome = random(0, 4);
                    if (outcome == 0) {
                        petState.setEmotion(PetEmotion::PARTY, "PARTY!");
                        playTone(1500, 80); playTone(1800, 80); playTone(2100, 120);
                    } else if (outcome == 1) {
                        petState.setEmotion(PetEmotion::HAPPY, "Magic 8: YES!");
                        playTone(1800, 150);
                    } else if (outcome == 2) {
                        petState.setEmotion(PetEmotion::SAD, "Magic 8: NO!");
                        playTone(500, 200);
                    } else {
                        char diceStr[20];
                        snprintf(diceStr, sizeof(diceStr), "Roll: %d!", random(1, 7));
                        petState.setEmotion(PetEmotion::HAPPY, diceStr);
                        playTone(1400, 80); playTone(1600, 80);
                    }
                    shakeCount = 0; // Reset after mega combo
                }
            }
        }
    }
    
    // Clear shake state after inactivity
    if (shaking && (millis() - lastShakeTime > 2500)) {
        shaking = false;
        shakeCount = 0;
    }
}

void HardwareIO::checkButtons() {
    // Single click (short)
    if (M5.BtnA.wasClicked()) {
        petState.addAttention(20);
        petState.setEmotion(PetEmotion::LOVE, "Pat pat!");
        playTone(1500, 100);
    }
}
