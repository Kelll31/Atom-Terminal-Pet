#include "Link.h"

#include <WiFi.h>
#include <WebSocketsClient.h>
#ifdef ENABLE_OTA
#include <ArduinoOTA.h>
#endif

#include "AudioIO.h"

Link netLink;

static WebSocketsClient webSocket;

static void wsEventBridge(WStype_t type, uint8_t* payload, size_t length) {
    netLink.handleWsEvent((int)type, payload, length);
}

static void serialTaskEntry(void*) { netLink.serialLoop(); }

// ── Запуск ──────────────────────────────────────────────────────────────────
void Link::begin(const char* ssid, const char* pass, const char* host, const char* hostname) {
    strncpy(_ssid, ssid ? ssid : "", sizeof(_ssid) - 1);
    strncpy(_pass, pass ? pass : "", sizeof(_pass) - 1);
    strncpy(_host, host ? host : "", sizeof(_host) - 1);
    if (hostname && hostname[0]) strncpy(_hostname, hostname, sizeof(_hostname) - 1);

    _commands = xQueueCreate(4, LINK_CMD_MAX);

    // Приёмный буфер USB обязан быть большим: сервер шлёт звук кусками по 4 КБ,
    // а в буфер по умолчанию (256 байт) они не влезают и речь рвётся.
    // Порядок важен — после Serial.begin() размер уже не изменить, поэтому
    // M5.begin() поднимает порт с baudrate=0 и не трогает его.
    Serial.setRxBufferSize(SERIAL_RX_BUFFER);
    Serial.setTxBufferSize(SERIAL_TX_BUFFER);
    Serial.begin(SERIAL_BAUD);
    // Если сервер не запущен, хост не разбирает USB-буфер. Без короткого
    // таймаута отправка кадра микрофона вешала основной цикл на сотни миллисекунд.
    Serial.setTxTimeoutMs(30);

    xTaskCreatePinnedToCore(serialTaskEntry, "serial", STACK_SERIAL, nullptr, PRIO_SERIAL, nullptr, 1);

    if (_ssid[0]) {
        WiFi.persistent(false);
        WiFi.mode(WIFI_STA);
        WiFi.setHostname(_hostname);
        // Переподключением занимаемся сами (updateWifi): встроенный автоповтор
        // одновременно с нашими попытками дёргал драйвер и удлинял простой.
        WiFi.setAutoReconnect(false);
        // Сон Wi-Fi добавляет к аудиопотоку десятки миллисекунд задержки.
        WiFi.setSleep(false);
        _nextWifiTry = 0;   // подключаемся при первом же проходе цикла
    }
}

void Link::enableOta(const char* password) {
#ifdef ENABLE_OTA
    if (_otaStarted || !password || !password[0]) return;
    ArduinoOTA.setHostname(_hostname);
    ArduinoOTA.setPassword(password);
    ArduinoOTA.onStart([]() { audioIO.stopPlayback(); });
    ArduinoOTA.begin();
    _otaStarted = true;
#else
    (void)password;
#endif
}

// ── Wi-Fi ───────────────────────────────────────────────────────────────────
void Link::updateWifi(uint32_t now) {
    if (!_ssid[0]) return;

    const bool up = WiFi.status() == WL_CONNECTED;
    if (up != _wifiConnected) {
        _wifiConnected = up;
        if (up) {
            _wifiBackoff = WIFI_RETRY_MIN_MS;
            _wifiAttemptRunning = false;
            if (!_wsStarted && _host[0]) {
                webSocket.begin(_host, WS_PORT, WS_PATH);
                webSocket.onEvent(wsEventBridge);
                webSocket.setReconnectInterval(4000);
                webSocket.enableHeartbeat(15000, 3000, 2);
                _wsStarted = true;
            }
        } else if (_wsStarted) {
            // Пока сети нет, клиент WebSocket трогать нельзя: каждая его
            // попытка соединиться — это блокирующий TCP-connect в основном
            // цикле, из-за которого копились и терялись кадры микрофона.
            webSocket.disconnect();
            _wsConnected = false;
        }
    }

    if (up) return;

    // Попытка подключения не должна висеть вечно: если за 15 секунд не вышло,
    // обрываем и ждём — иначе драйвер держит канал и мешает следующей попытке.
    if (_wifiAttemptRunning && now - _wifiAttemptStarted > 15000) {
        _wifiAttemptRunning = false;
        WiFi.disconnect(false, false);
        _nextWifiTry = now + _wifiBackoff;
        _wifiBackoff = _wifiBackoff * 2 > WIFI_RETRY_MAX_MS ? WIFI_RETRY_MAX_MS : _wifiBackoff * 2;
        return;
    }

    if (!_wifiAttemptRunning && now >= _nextWifiTry) {
        _wifiAttemptRunning = true;
        _wifiAttemptStarted = now;
        WiFi.begin(_ssid, _pass);
    }
}

// ── WebSocket ───────────────────────────────────────────────────────────────
void Link::handleWsEvent(int type, uint8_t* payload, size_t length) {
    switch (type) {
        case WStype_DISCONNECTED:
            _wsConnected = false;
            break;

        case WStype_CONNECTED:
            _wsConnected = true;
            _lastServerMs = millis();
            break;

        case WStype_TEXT:
            _lastServerMs = millis();
            pushCommand((const char*)payload, length);
            break;

        case WStype_BIN:
            _lastServerMs = millis();
            audioIO.enqueue(payload, length);
            break;

        default:
            break;
    }
}

// ── Основной цикл ───────────────────────────────────────────────────────────
void Link::loop() {
    const uint32_t now = millis();

    static uint32_t lastWifiCheck = 0;
    if (now - lastWifiCheck > 500) {
        lastWifiCheck = now;
        updateWifi(now);
    }

    if (_wsStarted && _wifiConnected) webSocket.loop();

#ifdef ENABLE_OTA
    if (_otaStarted && _wifiConnected) ArduinoOTA.handle();
#endif

    drainCommands();
}

void Link::pushCommand(const char* json, size_t length) {
    if (!_commands || !json || length == 0 || length >= LINK_CMD_MAX) return;
    char slot[LINK_CMD_MAX];
    memcpy(slot, json, length);
    slot[length] = '\0';
    xQueueSend(_commands, slot, 0);
}

void Link::drainCommands() {
    if (!_commands || !_onCommand) return;
    char slot[LINK_CMD_MAX];
    while (xQueueReceive(_commands, slot, 0) == pdTRUE) {
        _lastServerMs = millis();
        _onCommand(slot);
    }
}

// ── Отправка ────────────────────────────────────────────────────────────────
void Link::writeFrame(uint8_t type, const uint8_t* data, size_t length) {
    const uint8_t header[7] = {
        0xAA, 0xBB, type,
        (uint8_t)(length & 0xFF), (uint8_t)((length >> 8) & 0xFF),
        (uint8_t)((length >> 16) & 0xFF), (uint8_t)((length >> 24) & 0xFF)
    };
    Serial.write(header, sizeof(header));
    Serial.write(data, length);
}

void Link::sendJson(const JsonDocument& doc) {
    String payload;
    serializeJson(doc, payload);
    if (_wsConnected) {
        webSocket.sendTXT(payload);
    } else {
        writeFrame(0x01, (const uint8_t*)payload.c_str(), payload.length());
    }
}

bool Link::sendAudio(const uint8_t* pcm, size_t bytes) {
    if (!pcm || bytes == 0) return false;
    if (_wsConnected) return webSocket.sendBIN((uint8_t*)pcm, bytes);
    writeFrame(0x02, pcm, bytes);
    return true;
}

const char* Link::ssid() const { return _ssid; }
String Link::ip() const { return _wifiConnected ? WiFi.localIP().toString() : String("usb"); }
int Link::rssi() const { return _wifiConnected ? WiFi.RSSI() : 0; }

// ── Чтение USB ──────────────────────────────────────────────────────────────
// Задача только разбирает кадры: звук уходит прямо в кольцевой буфер (он
// потокобезопасен), а команды складываются в очередь для основного цикла.
void Link::serialLoop() {
    enum State { WAIT_AA, WAIT_BB, READ_TYPE, READ_LEN, READ_PAYLOAD, READ_TEXT };
    static uint8_t payload[SERIAL_MAX_PAYLOAD];

    static char text[LINK_CMD_MAX];   // не на стеке: рядом лежит буфер pushCommand

    State state = WAIT_AA;
    uint8_t msgType = 0;
    uint32_t msgLength = 0;
    uint32_t received = 0;
    uint32_t lenBytes = 0;
    size_t textLength = 0;

    while (true) {
        if (!Serial.available()) {
            vTaskDelay(pdMS_TO_TICKS(2));
            continue;
        }

        // Ограничиваем размер порции: при непрерывном потоке задача с
        // приоритетом выше основного цикла иначе не отдаёт процессор совсем.
        int budget = 4096;
        while (Serial.available() && budget > 0) {
            switch (state) {
                case WAIT_AA: {
                    const int b = Serial.read();
                    budget--;
                    if (b == 0xAA) state = WAIT_BB;
                    else if (b == '{') { text[0] = '{'; textLength = 1; state = READ_TEXT; }
                    break;
                }

                case WAIT_BB:
                    state = (Serial.read() == 0xBB) ? READ_TYPE : WAIT_AA;
                    budget--;
                    break;

                case READ_TYPE:
                    msgType = (uint8_t)Serial.read();
                    budget--;
                    msgLength = 0;
                    lenBytes = 0;
                    received = 0;
                    state = READ_LEN;
                    break;

                case READ_LEN:
                    msgLength |= ((uint32_t)Serial.read()) << (lenBytes * 8);
                    budget--;
                    if (++lenBytes == 4) {
                        state = (msgLength > 0 && msgLength <= SERIAL_MAX_PAYLOAD) ? READ_PAYLOAD : WAIT_AA;
                    }
                    break;

                case READ_PAYLOAD: {
                    const size_t want = msgLength - received;
                    const size_t avail = (size_t)Serial.available();
                    const size_t take = avail < want ? avail : want;
                    const size_t got = Serial.readBytes(&payload[received], take);
                    received += got;
                    budget -= (int)got;

                    if (received >= msgLength) {
                        if (msgType == 0x01) {
                            pushCommand((const char*)payload, msgLength);
                        } else if (msgType == 0x02) {
                            _lastServerMs = millis();
                            audioIO.enqueue(payload, msgLength);
                        }
                        state = WAIT_AA;
                    }
                    break;
                }

                case READ_TEXT: {
                    const char c = (char)Serial.read();
                    budget--;
                    if (c == '\n' || c == '\r') {
                        if (textLength > 1) {
                            text[textLength] = '\0';
                            pushCommand(text, textLength);
                        }
                        textLength = 0;
                        state = WAIT_AA;
                    } else if (textLength < sizeof(text) - 1) {
                        text[textLength++] = c;
                    } else {
                        textLength = 0;
                        state = WAIT_AA;   // строка длиннее буфера — кадр битый
                    }
                    break;
                }
            }
        }

        // Обязательная уступка процессора. Запаса хватает с избытком: 4 КБ за
        // миллисекунду — это на два порядка больше, чем шлёт сервер.
        vTaskDelay(1);
    }
}
