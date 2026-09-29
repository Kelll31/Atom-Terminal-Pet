#pragma once
#include <M5Unified.h>

// Событие кнопки под экраном
enum class ButtonEvent {
    NONE,
    CLICK,        // короткое нажатие — погладить
    DOUBLE_CLICK, // сменить экран
    HOLD,         // удержание — вкл/выкл микрофон
    LONG_HOLD     // долгое удержание — экран состояния, ещё дольше — перезагрузка
};

/**
 * Кнопка и IMU: наклон, тряска, постукивание, переворот.
 *
 * Толчки считаются не по модулю ускорения, а по его переменной части: вектор
 * силы тяжести вычитается фильтром высоких частот. Раньше порог сравнивался с
 * полным модулем, поэтому наклон устройства читался как удар, а мягкое
 * покачивание на столе — как тряска.
 */
class Motion {
public:
    void begin();
    void update();   // вызывать из основного цикла

    ButtonEvent pollButton();

    float pitch() const { return _pitch; }
    float roll() const  { return _roll; }

    bool  isShaking() const { return _shaking; }
    int   shakeCount() const { return _shakeCount; }
    void  clearShake() { _shaking = false; _shakeCount = 0; }

    bool  wasTapped() const { return _tapped; }
    void  clearTap() { _tapped = false; }

    bool  isFaceDown() const { return _faceDown; }
    bool  isMoving() const { return _moving; }
    uint32_t lastMotionMs() const { return _lastMotionMs; }

    // Ориентация 0..3 по вектору силы тяжести. Меняется только при уверенном
    // наклоне и не дребезжит на границе — экран не мигает от вибрации стола.
    int  orientation() const { return _orientation; }
    bool orientationChanged();   // однократное событие

    bool isAvailable() const { return _available; }

private:
    bool  _available = false;
    bool  _seeded = false;        // первый замер задаёт вектор силы тяжести
    uint32_t _settleUntil = 0;    // пока фильтр сходится, толчки не считаем
    float _pitch = 0.0f, _roll = 0.0f;
    float _gravityX = 0.0f, _gravityY = 0.0f, _gravityZ = 1.0f;

    bool _shaking = false;
    bool _tapped = false;
    bool _faceDown = false;
    bool _moving = false;
    int  _shakeCount = 0;

    uint32_t _lastShakeMs = 0;
    uint32_t _lastImpactMs = 0;
    uint32_t _lastMotionMs = 0;
    uint32_t _lastUpdateMs = 0;

    int  _orientation = 0;
    int  _orientationCandidate = 0;
    uint32_t _orientationSince = 0;
    bool _orientationEvent = false;
};

extern Motion motion;
