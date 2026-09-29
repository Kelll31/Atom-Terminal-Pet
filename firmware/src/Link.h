#pragma once
#include <Arduino.h>
#include <IPAddress.h>
#include <ArduinoJson.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include "Config.h"

// Максимальная длина команды. Самая длинная — конфигурация Wi-Fi из панели.
static constexpr size_t LINK_CMD_MAX = 512;

/**
 * Связь с сервером: Wi-Fi + WebSocket, а если сети нет — USB Serial.
 *
 * Транспорт выбирается сам: пока WebSocket жив, всё идёт по нему, иначе
 * по кабелю. Наружу это один вызов sendJson/sendAudio.
 *
 * Две вещи, которых не хватало прошлой версии:
 *
 *   1. Wi-Fi переподключается. Раньше флаг подключения выставлялся один раз
 *      в setup(): если роутер поднялся позже питомца, устройство навсегда
 *      оставалось на USB. Теперь состояние проверяется в цикле, а попытки
 *      повторяются с растущей паузой (5 → 60 с).
 *
 *   2. Команды исполняются в основном цикле. Раньше задача Serial дёргала
 *      анимацию, дисплей и NVS прямо из своего контекста — параллельно с
 *      задачей отрисовки. Теперь она только складывает разобранный кадр в
 *      очередь, а разбирает его основной цикл.
 */
class Link {
public:
    using CommandHandler = void (*)(const char* json);

    void begin(const char* ssid, const char* pass, const char* host, const char* hostname);
    void loop();

    void onCommand(CommandHandler handler) { _onCommand = handler; }

    void sendJson(const JsonDocument& doc);
    bool sendAudio(const uint8_t* pcm, size_t bytes);

    bool wifiConnected() const { return _wifiConnected; }
    bool wsConnected() const { return _wsConnected; }
    // Сервер считается живым, пока идёт трафик — по Wi-Fi или по кабелю.
    bool serverOnline() const { return _wsConnected || (millis() - _lastServerMs < 8000); }
    void noteServerSeen() { _lastServerMs = millis(); }

    const char* ssid() const;
    String ip() const;
    int rssi() const;

    // Обновление по воздуху. Включается, только если задан пароль:
    // открытый OTA в локальной сети — это чужая прошивка в вашем питомце.
    void enableOta(const char* password);

    void serialLoop();                                        // точка входа задачи чтения USB
    void handleWsEvent(int type, uint8_t* payload, size_t length);   // вызывается из обёртки

private:
    char _ssid[64] = "";
    char _pass[64] = "";
    char _host[64] = "";
    char _hostname[32] = "atom-pet";

    volatile bool _wifiConnected = false;
    volatile bool _wsConnected = false;
    bool _wsStarted = false;
    bool _otaStarted = false;

    uint32_t _lastServerMs = 0;
    uint32_t _nextWifiTry = 0;
    uint32_t _wifiBackoff = WIFI_RETRY_MIN_MS;
    uint32_t _wifiAttemptStarted = 0;
    bool     _wifiAttemptRunning = false;

    QueueHandle_t _commands = nullptr;
    CommandHandler _onCommand = nullptr;

    void updateWifi(uint32_t now);
    void drainCommands();
    void pushCommand(const char* json, size_t length);
    void writeFrame(uint8_t type, const uint8_t* data, size_t length);
};

extern Link netLink;
