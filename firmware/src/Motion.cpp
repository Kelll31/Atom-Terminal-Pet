#include "Motion.h"
#include <math.h>

Motion motion;

// Порог удара по переменной части ускорения (g). Ладонь по корпусу даёт ~0.6,
// перекладывание со стола на стол — около 0.2.
static constexpr float TAP_THRESHOLD   = 0.55f;
static constexpr float SHAKE_THRESHOLD = 1.10f;
static constexpr float MOVE_THRESHOLD  = 0.05f;

// Между двумя засчитанными толчками должен пройти хотя бы этот интервал,
// иначе один взмах считался за пять.
static constexpr uint32_t IMPACT_DEBOUNCE_MS = 220;
static constexpr uint32_t SHAKE_WINDOW_MS    = 2500;

// Ориентация должна продержаться столько, чтобы её признали новой.
static constexpr uint32_t ORIENTATION_HOLD_MS = 600;
static constexpr float ORIENTATION_ENTER = 0.70f;   // войти в новую ориентацию
static constexpr float ORIENTATION_EXIT  = 0.50f;   // выйти из текущей

void Motion::begin() {
    // M5.begin() уже поднимает IMU на большинстве плат — повторно не дёргаем.
    _available = M5.Imu.isEnabled() || M5.Imu.begin();
    M5.BtnA.setHoldThresh(700);
    _lastMotionMs = millis();
    _lastUpdateMs = millis();
}

void Motion::update() {
    if (!_available || !M5.Imu.update()) return;

    float ax = 0, ay = 0, az = 0;
    M5.Imu.getAccel(&ax, &ay, &az);

    const uint32_t now = millis();

    // Первый замер принимаем за силу тяжести целиком. Если этого не делать,
    // фильтр стартует с «экраном вверх», и питомец, включённый в вертикальной
    // подставке, на первой же секунде считает себя встряхнутым.
    if (!_seeded) {
        _seeded = true;
        _gravityX = ax;
        _gravityY = ay;
        _gravityZ = az;
        _settleUntil = now + 800;
        _lastUpdateMs = now;
        return;
    }

    // Постоянная времени фильтра ~0.35 с: сила тяжести проходит, удары — нет.
    const float dt = (float)(now - _lastUpdateMs) * 0.001f;
    _lastUpdateMs = now;
    const float alpha = fminf(1.0f, dt / 0.35f);

    _gravityX += (ax - _gravityX) * alpha;
    _gravityY += (ay - _gravityY) * alpha;
    _gravityZ += (az - _gravityZ) * alpha;

    // Переменная часть — то, что осталось после вычитания силы тяжести
    const float dx = ax - _gravityX;
    const float dy = ay - _gravityY;
    const float dz = az - _gravityZ;
    const float impact = sqrtf(dx * dx + dy * dy + dz * dz);

    _pitch = atan2f(-_gravityX, sqrtf(_gravityY * _gravityY + _gravityZ * _gravityZ)) * 180.0f / (float)PI;
    _roll  = atan2f(_gravityY, _gravityZ) * 180.0f / (float)PI;

    _moving = impact > MOVE_THRESHOLD;
    if (_moving) _lastMotionMs = now;

    _faceDown = (_gravityZ < -0.75f);

    if (now > _settleUntil && impact > TAP_THRESHOLD && now - _lastImpactMs > IMPACT_DEBOUNCE_MS) {
        _lastImpactMs = now;
        if (impact > SHAKE_THRESHOLD) {
            _shakeCount++;
            _lastShakeMs = now;
            _shaking = true;
        } else {
            _tapped = true;
        }
    }

    if (_shaking && now - _lastShakeMs > SHAKE_WINDOW_MS) {
        _shaking = false;
        _shakeCount = 0;
    }

    // ── Ориентация с гистерезисом ──────────────────────────────────────────
    int candidate = _orientation;
    if (_gravityY > ORIENTATION_ENTER)       candidate = 0;
    else if (_gravityY < -ORIENTATION_ENTER) candidate = 2;
    else if (_gravityX > ORIENTATION_ENTER)  candidate = 1;
    else if (_gravityX < -ORIENTATION_ENTER) candidate = 3;
    else {
        // Ни одна ось не доминирует — держим прежнюю ориентацию,
        // пока текущая не потеряет опору окончательно.
        const float axis = (_orientation == 0 || _orientation == 2) ? fabsf(_gravityY) : fabsf(_gravityX);
        if (axis > ORIENTATION_EXIT) candidate = _orientation;
    }

    if (candidate != _orientationCandidate) {
        _orientationCandidate = candidate;
        _orientationSince = now;
    } else if (candidate != _orientation && now - _orientationSince > ORIENTATION_HOLD_MS) {
        _orientation = candidate;
        _orientationEvent = true;
    }
}

bool Motion::orientationChanged() {
    if (!_orientationEvent) return false;
    _orientationEvent = false;
    return true;
}

ButtonEvent Motion::pollButton() {
    if (M5.BtnA.pressedFor(3000))   return ButtonEvent::LONG_HOLD;
    if (M5.BtnA.wasHold())          return ButtonEvent::HOLD;
    if (M5.BtnA.wasDoubleClicked()) return ButtonEvent::DOUBLE_CLICK;
    if (M5.BtnA.wasSingleClicked()) return ButtonEvent::CLICK;
    return ButtonEvent::NONE;
}
