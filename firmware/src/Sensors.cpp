#include "Sensors.h"

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

void Sensors::init() {
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

    // Порог подобран так, чтобы срабатывала ладонь в 3-5 см, а не стол на 20 см
    bool near = proximity > 400;
    if (near && !handNear) {
        handSince = now;
    }
    if (!near && handNear && now - handSince > 120 && now - handSince < 2500) {
        handWaveEvent = true;  // рука подержалась и убралась — это «поглаживание»
    }
    handNear = near;
}

bool Sensors::wasHandWaved() {
    if (!handWaveEvent) return false;
    handWaveEvent = false;
    return true;
}

uint8_t Sensors::suggestedBrightness() const {
    if (!available) return 110;
    if (ambient < 20)   return 30;    // ночь
    if (ambient < 120)  return 70;
    if (ambient < 600)  return 130;
    if (ambient < 2000) return 190;
    return 255;                       // яркий свет / солнце
}
