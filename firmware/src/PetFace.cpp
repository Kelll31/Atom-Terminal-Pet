#include "PetFace.h"
#include <math.h>

// ── Пропорции ───────────────────────────────────────────────────────────────
static constexpr int   SCREEN   = 128;
static constexpr int   TOP_Y    = 12;    // макушка
static constexpr int   BASE_Y   = 128;   // низ экрана
static constexpr float MAX_HALF = 72.0f; // полуширина у основания (шире экрана — тело обрезается краями)
static constexpr int   TIP_R    = 16;    // радиус скругления макушки

static constexpr int EYE_Y   = 58;
static constexpr int EYE_DX  = 15;   // половина расстояния между зрачками
static constexpr int EYE_R   = 16;
static constexpr int MOUTH_Y = 96;

// ── Палитра ─────────────────────────────────────────────────────────────────
#define C_SKIN      canvas.color565(250, 146, 166)
#define C_SKIN_LIT  canvas.color565(255, 192, 204)
#define C_SKIN_SHD  canvas.color565(206, 100, 126)
#define C_OUTLINE   canvas.color565(58, 24, 34)
#define C_MOUTH     canvas.color565(96, 26, 40)
#define C_MOUTH_LIT canvas.color565(132, 40, 56)
#define C_TONGUE    canvas.color565(238, 112, 134)
#define C_PANTS     canvas.color565(104, 194, 60)
#define C_PANTS_SHD canvas.color565(74, 148, 42)
#define C_FLOWER    canvas.color565(150, 62, 200)
#define C_DROOL     canvas.color565(196, 234, 255)
#define C_WHITE     canvas.color565(255, 253, 250)
#define C_PUPIL     canvas.color565(30, 18, 22)

static inline float clampf(float v, float lo, float hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}

uint16_t PetFace::skin(M5Canvas& canvas)    { return C_SKIN; }
uint16_t PetFace::outline(M5Canvas& canvas) { return C_OUTLINE; }

uint16_t PetFace::accent(M5Canvas& canvas, PetEmotion emotion) {
    switch (emotion) {
        case PetEmotion::ANGRY:   return canvas.color565(255, 70, 80);
        case PetEmotion::PANIC:   return canvas.color565(255, 140, 40);
        case PetEmotion::SWEAT:   return canvas.color565(255, 190, 40);
        case PetEmotion::SAD:     return canvas.color565(90, 160, 255);
        case PetEmotion::LOVE:    return canvas.color565(255, 90, 160);
        case PetEmotion::PARTY:   return canvas.color565(255, 120, 200);
        case PetEmotion::WORKING: return canvas.color565(60, 220, 160);
        case PetEmotion::THINKING:return canvas.color565(160, 140, 255);
        case PetEmotion::LISTENING:return canvas.color565(40, 210, 240);
        case PetEmotion::SLEEPING:return canvas.color565(130, 130, 255);
        default:                  return canvas.color565(255, 170, 190);
    }
}

// ── Силуэт ──────────────────────────────────────────────────────────────────
// Для каждой строки экрана считаем полуширину тела и смещение центра.
// halfWidth[y] < 0 означает «тела в этой строке нет».
void PetFace::buildSilhouette(const FacePose& pose, int16_t* halfWidth, int16_t* centerX) {
    const float squash  = clampf(pose.squash, -0.35f, 0.35f);
    const float topY    = TOP_Y - squash * 10.0f + pose.bob;
    const float baseY   = BASE_Y + pose.bob;
    const float height  = baseY - topY;
    const float maxHalf = MAX_HALF * (1.0f - squash * 0.35f);

    for (int y = 0; y < SCREEN; y++) {
        float local = y - topY;
        if (local < 0 || height <= 1.0f) {
            halfWidth[y] = -1;
            centerX[y] = 64;
            continue;
        }

        float t = clampf(local / height, 0.0f, 1.0f);
        float w = maxHalf * powf(t, 0.62f);

        // Скруглённая макушка
        if (local < TIP_R) {
            float dy = TIP_R - local;
            float circle = sqrtf(fmaxf(0.0f, (float)TIP_R * TIP_R - dy * dy));
            if (circle > w) w = circle;
        }

        halfWidth[y] = (int16_t)(w + 0.5f);
        // Верхушка наклоняется сильнее основания — тело «ведёт» при движении
        centerX[y] = (int16_t)(64.0f + pose.lean * powf(1.0f - t, 1.6f) + 0.5f);
    }
}

// ── Фон ─────────────────────────────────────────────────────────────────────
void PetFace::drawBackground(M5Canvas& canvas, PetEmotion emotion, uint32_t now) {
    uint16_t top, bottom;

    switch (emotion) {
        case PetEmotion::PANIC:
        case PetEmotion::ANGRY: {
            uint8_t pulse = (uint8_t)((sinf(now * 0.006f) + 1.0f) * 18);
            top    = canvas.color565(60 + pulse, 8, 16);
            bottom = canvas.color565(16, 2, 6);
            break;
        }
        case PetEmotion::SWEAT:
            top = canvas.color565(70, 46, 6); bottom = canvas.color565(18, 10, 2); break;
        case PetEmotion::SAD:
            top = canvas.color565(10, 22, 54); bottom = canvas.color565(3, 6, 20); break;
        case PetEmotion::LOVE:
            top = canvas.color565(60, 10, 40); bottom = canvas.color565(16, 2, 12); break;
        case PetEmotion::SLEEPING:
            top = canvas.color565(14, 10, 46); bottom = canvas.color565(2, 2, 12); break;
        case PetEmotion::WORKING:
            top = canvas.color565(4, 44, 34); bottom = canvas.color565(2, 12, 12); break;
        case PetEmotion::THINKING:
            top = canvas.color565(24, 14, 60); bottom = canvas.color565(6, 4, 18); break;
        case PetEmotion::LISTENING:
            top = canvas.color565(4, 44, 56); bottom = canvas.color565(2, 12, 18); break;
        case PetEmotion::PARTY: {
            float t = now * 0.004f;
            top = canvas.color565((uint8_t)((sinf(t) + 1) * 60),
                                  (uint8_t)((sinf(t + 2.09f) + 1) * 60),
                                  (uint8_t)((sinf(t + 4.19f) + 1) * 60));
            bottom = canvas.color565(10, 4, 16);
            break;
        }
        case PetEmotion::HAPPY:
            top = canvas.color565(56, 40, 8); bottom = canvas.color565(14, 10, 2); break;
        default:
            top = canvas.color565(10, 16, 30); bottom = canvas.color565(2, 4, 10); break;
    }

    canvas.fillSprite(bottom);
    for (int y = 0; y < 96; y++) {
        // Плавный градиент сверху вниз (простое смешивание двух цветов)
        float k = 1.0f - (float)y / 96.0f;
        uint8_t r = (uint8_t)(((top >> 11) & 0x1F) * k + ((bottom >> 11) & 0x1F) * (1 - k));
        uint8_t g = (uint8_t)(((top >> 5) & 0x3F) * k + ((bottom >> 5) & 0x3F) * (1 - k));
        uint8_t b = (uint8_t)((top & 0x1F) * k + (bottom & 0x1F) * (1 - k));
        canvas.drawFastHLine(0, y, SCREEN, (uint16_t)((r << 11) | (g << 5) | b));
    }

    if (emotion == PetEmotion::WORKING || emotion == PetEmotion::THINKING) {
        uint16_t line = canvas.color565(0, 40, 60);
        for (int y = (int)((now / 60) % 6); y < SCREEN; y += 6) {
            canvas.drawFastHLine(0, y, SCREEN, line);
        }
    }
}

// ── Тело ────────────────────────────────────────────────────────────────────
void PetFace::drawBody(M5Canvas& canvas, const FacePose& pose, const int16_t* halfWidth, const int16_t* centerX) {
    // 1. Контур: тот же силуэт, но на 2 px шире
    int firstRow = -1;
    for (int y = 0; y < SCREEN; y++) {
        if (halfWidth[y] < 0) continue;
        if (firstRow < 0) firstRow = y;
        int w = halfWidth[y] + 2;
        canvas.drawFastHLine(centerX[y] - w, y, w * 2, C_OUTLINE);
    }
    // Шапочка контура над макушкой
    if (firstRow > 1) {
        canvas.fillSmoothCircle(centerX[firstRow], firstRow + 1, 3, C_OUTLINE);
    }

    // 2. Заливка тела с объёмом
    for (int y = 0; y < SCREEN; y++) {
        int w = halfWidth[y];
        if (w <= 0) continue;
        int cx = centerX[y];
        int left = cx - w;

        canvas.drawFastHLine(left, y, w * 2, C_SKIN);

        int shade = w / 4;
        if (shade > 2) {
            canvas.drawFastHLine(cx + w - shade, y, shade, C_SKIN_SHD);
        }
        if (y < 92) {
            int lit = w / 3;
            if (lit > 2) canvas.drawFastHLine(left + 2, y, lit, C_SKIN_LIT);
        }
    }

    // 3. Пятнышки морской звезды
    canvas.fillSmoothCircle(centerX[40] - 20, 40, 3, C_SKIN_SHD);
    canvas.fillSmoothCircle(centerX[30] + 14, 30, 2, C_SKIN_SHD);
    canvas.fillSmoothCircle(centerX[76] - 40, 76, 4, C_SKIN_SHD);
    canvas.fillSmoothCircle(centerX[84] + 44, 84, 3, C_SKIN_SHD);
}

// ── Руки ────────────────────────────────────────────────────────────────────
void PetFace::drawArms(M5Canvas& canvas, const FacePose& pose, const int16_t* halfWidth, const int16_t* centerX) {
    const int y = 104;
    int w = halfWidth[y];
    if (w <= 0) return;

    int swing = (int)(pose.armSwing * 7.0f);
    int leftX  = centerX[y] - w - 2;
    int rightX = centerX[y] + w + 2;

    canvas.fillSmoothCircle(leftX,  y - swing, 13, C_OUTLINE);
    canvas.fillSmoothCircle(rightX, y + swing, 13, C_OUTLINE);
    canvas.fillSmoothCircle(leftX,  y - swing, 11, C_SKIN);
    canvas.fillSmoothCircle(rightX, y + swing, 11, C_SKIN_SHD);
}

// ── Шорты ───────────────────────────────────────────────────────────────────
void PetFace::drawShorts(M5Canvas& canvas, const int16_t* halfWidth, const int16_t* centerX) {
    const int waistY = 112;
    for (int y = waistY; y < SCREEN; y++) {
        int w = halfWidth[y];
        if (w <= 0) continue;
        int cx = centerX[y];
        canvas.drawFastHLine(cx - w, y, w * 2, y < waistY + 3 ? C_PANTS_SHD : C_PANTS);
        canvas.drawFastHLine(cx + w - 4, y, 4, C_PANTS_SHD);
        canvas.drawFastHLine(cx - w, y, 2, C_OUTLINE);
        canvas.drawFastHLine(cx + w - 2, y, 2, C_OUTLINE);
    }
    canvas.drawFastHLine(centerX[waistY] - halfWidth[waistY], waistY, halfWidth[waistY] * 2, C_OUTLINE);

    // Фиолетовые цветочки
    canvas.fillSmoothCircle(centerX[120] - 34, 121, 6, C_FLOWER);
    canvas.fillSmoothCircle(centerX[120],      124, 7, C_FLOWER);
    canvas.fillSmoothCircle(centerX[120] + 34, 120, 6, C_FLOWER);
}

// ── Брови ───────────────────────────────────────────────────────────────────
void PetFace::drawBrows(M5Canvas& canvas, const FacePose& pose) {
    const int browY = EYE_Y - EYE_R - 6 - (int)pose.browRaise;
    const int tilt  = (int)(pose.browAngle * 7.0f);
    const int halfLen = 13;

    int lx = 64 - EYE_DX - EYE_R / 2;
    int rx = 64 + EYE_DX + EYE_R / 2;

    canvas.drawWideLine(lx - halfLen, browY + tilt, lx + halfLen, browY - tilt, 2.6f, C_OUTLINE);
    canvas.drawWideLine(rx - halfLen, browY - tilt, rx + halfLen, browY + tilt, 2.6f, C_OUTLINE);
}

// ── Глаза ───────────────────────────────────────────────────────────────────
void PetFace::drawEyes(M5Canvas& canvas, const FacePose& pose, PetEmotion emotion, uint32_t now) {
    const int lx = 64 - EYE_DX - EYE_R / 2;
    const int rx = 64 + EYE_DX + EYE_R / 2;
    const int cy = EYE_Y;

    // Сон — закрытые дуги
    if (emotion == PetEmotion::SLEEPING || pose.eyeOpen < 0.08f) {
        canvas.drawWideLine(lx - 12, cy, lx, cy + 6, 2.4f, C_OUTLINE);
        canvas.drawWideLine(lx, cy + 6, lx + 12, cy, 2.4f, C_OUTLINE);
        canvas.drawWideLine(rx - 12, cy, rx, cy + 6, 2.4f, C_OUTLINE);
        canvas.drawWideLine(rx, cy + 6, rx + 12, cy, 2.4f, C_OUTLINE);
        return;
    }

    // Влюблённость — сердечки вместо глаз
    if (emotion == PetEmotion::LOVE) {
        float pulse = 1.0f + sinf(now * 0.006f) * 0.12f;
        for (int i = 0; i < 2; i++) {
            int cx = (i == 0) ? lx : rx;
            int r = (int)(7 * pulse);
            uint16_t heart = canvas.color565(255, 60, 120);
            canvas.fillSmoothCircle(cx - r / 2, cy - r / 2, r, heart);
            canvas.fillSmoothCircle(cx + r / 2, cy - r / 2, r, heart);
            canvas.fillTriangle(cx - r - r / 2 + 1, cy, cx + r + r / 2 - 1, cy, cx, cy + r * 2, heart);
            canvas.fillSmoothCircle(cx - r / 2, cy - r, 2, C_WHITE);
        }
        return;
    }

    const float open = clampf(pose.eyeOpen, 0.08f, 1.35f);
    const int rx_ = EYE_R;
    const int ry_ = (int)(EYE_R * open);

    for (int i = 0; i < 2; i++) {
        int cx = (i == 0) ? lx : rx;

        // Белок с контуром
        canvas.fillEllipse(cx, cy, rx_ + 2, ry_ + 2, C_OUTLINE);
        canvas.fillEllipse(cx, cy, rx_, ry_, C_WHITE);

        if (emotion == PetEmotion::DIZZY) {
            // Кружащиеся крестики
            float a = now * 0.008f + i * 3.14f;
            for (int k = 0; k < 2; k++) {
                float ang = a + k * 1.57f;
                canvas.drawWideLine(cx - (int)(cosf(ang) * rx_ * 0.8f), cy - (int)(sinf(ang) * ry_ * 0.8f),
                                    cx + (int)(cosf(ang) * rx_ * 0.8f), cy + (int)(sinf(ang) * ry_ * 0.8f),
                                    2.0f, C_PUPIL);
            }
            continue;
        }

        // Зрачок: смотрит по lookX/lookY, слегка сведён к центру (фирменный «дурашливый» взгляд)
        int inward = (i == 0) ? 2 : -2;
        int px = cx + inward + (int)pose.lookX;
        int py = cy + (int)pose.lookY;
        int pr = (int)(rx_ * 0.55f);
        int pry = (int)fmaxf(2.0f, ry_ * 0.55f);

        canvas.fillEllipse(px, py, pr, pry, C_PUPIL);
        if (ry_ > 6) {
            canvas.fillSmoothCircle(px + pr / 2, py - pry / 2, 3, C_WHITE);
            canvas.fillSmoothCircle(px - pr / 2, py + pry / 2, 1, C_WHITE);
        }

        // Нижнее веко (прищур)
        if (pose.eyeSquint > 0.05f) {
            int lidH = (int)(ry_ * 2 * pose.eyeSquint);
            canvas.fillRect(cx - rx_ - 2, cy + ry_ - lidH, (rx_ + 2) * 2, lidH + 3, C_SKIN);
            canvas.drawWideLine(cx - rx_, cy + ry_ - lidH, cx + rx_, cy + ry_ - lidH, 2.0f, C_OUTLINE);
        }
    }
}

// ── Рот ─────────────────────────────────────────────────────────────────────
void PetFace::drawMouth(M5Canvas& canvas, const FacePose& pose, PetEmotion emotion, uint32_t now) {
    const int cx = 64;
    const int cy = MOUTH_Y + (int)pose.bob;
    const float open = clampf(pose.mouthOpen, 0.0f, 1.0f);
    const int width = (int)(14 + pose.mouthWidth * 18);

    if (open < 0.12f) {
        // Закрытый рот — кривая из трёх отрезков
        int curve = (int)(pose.mouthCurve * 9.0f);
        canvas.drawWideLine(cx - width, cy - curve / 2, cx - width / 3, cy + curve, 2.6f, C_OUTLINE);
        canvas.drawWideLine(cx - width / 3, cy + curve, cx + width / 3, cy + curve, 2.6f, C_OUTLINE);
        canvas.drawWideLine(cx + width / 3, cy + curve, cx + width, cy - curve / 2, 2.6f, C_OUTLINE);
        return;
    }

    int height = (int)(4 + open * 22);

    canvas.fillEllipse(cx, cy, width + 2, height + 2, C_OUTLINE);
    canvas.fillEllipse(cx, cy, width, height, C_MOUTH);
    // Блик на нёбе
    canvas.fillEllipse(cx, cy - height / 2, width / 2, height / 5, C_MOUTH_LIT);
    // Язык
    if (height > 8) {
        canvas.fillEllipse(cx, cy + height / 2, width - 4, height / 3, C_TONGUE);
    }
}

// ── Слюнка ──────────────────────────────────────────────────────────────────
static void drawDrool(M5Canvas& canvas, const FacePose& pose) {
    if (pose.drool < 0.05f) return;
    int len = (int)(6 + pose.drool * 22);
    int x = 64 + (int)(14 + pose.mouthWidth * 12);
    int y = MOUTH_Y + (int)pose.bob + 4;

    canvas.drawWideLine(x, y, x + 2, y + len, 2.2f, C_DROOL);
    canvas.fillSmoothCircle(x + 2, y + len, 3, C_DROOL);
}

// ── Эффекты эмоций ──────────────────────────────────────────────────────────
void PetFace::drawExtras(M5Canvas& canvas, const FacePose& pose, PetEmotion emotion, uint32_t now) {
    uint16_t hot = accent(canvas, emotion);

    if (pose.blush > 0.05f) {
        uint8_t alpha = (uint8_t)(120 + pose.blush * 90);
        uint16_t blush = canvas.color565(alpha, 60, 90);
        canvas.fillEllipse(30, 82, 10, 5, blush);
        canvas.fillEllipse(98, 82, 10, 5, blush);
    }

    switch (emotion) {
        case PetEmotion::SWEAT:
        case PetEmotion::PANIC: {
            for (int i = 0; i < 3; i++) {
                int phase = (now / 6 + i * 300) % 900;
                int y = 20 + phase / 12;
                int x = (i == 0) ? 20 : (i == 1 ? 108 : 96);
                if (y < 100) {
                    canvas.fillSmoothCircle(x, y, 3, canvas.color565(120, 190, 255));
                    canvas.fillTriangle(x - 3, y, x + 3, y, x, y - 7, canvas.color565(120, 190, 255));
                }
            }
            break;
        }
        case PetEmotion::HAPPY:
        case PetEmotion::PARTY: {
            for (int i = 0; i < 4; i++) {
                int phase = (now / 8 + i * 250) % 1000;
                int y = 110 - phase / 10;
                int x = 14 + i * 34 + (int)(sinf(now * 0.004f + i) * 6);
                if (y > 6) {
                    int r = 2 + (i % 2);
                    canvas.fillSmoothCircle(x, y, r, hot);
                }
            }
            break;
        }
        case PetEmotion::SAD: {
            for (int i = 0; i < 2; i++) {
                int phase = (now / 6 + i * 500) % 1200;
                int y = EYE_Y + 12 + phase / 20;
                int x = (i == 0) ? 34 : 94;
                if (y < 120) canvas.fillSmoothCircle(x, y, 3, canvas.color565(90, 160, 255));
            }
            break;
        }
        case PetEmotion::ANGRY: {
            if ((now / 220) % 2 == 0) {
                canvas.fillTriangle(8, 6, 22, 6, 10, 22, canvas.color565(255, 220, 40));
                canvas.fillTriangle(106, 6, 120, 6, 118, 22, canvas.color565(255, 220, 40));
            }
            break;
        }
        case PetEmotion::SLEEPING: {
            canvas.setTextColor(canvas.color565(200, 200, 255));
            canvas.setTextDatum(middle_center);
            canvas.setTextSize(1);
            int phase = now % 3000;
            for (int i = 0; i < 3; i++) {
                int start = i * 700;
                if (phase > start) {
                    int age = phase - start;
                    int y = 40 - age / 90;
                    if (y > 4) {
                        canvas.setTextSize(i == 2 ? 2 : 1);
                        canvas.drawString("z", 96 + i * 8, y);
                    }
                }
            }
            canvas.setTextSize(1);
            break;
        }
        case PetEmotion::THINKING: {
            for (int i = 0; i < 3; i++) {
                float a = now * 0.004f + i * 2.1f;
                int x = 64 + (int)(cosf(a) * 50);
                int y = 40 + (int)(sinf(a) * 26);
                canvas.fillSmoothCircle(x, y, 3, hot);
            }
            break;
        }
        case PetEmotion::LISTENING: {
            // Эквалайзер снизу
            for (int i = 0; i < 7; i++) {
                int h = 3 + (int)(fabsf(sinf(now * 0.012f + i * 0.7f)) * 14);
                canvas.fillRect(10 + i * 16, 124 - h, 9, h, hot);
            }
            break;
        }
        case PetEmotion::LOVE: {
            for (int i = 0; i < 3; i++) {
                int phase = (now / 7 + i * 400) % 1200;
                int y = 108 - phase / 12;
                int x = 24 + i * 36;
                if (y > 8) {
                    int r = 3;
                    uint16_t heart = canvas.color565(255, 90, 150);
                    canvas.fillSmoothCircle(x - r / 2, y, r, heart);
                    canvas.fillSmoothCircle(x + r / 2, y, r, heart);
                    canvas.fillTriangle(x - r - 1, y + 1, x + r + 1, y + 1, x, y + r * 2, heart);
                }
            }
            break;
        }
        default:
            break;
    }
}

// ── Кадр целиком ────────────────────────────────────────────────────────────
void PetFace::draw(M5Canvas& canvas, const FacePose& pose, PetEmotion emotion, uint32_t now) {
    static int16_t halfWidth[SCREEN];
    static int16_t centerX[SCREEN];

    buildSilhouette(pose, halfWidth, centerX);

    drawBackground(canvas, emotion, now);
    drawArms(canvas, pose, halfWidth, centerX);
    drawBody(canvas, pose, halfWidth, centerX);
    drawShorts(canvas, halfWidth, centerX);
    drawBrows(canvas, pose);
    drawEyes(canvas, pose, emotion, now);
    drawMouth(canvas, pose, emotion, now);
    drawDrool(canvas, pose);
    drawExtras(canvas, pose, emotion, now);
}
