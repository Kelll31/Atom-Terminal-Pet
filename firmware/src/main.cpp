#include <M5Unified.h>
#include <WiFi.h>
#include <Preferences.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include "pet_display.h"

#ifndef DEFAULT_WIFI_SSID
#define DEFAULT_WIFI_SSID ""
#endif

#ifndef DEFAULT_WIFI_PASS
#define DEFAULT_WIFI_PASS ""
#endif

#ifndef DEFAULT_SERVER_IP
#define DEFAULT_SERVER_IP "192.168.1.100"
#endif

Preferences preferences;
char wifi_ssid[64] = "";
char wifi_pass[64] = "";
char server_ip[64] = "192.168.1.100";
const int websocket_port = 8000;
const char* websocket_path = "/ws/audio";

WebSocketsClient webSocket;

static constexpr size_t RECORD_BUFFER_SIZE = 16000 * 2 * 3; // 3 sec, 16kHz, 16-bit
uint8_t* record_buffer = nullptr;
size_t record_index = 0;
bool is_recording = false;
bool is_wifi_connected = false;
bool is_ws_connected = false;
unsigned long last_anim_update = 0;

void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
    switch(type) {
        case WStype_DISCONNECTED:
            Serial.println("[WS] Disconnected!");
            is_ws_connected = false;
            setPetEmotion("sad", "WS Disconnected");
            break;
        case WStype_CONNECTED:
            Serial.println("[WS] Connected to server");
            is_ws_connected = true;
            setPetEmotion("happy", "Ready!");
            break;
        case WStype_BIN:
            Serial.printf("[WS] Audio reply length: %u\n", length);
            setPetEmotion("talking");
            M5.Speaker.playRaw((const int16_t*)payload, length / 2, 16000, true);
            setPetEmotion("happy");
            break;
        case WStype_TEXT: {
            String msg = String((char*)payload);
            if (msg.startsWith("EMOTION:")) {
                String emotion = msg.substring(8);
                setPetEmotion(emotion.c_str());
            }
            break;
        }
        case WStype_ERROR:
        case WStype_FRAGMENT_TEXT_START:
        case WStype_FRAGMENT_BIN_START:
        case WStype_FRAGMENT:
        case WStype_FRAGMENT_FIN:
            break;
    }
}

void loadConfig() {
    preferences.begin("ai-companion", true); // read-only
    String saved_ssid = preferences.getString("wifi_ssid", DEFAULT_WIFI_SSID);
    String saved_pass = preferences.getString("wifi_pass", DEFAULT_WIFI_PASS);
    String saved_ip   = preferences.getString("server_ip", DEFAULT_SERVER_IP);
    preferences.end();

    if (saved_ssid.length() == 0 && strlen(DEFAULT_WIFI_SSID) > 0) {
        saved_ssid = DEFAULT_WIFI_SSID;
        saved_pass = DEFAULT_WIFI_PASS;
    }
    if (saved_ip.length() == 0 && strlen(DEFAULT_SERVER_IP) > 0) {
        saved_ip = DEFAULT_SERVER_IP;
    }

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

bool connectWiFi(int timeout_ms = 10000) {
    if (strlen(wifi_ssid) == 0) {
        Serial.println("No WiFi SSID stored in NVS.");
        setPetEmotion("sad", "No WiFi! Connect USB");
        return false;
    }

    Serial.printf("Connecting to WiFi SSID: %s\n", wifi_ssid);
    setPetEmotion("tool", "Connecting WiFi...");

    WiFi.mode(WIFI_STA);
    WiFi.begin(wifi_ssid, wifi_pass);

    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < (unsigned long)timeout_ms) {
        delay(250);
        Serial.print(".");
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        is_wifi_connected = true;
        Serial.print("WiFi Connected! IP: ");
        Serial.println(WiFi.localIP());
        setPetEmotion("happy", "WiFi Connected!");
        return true;
    } else {
        is_wifi_connected = false;
        Serial.println("WiFi Connection Failed.");
        setPetEmotion("sad", "WiFi Failed!");
        return false;
    }
}

void startWebSocket() {
    if (!is_wifi_connected) return;
    Serial.printf("Starting WS connection to %s:%d%s\n", server_ip, websocket_port, websocket_path);
    setPetEmotion("tool", "Connecting WS...");

    webSocket.begin(server_ip, websocket_port, websocket_path);
    webSocket.onEvent(webSocketEvent);
    webSocket.setReconnectInterval(5000);
}

void checkSerialConfig() {
    if (!Serial.available()) return;

    String input = Serial.readStringUntil('\n');
    input.trim();
    if (input.length() == 0) return;

    StaticJsonDocument<512> doc;
    DeserializationError err = deserializeJson(doc, input);

    if (!err && doc.containsKey("ssid") && doc.containsKey("pass")) {
        const char* new_ssid = doc["ssid"] | "";
        const char* new_pass = doc["pass"] | "";
        const char* new_server = doc["server"] | server_ip;

        Serial.printf("[USB CONFIG] Saving new WiFi credentials: SSID='%s', Server='%s'\n", new_ssid, new_server);
        saveConfig(new_ssid, new_pass, new_server);

        StaticJsonDocument<256> resp;
        resp["status"] = "ok";
        resp["msg"] = "Configuration saved successfully. Connecting to WiFi...";
        serializeJson(resp, Serial);
        Serial.println();

        WiFi.disconnect(true);
        delay(500);

        if (connectWiFi()) {
            startWebSocket();
        }
    } else if (input == "GET_CONFIG") {
        StaticJsonDocument<256> resp;
        resp["status"] = "ok";
        resp["ssid"] = wifi_ssid;
        resp["server"] = server_ip;
        resp["wifi_connected"] = is_wifi_connected;
        resp["ip"] = is_wifi_connected ? WiFi.localIP().toString() : "";
        serializeJson(resp, Serial);
        Serial.println();
    } else if (input == "RESET_CONFIG") {
        saveConfig("", "", "192.168.1.100");
        WiFi.disconnect(true);
        is_wifi_connected = false;
        setPetEmotion("sad", "Config Reset");

        StaticJsonDocument<128> resp;
        resp["status"] = "ok";
        resp["msg"] = "Settings cleared";
        serializeJson(resp, Serial);
        Serial.println();
    }
}

void setup() {
    auto cfg = M5.config();
    M5.begin(cfg);
    Serial.begin(115200);

    // Initialize 128x128 Pet Display Sprite
    initPetDisplay();

    loadConfig();

    auto spk_cfg = M5.Speaker.config();
    spk_cfg.sample_rate = 16000;
    M5.Speaker.config(spk_cfg);
    M5.Speaker.begin();

    auto mic_cfg = M5.Mic.config();
    mic_cfg.sample_rate = 16000;
    M5.Mic.config(mic_cfg);
    M5.Mic.begin();

    record_buffer = (uint8_t*)malloc(RECORD_BUFFER_SIZE);

    if (strlen(wifi_ssid) > 0) {
        if (connectWiFi()) {
            startWebSocket();
        }
    } else {
        setPetEmotion("sad", "WiFi Setup Required");
    }
}

void loop() {
    M5.update();
    checkSerialConfig();

    if (is_wifi_connected) {
        webSocket.loop();
    }

    // 25 FPS Screen Render Loop (Double Buffered Canvas in pet_display)
    unsigned long now = millis();
    if (now - last_anim_update >= 40) {
        last_anim_update = now;
        renderPetFrame();
        canvas.pushSprite(0, 0);
    }

    // Long press screen (5 seconds): Reset settings
    if (M5.BtnA.pressedFor(5000)) {
        setPetEmotion("sad", "Resetting...");
        saveConfig("", "", "192.168.1.100");
        WiFi.disconnect(true);
        delay(2000);
        ESP.restart();
    }

    // Tap Screen: Pet the Pet!
    if (M5.BtnA.wasClicked() && !is_recording) {
        Serial.println("Screen tapped: Patting the pet!");
        setPetEmotion("love", "Love you!");
        M5.Speaker.tone(1500, 100);
        delay(120);
        M5.Speaker.tone(2000, 150);
        if (is_wifi_connected && is_ws_connected) {
            webSocket.sendTXT("PET_ACTION:pat");
        }
    }

    // Hold Screen: Voice Recording
    if (M5.BtnA.wasPressed() && !M5.BtnA.pressedFor(5000)) {
        if (is_wifi_connected && is_ws_connected) {
            is_recording = true;
            record_index = 0;
            setPetEmotion("recording", "Listening...");
            Serial.println("Start Recording...");
        } else {
            Serial.println("Cannot record: WiFi or WS not connected.");
        }
    }

    if (is_recording) {
        if (M5.Mic.record(&record_buffer[record_index], 1024, 16000)) {
            record_index += 1024;
            if (record_index >= RECORD_BUFFER_SIZE - 1024) {
                is_recording = false;
                setPetEmotion("thinking", "Thinking...");
                Serial.println("Buffer full, sending...");
                webSocket.sendBIN(record_buffer, record_index);
            }
        }
    }

    if (M5.BtnA.wasReleased() && is_recording) {
        is_recording = false;
        setPetEmotion("thinking", "Thinking...");
        Serial.println("Stop Recording, sending...");
        webSocket.sendBIN(record_buffer, record_index);
    }
}
