/**
 * Atom-Terminal-Pet — прошивка M5Stack AtomS3R + Atomic Echo Base.
 *
 * Что делает устройство:
 *   • непрерывно слушает микрофон и стримит звук серверу (Wi-Fi или USB);
 *   • проигрывает ответ через ES8311 из кольцевого буфера (отдельная задача);
 *   • рисует Патрика 128x128 с мимикой под эмоцию и громкость речи;
 *   • показывает метрики ПК, часы и состояние сети на отдельных экранах;
 *   • реагирует на кнопку, тряску, наклон и приближение руки (LTR-553);
 *   • позволяет перебить питомца: кнопка или встряска во время речи.
 *
 * Разделение по задачам:
 *   audio_tx / audio_rx  — единственные владельцы I2S (см. AudioIO);
 *   serial               — разбор кадров USB, ничего не исполняет сам;
 *   render               — отрисовка кадра, ядро 0;
 *   loop()               — всё остальное: кнопка, жесты, команды, стрим микрофона.
 */

#include <Arduino.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <time.h>

#include "Config.h"
#include "AudioIO.h"
#include "Link.h"
#include "Motion.h"
#include "PCTracker.h"
#include "PetAnimator.h"
#include "PetState.h"
#include "Sensors.h"

// ── Настройки устройства ────────────────────────────────────────────────────
static Preferences preferences;

static char wifi_ssid[64] = "";
static char wifi_pass[64] = "";
static char server_ip[64] = "192.168.1.100";
static char pet_name[17]  = "Atom";
static char ota_pass[33]  = "";
static int  rotation      = 0;
static bool auto_rotate   = false;   // по умолчанию слушаемся настройки из панели
static uint8_t volume     = 80;

static bool mic_muted = false;
static bool audio_ok  = false;
static bool auto_brightness = true;

static uint32_t lastStatusSent = 0;

static void sendDeviceStatus();

// ── Настройки в NVS ─────────────────────────────────────────────────────────
static void loadConfig() {
    preferences.begin("ai-companion", true);
    String savedSsid = preferences.getString("wifi_ssid", "");
    String savedPass = preferences.getString("wifi_pass", "");
    String savedIp   = preferences.getString("server_ip", "192.168.1.100");
    String savedName = preferences.getString("pet_name", "Atom");
    String savedOta  = preferences.getString("ota_pass", "");
    rotation    = preferences.getInt("rotation", 0);
    auto_rotate = preferences.getBool("auto_rot", false);
    volume      = (uint8_t)preferences.getUChar("volume", 80);
    preferences.end();

    strncpy(wifi_ssid, savedSsid.c_str(), sizeof(wifi_ssid) - 1);
    strncpy(wifi_pass, savedPass.c_str(), sizeof(wifi_pass) - 1);
    strncpy(server_ip, savedIp.c_str(), sizeof(server_ip) - 1);
    strncpy(pet_name,  savedName.c_str(), sizeof(pet_name) - 1);
    strncpy(ota_pass,  savedOta.c_str(), sizeof(ota_pass) - 1);

#ifdef DEFAULT_WIFI_SSID
    if (strlen(wifi_ssid) == 0) strncpy(wifi_ssid, DEFAULT_WIFI_SSID, sizeof(wifi_ssid) - 1);
#endif
#ifdef DEFAULT_WIFI_PASS
    if (strlen(wifi_pass) == 0) strncpy(wifi_pass, DEFAULT_WIFI_PASS, sizeof(wifi_pass) - 1);
#endif
#ifdef DEFAULT_SERVER_IP
    if (strcmp(server_ip, "192.168.1.100") == 0) strncpy(server_ip, DEFAULT_SERVER_IP, sizeof(server_ip) - 1);
#endif

    petAnimator.setPetName(pet_name);
}

static void saveNetworkConfig(const char* ssid, const char* pass, const char* server,
                              const char* name, const char* ota) {
    preferences.begin("ai-companion", false);
    if (ssid)   preferences.putString("wifi_ssid", ssid);
    if (pass)   preferences.putString("wifi_pass", pass);
    if (server) preferences.putString("server_ip", server);
    if (name && name[0]) preferences.putString("pet_name", name);
    if (ota)    preferences.putString("ota_pass", ota);
    preferences.end();
}

// ── Отчёт о состоянии ───────────────────────────────────────────────────────
static void sendDeviceStatus() {
    StaticJsonDocument<512> doc;
    doc["action"]  = "device_status";
    doc["device"]  = "AtomS3R";
    doc["fw"]      = FW_VERSION;
    doc["ip"]      = netLink.ip();
    doc["ssid"]    = netLink.wifiConnected() ? String(netLink.ssid()) : String("usb");
    doc["rssi"]    = netLink.rssi();
    doc["mic"]     = !mic_muted;
    doc["audio"]   = audio_ok;
    doc["sensors"] = sensors.isAvailable();
    doc["i2c"]     = sensors.getBusReport();
    doc["psram"]   = psramFound();
    doc["heap"]    = (int)(ESP.getFreeHeap() / 1024);
    doc["volume"]  = volume;
    // Счётчики потерь помогают отличить «сеть тормозит» от «прошивка не успевает»
    doc["drop_out"] = audioIO.droppedPlayBytes();
    doc["drop_in"]  = audioIO.droppedMicChunks();
    netLink.sendJson(doc);
    lastStatusSent = millis();
}

static void sendSimpleEvent(const char* action, const char* key = nullptr,
                            const char* value = nullptr, int number = 0) {
    StaticJsonDocument<128> doc;
    doc["action"] = action;
    if (key && value) doc[key] = value;
    else if (key)     doc[key] = number;
    netLink.sendJson(doc);
}

// Прерывание речи: чистим буфер и сообщаем серверу
static void interruptSpeech(const char* reason) {
    audioIO.stopPlayback();
    petState.setEmotion(PetEmotion::LISTENING, "Slushayu");
    petState.resetIdleTimer();
    petAnimator.showBubble("Slushayu!", 2000);
    audioIO.playChime(Chime::LISTEN);
    sendSimpleEvent("interrupt", "reason", reason);
}

// ── Команды сервера ─────────────────────────────────────────────────────────
static PetEmotion parseEmotion(const char* name) {
    if (!name) return PetEmotion::IDLE;
    if (!strcmp(name, "happy"))     return PetEmotion::HAPPY;
    if (!strcmp(name, "angry"))     return PetEmotion::ANGRY;
    if (!strcmp(name, "sad"))       return PetEmotion::SAD;
    if (!strcmp(name, "love"))      return PetEmotion::LOVE;
    if (!strcmp(name, "dizzy"))     return PetEmotion::DIZZY;
    if (!strcmp(name, "sleepy") || !strcmp(name, "sleeping")) return PetEmotion::SLEEPING;
    if (!strcmp(name, "working"))   return PetEmotion::WORKING;
    if (!strcmp(name, "listening")) return PetEmotion::LISTENING;
    if (!strcmp(name, "talking"))   return PetEmotion::TALKING;
    if (!strcmp(name, "thinking"))  return PetEmotion::THINKING;
    if (!strcmp(name, "panic"))     return PetEmotion::PANIC;
    if (!strcmp(name, "sweat"))     return PetEmotion::SWEAT;
    if (!strcmp(name, "party"))     return PetEmotion::PARTY;
    return PetEmotion::IDLE;
}

static void applyRotation(int value) {
    rotation = value & 3;
    petAnimator.requestRotation(rotation);
}

// Вызывается только из основного цикла (Link складывает команды в очередь),
// поэтому можно спокойно трогать дисплей, NVS и анимацию.
static void handleCommand(const char* payload) {
    StaticJsonDocument<768> doc;
    if (deserializeJson(doc, payload)) return;

    if (!doc.containsKey("action")) {
        if (doc.containsKey("ssid")) {  // конфигурация Wi-Fi из панели
            saveNetworkConfig(doc["ssid"] | "", doc["pass"] | "", doc["server"] | server_ip,
                              doc["pet_name"] | pet_name, doc["ota_pass"] | ota_pass);
            petAnimator.showBubble("Saved, restarting", 2000);
            delay(600);
            ESP.restart();
        }
        return;
    }

    const char* action = doc["action"];

    if (!strcmp(action, "update_pc")) {
        pcTracker.setMetrics(doc["cpu"] | 0, doc["ram"] | 0, doc["gpu"] | 0, doc["temp"] | 0);
        if (doc.containsKey("spotify")) pcTracker.setSpotify(doc["spotify"] | "");
        else pcTracker.clearSpotify();
        if (doc.containsKey("time_left")) pcTracker.setPomodoro(doc["time_left"] | 0);

    } else if (!strcmp(action, "speak") || !strcmp(action, "set_emotion")) {
        PetEmotion emotion = parseEmotion(doc["emotion"] | "idle");
        const char* text = doc["text"] | "";
        petState.setEmotion(emotion, "");
        petState.resetIdleTimer();
        if (text[0]) petAnimator.showBubble(text, 9000);

    } else if (!strcmp(action, "agent_status")) {
        const char* state = doc["state"] | "";
        if (!strcmp(state, "thinking"))      petState.setEmotion(PetEmotion::THINKING, "");
        else if (!strcmp(state, "working"))  petState.setEmotion(PetEmotion::WORKING, doc["tool"] | "");
        else if (!strcmp(state, "speaking")) petState.setEmotion(PetEmotion::TALKING, "");
        else if (!strcmp(state, "idle"))     petState.setBaseEmotion(PetEmotion::LISTENING, "");

    } else if (!strcmp(action, "listening")) {
        petState.setBaseEmotion(PetEmotion::LISTENING, "");

    } else if (!strcmp(action, "stop_audio")) {
        audioIO.stopPlayback();
        petState.setEmotion(PetEmotion::LISTENING, "");

    } else if (!strcmp(action, "beep")) {
        audioIO.playChime(Chime::NOTIFY);

    } else if (!strcmp(action, "pomodoro")) {
        pcTracker.setPomodoro(doc["time_left"] | 0);
        petState.setEmotion(PetEmotion::WORKING, "Focus");

    } else if (!strcmp(action, "set_rotation")) {
        // Явный поворот из панели выключает автоповорот: иначе IMU тут же
        // возвращал экран обратно, и настройка выглядела сломанной.
        auto_rotate = false;
        applyRotation(doc["rotation"] | 0);
        preferences.begin("ai-companion", false);
        preferences.putInt("rotation", rotation);
        preferences.putBool("auto_rot", false);
        preferences.end();

    } else if (!strcmp(action, "set_autorotate")) {
        auto_rotate = doc["enabled"] | false;
        preferences.begin("ai-companion", false);
        preferences.putBool("auto_rot", auto_rotate);
        preferences.end();

    } else if (!strcmp(action, "set_screen")) {
        petAnimator.setScreen((PetScreen)(doc["screen"] | 0));

    } else if (!strcmp(action, "set_brightness")) {
        if (doc["auto"] | false) {
            auto_brightness = true;
        } else {
            auto_brightness = false;
            M5.Display.setBrightness(constrain((int)(doc["value"] | 128), 10, 255));
        }

    } else if (!strcmp(action, "set_volume")) {
        volume = (uint8_t)constrain((int)(doc["value"] | 80), 0, 100);
        audioIO.setVolume(volume);
        preferences.begin("ai-companion", false);
        preferences.putUChar("volume", volume);
        preferences.end();

    } else if (!strcmp(action, "set_mic")) {
        mic_muted = !(doc["enabled"] | true);
        audioIO.setMicMuted(mic_muted);
        sendDeviceStatus();

    } else if (!strcmp(action, "identify")) {
        petState.setEmotion(PetEmotion::PARTY, "Eto ya!");
        audioIO.playChime(Chime::PARTY);

    } else if (!strcmp(action, "restart")) {
        petAnimator.showBubble("Restarting", 1000);
        delay(400);
        ESP.restart();

    } else if (!strcmp(action, "status")) {
        sendDeviceStatus();
    }
}

// ── Взаимодействие ──────────────────────────────────────────────────────────
static void handleButton() {
    static bool longHoldHandled = false;

    ButtonEvent event = motion.pollButton();

    if (event != ButtonEvent::LONG_HOLD) longHoldHandled = false;
    if (event == ButtonEvent::NONE) return;

    petState.resetIdleTimer();

    // Во время речи любое нажатие — «дай сказать»
    if (event == ButtonEvent::CLICK && audioIO.isSpeaking()) {
        interruptSpeech("button");
        return;
    }

    switch (event) {
        case ButtonEvent::CLICK:
            petState.addAttention(20);
            petState.setEmotion(PetEmotion::LOVE, "Mur!");
            petAnimator.poke();
            audioIO.playChime(Chime::OK);
            sendSimpleEvent("pet_touched", "source", "button");
            break;

        case ButtonEvent::DOUBLE_CLICK:
            petAnimator.nextScreen();
            audioIO.playChime(Chime::TICK);
            break;

        case ButtonEvent::HOLD:
            mic_muted = !mic_muted;
            audioIO.setMicMuted(mic_muted);
            petAnimator.showBubble(mic_muted ? "Mic OFF" : "Mic ON", 2500);
            audioIO.playChime(mic_muted ? Chime::ERROR : Chime::LISTEN);
            sendDeviceStatus();
            break;

        case ButtonEvent::LONG_HOLD:
            if (!longHoldHandled) {
                longHoldHandled = true;
                petAnimator.setScreen(PetScreen::INFO);
            }
            if (M5.BtnA.pressedFor(6000)) {
                petAnimator.showBubble("Restarting", 1200);
                delay(500);
                ESP.restart();
            }
            break;

        default:
            break;
    }
}

static void handleGestures() {
    if (motion.isShaking()) {
        const int count = motion.shakeCount();
        petState.resetIdleTimer();

        if (audioIO.isSpeaking()) {
            interruptSpeech("shake");
        } else if (count >= 5) {
            petState.setEmotion(PetEmotion::PARTY, "Party!");
            audioIO.playChime(Chime::PARTY);
        } else if (count >= 3) {
            petState.setEmotion(PetEmotion::DIZZY, "Dizzy!");
        } else {
            petState.setEmotion(PetEmotion::HAPPY, "Hey!");
            petAnimator.poke();
        }

        sendSimpleEvent("shake", "count", nullptr, count);
        motion.clearShake();
    }

    if (motion.wasTapped()) {
        motion.clearTap();
        petAnimator.poke();
        petState.addAttention(5);
    }

    // Рука рядом — гладят (датчик приближения LTR-553)
    if (sensors.wasHandWaved()) {
        petState.addAttention(15);
        petState.setEmotion(PetEmotion::LOVE, "Pat pat");
        petAnimator.poke();
        audioIO.playChime(Chime::OK);
        sendSimpleEvent("pet_touched", "source", "proximity");
    }

    // Перевернули экраном вниз — «спрятался» и выключил микрофон
    static bool wasFaceDown = false;
    const bool faceDown = motion.isFaceDown();
    if (faceDown != wasFaceDown) {
        wasFaceDown = faceDown;
        if (faceDown) {
            petState.setEmotion(PetEmotion::SLEEPING, "zzz");
            audioIO.setMicMuted(true);
        } else {
            audioIO.setMicMuted(mic_muted);
            petState.setEmotion(PetEmotion::HAPPY, "Hi!");
            petState.resetIdleTimer();
        }
    }

    if (auto_rotate && motion.orientationChanged()) {
        applyRotation(motion.orientation());
    }
}

static void handleBrightness() {
    static uint32_t lastCheck = 0;
    static uint8_t current = 0;

    if (!auto_brightness) return;   // яркость задана из панели вручную

    const uint32_t now = millis();
    if (now - lastCheck < 2000) return;
    lastCheck = now;

    uint8_t target = sensors.isAvailable() ? sensors.suggestedBrightness() : 130;

    // Никто не трогал 5 минут и тишина — приглушаем экран
    if (now - motion.lastMotionMs() > 300000 && !audioIO.isPlaying()) {
        target = target / 3;
    }

    if (current != target) {
        current = target;
        M5.Display.setBrightness(target);
    }
}

// Появление и пропажа сети — событие, о котором стоит сказать вслух и на экране.
static void handleConnectivity() {
    static bool wifiWas = false;
    static bool serverWas = false;

    const bool wifiNow = netLink.wifiConnected();
    if (wifiNow != wifiWas) {
        wifiWas = wifiNow;
        if (wifiNow) {
            petAnimator.setNetworkInfo(netLink.ssid(), netLink.ip().c_str(), netLink.rssi());
            petState.setEmotion(PetEmotion::HAPPY, "WiFi OK");
            audioIO.playChime(Chime::OK);
            configTime(3 * 3600, 0, "pool.ntp.org", "time.google.com");
            netLink.enableOta(ota_pass);
        } else {
            petAnimator.setNetworkInfo("-", "usb", 0);
            petAnimator.showBubble("Wi-Fi lost, USB mode", 4000);
        }
    }

    const bool serverNow = netLink.wsConnected();
    if (serverNow != serverWas) {
        serverWas = serverNow;
        if (serverNow) {
            petState.setEmotion(PetEmotion::HAPPY, "Online");
            petState.setBaseEmotion(PetEmotion::LISTENING, "");
            audioIO.playChime(Chime::OK);
            sendDeviceStatus();
        } else {
            petState.setBaseEmotion(PetEmotion::IDLE, "");
        }
    }
}

// ── Задача отрисовки ────────────────────────────────────────────────────────
static void taskRender(void*) {
    TickType_t wake = xTaskGetTickCount();
    while (true) {
        petAnimator.setAudioLevel(audioIO.playbackLevel());
        petAnimator.setMicLevel(audioIO.micLevel());
        petAnimator.setFlags(mic_muted, netLink.wifiConnected(), netLink.serverOnline(),
                             sensors.isAvailable());
        petAnimator.setClock(time(nullptr) > 1700000000);
        petAnimator.updateTargets(motion.pitch(), motion.roll());
        petAnimator.renderFrame();

        // Ровная частота кадров вместо «сколько получилось»: анимация перестала
        // дёргаться, когда сеть или NVS отнимали время у ядра.
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(RENDER_PERIOD_MS));
    }
}

// ── setup / loop ────────────────────────────────────────────────────────────
void setup() {
    auto cfg = M5.config();
    cfg.serial_baudrate = 0;   // порт поднимает Link — ему нужен большой буфер
    M5.begin(cfg);

    M5.Display.setBrightness(140);

    loadConfig();
    applyRotation(rotation);

    if (!petAnimator.init()) {
        M5.Display.fillScreen(TFT_RED);
        M5.Display.drawString("no memory", 8, 56);
    }
    motion.begin();
    sensors.init();

    audio_ok = audioIO.begin();
    if (audio_ok) audioIO.setVolume(volume);

    petState.setEmotion(PetEmotion::INIT, "Boot");
    xTaskCreatePinnedToCore(taskRender, "render", STACK_RENDER, nullptr, PRIO_RENDER, nullptr, 0);

    netLink.onCommand(handleCommand);
    netLink.begin(wifi_ssid, wifi_pass, server_ip, pet_name);

    if (audio_ok) {
        audioIO.playChime(Chime::BOOT);
        audioIO.startRecording();
    } else {
        petAnimator.showBubble("Audio codec not found", 6000);
    }

    if (!wifi_ssid[0]) {
        petAnimator.showBubble("Nastroy Wi-Fi cherez USB", 8000);
    }

    petState.setBaseEmotion(PetEmotion::LISTENING, "");
    sendDeviceStatus();
}

void loop() {
    M5.update();
    motion.update();
    petState.update();
    pcTracker.update();
    sensors.update();

    netLink.loop();

    handleConnectivity();
    handleButton();
    handleGestures();
    handleBrightness();

    const uint32_t now = millis();

    // Речь закончилась — снова слушаем
    if (petState.getEmotion() == PetEmotion::TALKING && !audioIO.isSpeaking()) {
        petState.setEmotion(PetEmotion::LISTENING, "");
    }

    // Микрофон: задача записи уже отдала готовый кадр 32 мс — просто пересылаем.
    // За проход отдаём не больше двух кадров, чтобы цикл оставался отзывчивым.
    for (int i = 0; i < 2; i++) {
        size_t length = 0;
        const uint8_t* chunk = audioIO.takeChunk(length);
        if (!chunk) break;
        netLink.sendAudio(chunk, length);
        audioIO.releaseChunk();
    }

    // Звук пошёл в динамик — значит питомец говорит
    if (audioIO.isSpeaking() && petState.getEmotion() != PetEmotion::TALKING) {
        petState.setEmotion(PetEmotion::TALKING, "");
    }

    if (now - lastStatusSent > STATUS_PERIOD_MS) sendDeviceStatus();

    delay(2);
}
