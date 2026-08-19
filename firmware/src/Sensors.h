#pragma once
#include <M5Unified.h>

/**
 * Датчик света и приближения LTR-553ALS — он стоит на плате AtomS3R.
 *
 * Даёт две вещи, которых не хватало питомцу:
 *   1. Приближение руки — можно «погладить», не нажимая кнопку.
 *   2. Освещённость — экран сам приглушается в темноте и не слепит ночью.
 *
 * Если датчика нет (AtomS3 без R или другая ревизия) — класс тихо отключается,
 * остальная прошивка работает как раньше.
 */
class Sensors {
public:
    void init();
    void update();

    bool isAvailable() const { return available; }

    // 0..2047, чем больше — тем ближе объект
    uint16_t getProximity() const { return proximity; }
    bool isHandNear() const { return handNear; }
    bool wasHandWaved();          // однократное событие «провели рукой»

    uint16_t getAmbientLight() const { return ambient; }
    uint8_t  suggestedBrightness() const;  // 20..255 по освещённости

private:
    static constexpr uint8_t ADDR = 0x23;

    bool available = false;
    uint16_t proximity = 0;
    uint16_t ambient = 0;
    bool handNear = false;
    bool handWaveEvent = false;
    unsigned long lastRead = 0;
    unsigned long handSince = 0;
};

extern Sensors sensors;
