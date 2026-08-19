#pragma once
#include <M5Unified.h>
#include "PetState.h"

/**
 * Отрисовка Патрика на экране 128x128.
 *
 * Силуэт строится по строкам (scanline): для каждой строки считается полуширина
 * тела, поэтому форма получается гладкой, без «швов» от наложенных эллипсов.
 * Поверх кладутся тень, светлая грань и тёмный контур — на маленьком экране
 * мультяшка читается только с контуром.
 *
 * Мимика описывается структурой FacePose: аниматор задаёт целевую позу,
 * плавно к ней подъезжает и отдаёт сюда уже сглаженные значения.
 */

struct FacePose {
    float eyeOpen    = 1.0f;   // 0 — закрыты, 1 — норма, >1 — выпучены
    float eyeSquint  = 0.0f;   // нижнее веко (прищур улыбки)
    float browAngle  = 0.0f;   // -1 злой домиком вниз, +1 грустный домиком вверх
    float browRaise  = 0.0f;   // подъём бровей в пикселях
    float mouthOpen  = 0.35f;  // 0 — закрыт, 1 — распахнут
    float mouthWidth = 0.5f;   // 0..1
    float mouthCurve = 0.0f;   // -1 уголки вниз, +1 улыбка
    float lookX      = 0.0f;   // смещение зрачков, px
    float lookY      = 0.0f;
    float lean       = 0.0f;   // наклон тела, px на верхушке
    float squash     = 0.0f;   // -1 сплющен, +1 вытянут
    float bob        = 0.0f;   // смещение по вертикали, px
    float blush      = 0.0f;   // 0..1
    float drool      = 0.0f;   // 0..1 длина слюнки
    float armSwing   = 0.0f;   // -1..1 взмах руками
};

class PetFace {
public:
    // Полная отрисовка кадра: фон, тело, лицо, эффекты эмоции.
    static void draw(M5Canvas& canvas, const FacePose& pose, PetEmotion emotion, uint32_t now);

    // Палитра — нужна и другим экранам (HUD, всплывающие подсказки).
    static uint16_t skin(M5Canvas& canvas);
    static uint16_t outline(M5Canvas& canvas);
    static uint16_t accent(M5Canvas& canvas, PetEmotion emotion);

private:
    static void buildSilhouette(const FacePose& pose, int16_t* halfWidth, int16_t* centerX);
    static void drawBackground(M5Canvas& canvas, PetEmotion emotion, uint32_t now);
    static void drawBody(M5Canvas& canvas, const FacePose& pose, const int16_t* halfWidth, const int16_t* centerX);
    static void drawArms(M5Canvas& canvas, const FacePose& pose, const int16_t* halfWidth, const int16_t* centerX);
    static void drawShorts(M5Canvas& canvas, const int16_t* halfWidth, const int16_t* centerX);
    static void drawEyes(M5Canvas& canvas, const FacePose& pose, PetEmotion emotion, uint32_t now);
    static void drawBrows(M5Canvas& canvas, const FacePose& pose);
    static void drawMouth(M5Canvas& canvas, const FacePose& pose, PetEmotion emotion, uint32_t now);
    static void drawExtras(M5Canvas& canvas, const FacePose& pose, PetEmotion emotion, uint32_t now);
};
