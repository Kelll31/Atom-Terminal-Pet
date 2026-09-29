#pragma once
#include <M5Unified.h>

/**
 * Датчик света и приближения LTR-553ALS — он стоит на плате AtomS3R.
 *
 * Даёт две вещи, которых не хватало питомцу:
 *   1. Приближение руки — можно «погладить», не нажимая кнопку.
 *   2. Освещённость — экран сам приглушается в темноте и не слепит ночью.
 *
 * Порог приближения не фиксированный, а плавающий: датчик подстраивается под
 * собственный фон. С жёстким порогом корпус в чехле или отражение от стола
 * читались как поднесённая рука, а на ярком солнце рука не срабатывала вовсе.
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
    uint8_t  suggestedBrightness() const { return brightness; }   // 25..255

    // Что нашлось на внутренней шине I2C — строка вида "0x23,0x68".
    // Нужна, чтобы понимать, есть ли датчик на конкретной ревизии платы.
    const char* getBusReport() const { return busReport; }

private:
    static constexpr uint8_t ADDR = 0x23;

    bool available = false;
    uint16_t proximity = 0;
    uint16_t ambient = 0;
    float    baseline = 0.0f;     // фон датчика приближения
    float    smoothAmbient = 0.0f;
    int      stepIndex = 2;        // текущая ступень яркости
    uint8_t  brightness = 130;
    bool handNear = false;
    bool handWaveEvent = false;
    unsigned long lastRead = 0;
    unsigned long handSince = 0;
    char busReport[48] = "";

    void scanBus();
    void updateBrightness();
};

extern Sensors sensors;
