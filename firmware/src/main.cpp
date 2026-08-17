#include <Arduino.h>
#include <WiFi.h>
#include <Preferences.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

#include "PetState.h"
#include "PetAnimator.h"
#include "HardwareIO.h"
#include "PCTracker.h"

// Configuration
Preferences preferences;
char wifi_ssid[64] = "";
char wifi_pass[64] = "";
char server_ip[64] = "192.168.1.100";
const int websocket_port = 8000;
const char* websocket_path = "/ws/audio";

WebSocketsClient webSocket;
bool is_wifi_connected = false;
bool is_ws_connected = false;

// Task handles
TaskHandle_t renderTaskHandle;

// --- Config Functions ---
void loadConfig() {
    preferences.begin("ai-companion", true);
    String saved_ssid = preferences.getString("wifi_ssid", "");
    String saved_pass = preferences.getString("wifi_pass", "");
    String saved_ip   = preferences.getString("server_ip", "192.168.1.100");
    preferences.end();
    
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
    if (strlen(wifi_ssid) == 0) return false;
    WiFi.mode(WIFI_STA);
    WiFi.begin(wifi_ssid, wifi_pass);
    
    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 10000) {
        delay(250);
    }
    
    is_wifi_connected = (WiFi.status() == WL_CONNECTED);
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
        } else if (action == "speak") {
            const char* emotion = doc["emotion"] | "talking";
            const char* text = doc["text"] | "";
            // map emotion string to enum (simplified)
            PetEmotion emo = PetEmotion::TALKING;
            if (strcmp(emotion, "happy") == 0) emo = PetEmotion::HAPPY;
            petState.setEmotion(emo, text);
        } else if (action == "pomodoro") {
            int timeLeft = doc["time_left"] | 0;
            pcTracker.setPomodoro(timeLeft);
        }
    }
}

void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
    switch(type) {
        case WStype_DISCONNECTED:
            is_ws_connected = false;
            break;
        case WStype_CONNECTED:
            is_ws_connected = true;
            petState.setEmotion(PetEmotion::HAPPY, "Connected");
            break;
        case WStype_TEXT:
            handleJsonCommand((const char*)payload);
            break;
        case WStype_BIN:
            petState.setEmotion(PetEmotion::TALKING);
            hardwareIO.playAudioStream(payload, length);
            petState.setEmotion(PetEmotion::IDLE);
            break;
        default:
            break;
    }
}

// --- Serial JSON Handling ---
void handleSerialJSON() {
    if (!Serial.available()) return;
    String input = Serial.readStringUntil('\n');
    input.trim();
    if (input.length() == 0) return;
    
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
    }
    
    handleSerialJSON();
    
    // Handle microphone recording finish
    static bool wasRecording = false;
    if (hardwareIO.isRecording()) {
        wasRecording = true;
    } else if (wasRecording) {
        // Just stopped recording
        wasRecording = false;
        size_t len = hardwareIO.getRecordSize();
        if (len > 0 && is_ws_connected) {
            webSocket.sendBIN(hardwareIO.getRecordBuffer(), len);
        }
        hardwareIO.resetRecordBuffer();
    }
    
    // Don't starve watchdog
    delay(5);
}
