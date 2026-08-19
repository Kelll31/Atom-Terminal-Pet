#include <Arduino.h>
#include <WiFi.h>
#include <Preferences.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

#include "PetState.h"
#include "PetAnimator.h"
#include "HardwareIO.h"
#include "PCTracker.h"

// Forward declarations
void sendSerialData(uint8_t type, const uint8_t* data, uint32_t length);

// Configuration
Preferences preferences;
char wifi_ssid[64] = "";
char wifi_pass[64] = "";
char server_ip[64] = "192.168.1.100";
const int websocket_port = 8000;
const char* websocket_path = "/ws/pet";

WebSocketsClient webSocket;
bool is_wifi_connected = false;
bool is_ws_connected = false;
unsigned long lastAudioRxTime = 0;
bool wsJustConnected = false;       // Flag: transition to LISTENING after WS connect
unsigned long wsConnectTime = 0;    // Time of last WS connection

// Task handles
TaskHandle_t renderTaskHandle;

// --- Config Functions ---
void loadConfig() {
    preferences.begin("ai-companion", true);
    String saved_ssid = preferences.getString("wifi_ssid", "");
    String saved_pass = preferences.getString("wifi_pass", "");
    String saved_ip   = preferences.getString("server_ip", "192.168.1.100");
    int saved_rotation = preferences.getInt("rotation", 0);
    preferences.end();
    
    M5.Display.setRotation(saved_rotation);

    strncpy(wifi_ssid, saved_ssid.c_str(), sizeof(wifi_ssid) - 1);
    strncpy(wifi_pass, saved_pass.c_str(), sizeof(wifi_pass) - 1);
    strncpy(server_ip, saved_ip.c_str(), sizeof(server_ip) - 1);
}

void saveConfig(const char* ssid, const char* pass, const char* server) {
    preferences.begin("ai-companion", false);
    preferences.putString("wifi_ssid", ssid);
    preferences.putString("wifi_pass", pass);
    preferences.putString("server_ip", server);
    preferences.end();
    
    strncpy(wifi_ssid, ssid, sizeof(wifi_ssid) - 1);
    strncpy(wifi_pass, pass, sizeof(wifi_pass) - 1);
    strncpy(server_ip, server, sizeof(server_ip) - 1);
}

bool connectWiFi() {
    if (strlen(wifi_ssid) == 0) {
        petState.setEmotion(PetEmotion::INIT, "No WiFi Config");
        return false;
    }
    
    petState.setEmotion(PetEmotion::THINKING, "Connecting WiFi...");
    WiFi.mode(WIFI_STA);
    WiFi.begin(wifi_ssid, wifi_pass);
    
    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 10000) {
        delay(250);
    }
    
    is_wifi_connected = (WiFi.status() == WL_CONNECTED);
    if (is_wifi_connected) {
        String ipStr = WiFi.localIP().toString();
        petState.setEmotion(PetEmotion::HAPPY, ipStr.c_str());
    } else {
        petState.setEmotion(PetEmotion::SAD, "WiFi Fail");
    }
    return is_wifi_connected;
}

// --- WebSocket Handling ---
void handleJsonCommand(const char* payload) {
    StaticJsonDocument<512> doc;
    DeserializationError err = deserializeJson(doc, payload);
    if (err) return;
    
    if (doc.containsKey("action")) {
        String action = doc["action"].as<String>();
        if (action == "update_pc") {
            int cpu = doc["cpu"] | 0;
            int ram = doc["ram"] | 0;
            int gpu = doc["gpu"] | 0;
            int temp = doc["temp"] | 0;
            pcTracker.setMetrics(cpu, ram, gpu, temp);
            
            if (doc.containsKey("spotify")) {
                pcTracker.setSpotify(doc["spotify"].as<const char*>());
            } else {
                pcTracker.clearSpotify();
            }
        } else if (action == "speak" || action == "set_emotion") {
            const char* emotion = doc["emotion"] | "idle";
            const char* text = doc["text"] | "";
            PetEmotion emo = PetEmotion::IDLE;
            if (strcmp(emotion, "happy") == 0) emo = PetEmotion::HAPPY;
            else if (strcmp(emotion, "angry") == 0) emo = PetEmotion::ANGRY;
            else if (strcmp(emotion, "sleepy") == 0 || strcmp(emotion, "sleeping") == 0) emo = PetEmotion::SLEEPING;
            else if (strcmp(emotion, "panic") == 0) emo = PetEmotion::PANIC;
            else if (strcmp(emotion, "sad") == 0) emo = PetEmotion::SAD;
            else if (strcmp(emotion, "love") == 0) emo = PetEmotion::LOVE;
            else if (strcmp(emotion, "dizzy") == 0) emo = PetEmotion::DIZZY;
            else if (strcmp(emotion, "talking") == 0) emo = PetEmotion::TALKING;
            else if (strcmp(emotion, "listening") == 0) emo = PetEmotion::LISTENING;
            else if (strcmp(emotion, "thinking") == 0) emo = PetEmotion::THINKING;
            else if (strcmp(emotion, "party") == 0) emo = PetEmotion::PARTY;
            else if (strcmp(emotion, "sweat") == 0) emo = PetEmotion::SWEAT;
            else if (strcmp(emotion, "working") == 0) emo = PetEmotion::WORKING;
            petState.setEmotion(emo, text);
        } else if (action == "pomodoro") {
            int timeLeft = doc["time_left"] | 0;
            pcTracker.setPomodoro(timeLeft);
        } else if (action == "set_rotation") {
            int r = doc["rotation"] | 0;
            M5.Display.setRotation(r);
            preferences.begin("ai-companion", false);
            preferences.putInt("rotation", r);
            preferences.end();
        }
    }
}

void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
    switch(type) {
        case WStype_DISCONNECTED:
            is_ws_connected = false;
            petState.setEmotion(PetEmotion::SAD, "WS Reconnecting...");
            break;
        case WStype_CONNECTED:
            is_ws_connected = true;
            petState.setEmotion(PetEmotion::HAPPY, "Online");
            wsJustConnected = true;    // Will auto-transition to LISTENING after 3s
            wsConnectTime = millis();
            {
                StaticJsonDocument<256> statusDoc;
                statusDoc["action"] = "device_status";
                statusDoc["device"] = "AtomS3";
                statusDoc["ip"] = WiFi.localIP().toString();
                statusDoc["ssid"] = WiFi.SSID();
                statusDoc["rssi"] = WiFi.RSSI();
                String statusStr;
                serializeJson(statusDoc, statusStr);
                webSocket.sendTXT(statusStr);
                sendSerialData(0x01, (const uint8_t*)statusStr.c_str(), statusStr.length());
            }
            break;
        case WStype_TEXT:
            handleJsonCommand((const char*)payload);
            break;
        case WStype_BIN:
            lastAudioRxTime = millis();
            if (petState.getEmotion() != PetEmotion::TALKING) {
                petState.setEmotion(PetEmotion::TALKING);
            }
            hardwareIO.enqueueAudio(payload, length);
            break;
        default:
            break;
    }
}

void sendSerialData(uint8_t type, const uint8_t* data, uint32_t length) {
    if (!Serial) return;
    uint8_t header[7];
    header[0] = 0xAA;
    header[1] = 0xBB;
    header[2] = type;
    header[3] = length & 0xFF;
    header[4] = (length >> 8) & 0xFF;
    header[5] = (length >> 16) & 0xFF;
    header[6] = (length >> 24) & 0xFF;
    Serial.write(header, 7);
    Serial.write(data, length);
}

// --- Serial Protocol Handling ---
void processSerial() {
    static int state = 0;
    static uint8_t msg_type = 0;
    static uint32_t msg_length = 0;
    static uint32_t bytes_read = 0;
    static uint8_t* payload_buffer = nullptr;
    static String text_buffer = ""; // For plain-text JSON fallback

    while (Serial.available()) {
        if (state == 0) { // Waiting for 0xAA or '{'
            uint8_t b = Serial.read();
            if (b == 0xAA) {
                state = 1;
            } else if (b == '{') {
                // Legacy plain-text JSON started!
                text_buffer = "{";
                state = 10;
            }
        } else if (state == 10) { // Reading plain-text JSON until newline
            char c = Serial.read();
            if (c == '\n' || c == '\r') {
                if (text_buffer.length() > 0) {
                    StaticJsonDocument<512> doc;
                    DeserializationError err = deserializeJson(doc, text_buffer);
                    if (!err) {
                        if (doc.containsKey("ssid")) {
                            saveConfig(doc["ssid"] | "", doc["pass"] | "", doc["server"] | server_ip);
                            ESP.restart();
                        } else {
                            handleJsonCommand(text_buffer.c_str());
                        }
                    }
                }
                text_buffer = "";
                state = 0;
            } else {
                text_buffer += c;
                if (text_buffer.length() > 512) state = 0; // Prevent overflow
            }
        } else if (state == 1) { // Waiting for 0xBB
            if (Serial.read() == 0xBB) state = 2;
            else state = 0;
        } else if (state == 2) { // Read Type
            msg_type = Serial.read();
            state = 3;
            bytes_read = 0;
            msg_length = 0;
        } else if (state == 3) { // Read Length (4 bytes, little endian)
            msg_length |= (Serial.read() << (bytes_read * 8));
            bytes_read++;
            if (bytes_read == 4) {
                if (msg_length > 0 && msg_length < 1000000) { // Sanity check
                    payload_buffer = (uint8_t*)malloc(msg_length + 1);
                    if (!payload_buffer) {
                        state = 0; // OOM
                    } else {
                        state = 4;
                        bytes_read = 0;
                    }
                } else {
                    state = 0; // Invalid length
                }
            }
        } else if (state == 4) { // Read Payload
            int avail = Serial.available();
            int to_read = msg_length - bytes_read;
            if (avail > to_read) avail = to_read;
            
            Serial.readBytes(&payload_buffer[bytes_read], avail);
            bytes_read += avail;
            
            if (bytes_read == msg_length) {
                if (msg_type == 0x01) { // JSON
                    payload_buffer[msg_length] = '\0'; // Null terminate string
                    String input = String((char*)payload_buffer);
                    StaticJsonDocument<512> doc;
                    DeserializationError err = deserializeJson(doc, input);
                    if (!err) {
                        if (doc.containsKey("ssid")) {
                            saveConfig(doc["ssid"] | "", doc["pass"] | "", doc["server"] | server_ip);
                            ESP.restart();
                        } else {
                            handleJsonCommand(input.c_str());
                        }
                    }
                } else if (msg_type == 0x02) { // Binary Audio
                    lastAudioRxTime = millis();
                    if (petState.getEmotion() != PetEmotion::TALKING) {
                        petState.setEmotion(PetEmotion::TALKING);
                    }
                    hardwareIO.enqueueAudio(payload_buffer, msg_length);
                }
                free(payload_buffer);
                payload_buffer = nullptr;
                state = 0;
            }
        }
    }
}

// --- FreeRTOS Tasks ---
void taskRender(void *pvParameters) {
    // Run indefinitely
    while (true) {
        unsigned long start = millis();
        
        petAnimator.updateTargets(hardwareIO.getPitch(), hardwareIO.getRoll());
        petAnimator.renderFrame();
        
        // Try to keep ~30 FPS (33ms per frame)
        unsigned long duration = millis() - start;
        if (duration < 33) {
            vTaskDelay((33 - duration) / portTICK_PERIOD_MS);
        } else {
            vTaskDelay(1 / portTICK_PERIOD_MS); // Yield
        }
    }
}

// --- Main Setup and Loop ---
void setup() {
    auto cfg = M5.config();
    M5.begin(cfg);
    Serial.begin(115200);

    // Initialize modules
    petAnimator.init();
    hardwareIO.init();
    
    loadConfig();
    
    if (connectWiFi()) {
        webSocket.begin(server_ip, websocket_port, websocket_path);
        webSocket.onEvent(webSocketEvent);
        webSocket.setReconnectInterval(5000);
        hardwareIO.startRecording(); // Start continuous recording
    }
    
    // Create Render Task on Core 0 (App core is 1, PRO core is 0)
    xTaskCreatePinnedToCore(
        taskRender,     // Task function
        "RenderTask",   // Name
        8192,           // Stack size
        NULL,           // Parameters
        1,              // Priority
        &renderTaskHandle, // Handle
        0               // Core ID (0)
    );
}

void loop() {
    // Core 1 (Main Loop) handles logic, WiFi, WS, IO
    hardwareIO.update();
    petState.update();
    pcTracker.update();
    
    if (is_wifi_connected) {
        webSocket.loop();
    } else {
        // Fallback: If WiFi fails but we are connected via USB, start recording anyway
        if (!hardwareIO.isRecording() && Serial) {
            hardwareIO.startRecording();
            petState.setEmotion(PetEmotion::HAPPY, "USB Connected");
        }
    }
    
    processSerial();
    
    // Auto-detect end of audio playback.
    // Wait for BOTH conditions to prevent echo (mic picking up speaker):
    //   1. Backend has stopped sending chunks (350ms silence on WebSocket)
    //   2. I2S DMA has drained after last play() call (500ms > chunk duration of 128ms)
    unsigned long now = millis();
    if (petState.getEmotion() == PetEmotion::TALKING 
        && (now - lastAudioRxTime > 350)
        && (now - hardwareIO.getLastPlayTime() > 500)) {
        hardwareIO.stopAudioPlayback(); // Zero out DMA buffer to eliminate repeating noise
        hardwareIO.resetRecordBuffer(); // Flush mic buffer recorded during speech
        petState.setEmotion(PetEmotion::LISTENING, "Listening...");
    }

    // Handle continuous audio streaming
    // IMPORTANT: send via only ONE channel to prevent duplicate STT/TTS pipeline triggers.
    // When WiFi is connected, M5 uses WebSocket; Serial is fallback for USB-only mode.
    if (hardwareIO.isRecording() && hardwareIO.hasAudioChunk() && petState.getEmotion() != PetEmotion::TALKING) {
        size_t len = hardwareIO.getRecordSize();
        if (len > 0) {
            if (is_ws_connected) {
                webSocket.sendBIN(hardwareIO.getRecordBuffer(), len); // WiFi preferred
            } else {
                sendSerialData(0x02, hardwareIO.getRecordBuffer(), len); // USB-only fallback
            }
        }
        hardwareIO.resetRecordBuffer();
    }
    
    // Handle shake events -> notify backend
    static bool wasShaking = false;
    if (hardwareIO.isShaking()) {
        if (!wasShaking) {
            wasShaking = true;
            StaticJsonDocument<128> shakeDoc;
            shakeDoc["action"] = "shake";
            shakeDoc["count"] = hardwareIO.getShakeCount();
            String shakeStr;
            serializeJson(shakeDoc, shakeStr);
            if (is_ws_connected) webSocket.sendTXT(shakeStr);
            sendSerialData(0x01, (const uint8_t*)shakeStr.c_str(), shakeStr.length());
        }
    } else {
        wasShaking = false;
    }
    
    // Auto-transition from HAPPY to LISTENING state after WebSocket connects.
    // Without this, device stays HAPPY forever (no LISTENING animation shown until first TTS).
    if (wsJustConnected && millis() - wsConnectTime > 3000) {
        wsJustConnected = false;
        if (hardwareIO.isRecording() && petState.getEmotion() == PetEmotion::HAPPY) {
            petState.setEmotion(PetEmotion::LISTENING, "Listening...");
        }
    }
    
    // Don't starve watchdog
    delay(5);
}
