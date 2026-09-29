#include "Sensors.h"
#include <math.h>

Sensors sensors;

// Регистры LTR-553ALS
static constexpr uint8_t REG_ALS_CONTR     = 0x80;
static constexpr uint8_t REG_PS_CONTR      = 0x81;
static constexpr uint8_t REG_PS_LED        = 0x82;
static constexpr uint8_t REG_PS_N_PULSES   = 0x83;
static constexpr uint8_t REG_PS_MEAS_RATE  = 0x84;
static constexpr uint8_t REG_ALS_MEAS_RATE = 0x85;
static constexpr uint8_t REG_PART_ID       = 0x86;
static constexpr uint8_t REG_ALS_DATA_CH1  = 0x88;
static constexpr uint8_t REG_PS_DATA       = 0x8D;

static constexpr uint32_t I2C_FREQ = 100000;

// Рука считается поднесённой, если сигнал поднялся на столько над фоном.
static constexpr float PROX_ENTER = 220.0f;
static constexpr float PROX_EXIT  = 120.0f;   // гистерезис: отпускаем позже

void Sensors::scanBus() {
    bool found[128] = {false};
    M5.In_I2C.scanID(found);

    busReport[0] = '\0';
    size_t used = 0;
    for (int address = 1; address < 127 && used < sizeof(busReport) - 6; address++) {
        if (!found[address]) continue;
        used += snprintf(busReport + used, sizeof(busReport) - used,
                         used ? ",0x%02X" : "0x%02X", address);
    }
    // Только ASCII: встроенный шрифт дисплея кириллицу не рисует,
    // а строка уходит и в панель, и на экран состояния.
    if (!busReport[0]) strncpy(busReport, "empty", sizeof(busReport) - 1);
}

void Sensors::init() {
    // Сначала смотрим, что вообще есть на шине: если датчика нет физически,
    // это сразу видно в панели, а не выглядит как «драйвер не работает».
    scanBus();

    uint8_t partId = 0;
    if (!M5.In_I2C.readRegister(ADDR, REG_PART_ID, &partId, 1, I2C_FREQ)) {
        available = false;
        return;
    }
    // Старшие 4 бита — номер части (0x9 у LTR-553)
    if ((partId >> 4) != 0x9) {
        available = false;
        return;
    }

    // Датчик просыпается ~100 мс, поэтому сначала будим, потом настраиваем
    M5.In_I2C.writeRegister8(ADDR, REG_ALS_CONTR, 0x01, I2C_FREQ);      // ALS active, gain x1
    delay(10);
    M5.In_I2C.writeRegister8(ADDR, REG_PS_LED, 0x7F, I2C_FREQ);          // 60 кГц, ток 100 мА
    M5.In_I2C.writeRegister8(ADDR, REG_PS_N_PULSES, 0x08, I2C_FREQ);     // 8 импульсов
    M5.In_I2C.writeRegister8(ADDR, REG_PS_MEAS_RATE, 0x02, I2C_FREQ);    // замер каждые 50 мс
    M5.In_I2C.writeRegister8(ADDR, REG_ALS_MEAS_RATE, 0x03, I2C_FREQ);   // 100 мс интеграция
    M5.In_I2C.writeRegister8(ADDR, REG_PS_CONTR, 0x03, I2C_FREQ);        // PS active

    available = true;
    baseline = -1.0f;   // фон возьмём с первого замера
}

void Sensors::update() {
    if (!available) return;

    unsigned long now = millis();
    if (now - lastRead < 100) return;
    lastRead = now;

    uint8_t psData[2] = {0, 0};
    if (M5.In_I2C.readRegister(ADDR, REG_PS_DATA, psData, 2, I2C_FREQ)) {
        proximity = (uint16_t)(((psData[1] & 0x07) << 8) | psData[0]);
    }

    uint8_t alsData[4] = {0, 0, 0, 0};
    if (M5.In_I2C.readRegister(ADDR, REG_ALS_DATA_CH1, alsData, 4, I2C_FREQ)) {
        uint16_t ch1 = (uint16_t)((alsData[1] << 8) | alsData[0]);
        uint16_t ch0 = (uint16_t)((alsData[3] << 8) | alsData[2]);
        ambient = ch0 > ch1 ? ch0 : ch1;
    }

    if (baseline < 0.0f) baseline = proximity;

    // Фон подтягивается только вниз и очень медленно: подъехавшая рука его
    // не «переучит», а вот новое место на столе датчик примет за минуту.
    if (proximity < baseline) baseline += (proximity - baseline) * 0.05f;
    else                      baseline += (proximity - baseline) * 0.002f;

    const float over = (float)proximity - baseline;
    const bool near = handNear ? (over > PROX_EXIT) : (over > PROX_ENTER);

    if (near && !handNear) {
        handSince = now;
    }
    // Рука подержалась и убралась — это «поглаживание». Слишком короткое
    // касание игнорируем (случайный блик), слишком долгое — это чехол.
    if (!near && handNear && now - handSince > 120 && now - handSince < 2500) {
        handWaveEvent = true;
    }
    handNear = near;

    updateBrightness();
}

bool Sensors::wasHandWaved() {
    if (!handWaveEvent) return false;
    handWaveEvent = false;
    return true;
}

// Яркость идёт ступенями, и переход между ними — с перекрытием: вверх шагаем,
// когда света стало на 20% больше порога, вниз — когда на 20% меньше. Без этого
// в сумерках, ровно на границе, подсветка прыгала между двумя уровнями.
void Sensors::updateBrightness() {
    smoothAmbient += ((float)ambient - smoothAmbient) * 0.15f;

    struct Step { float enter; uint8_t value; };
    static const Step STEPS[] = {
        {    0.0f,  25},   // ночь
        {   20.0f,  70},
        {  120.0f, 130},
        {  600.0f, 190},
        { 2000.0f, 255},   // яркий свет / солнце
    };
    constexpr int COUNT = (int)(sizeof(STEPS) / sizeof(STEPS[0]));

    if (stepIndex < COUNT - 1 && smoothAmbient > STEPS[stepIndex + 1].enter * 1.2f) {
        stepIndex++;
    } else if (stepIndex > 0 && smoothAmbient < STEPS[stepIndex].enter * 0.8f) {
        stepIndex--;
    }

    brightness = STEPS[stepIndex].value;
}
