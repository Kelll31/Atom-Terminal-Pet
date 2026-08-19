#include "PetAnimator.h"
#include "PCTracker.h"

PetAnimator petAnimator;

PetAnimator::PetAnimator() : canvas(&M5.Display) {
    leftEye  = {30, 40};
    rightEye = {98, 40};
    targetLeftEye  = {30, 40};
    targetRightEye = {98, 40};

    eyeWidth  = 15; eyeHeight  = 25;
    targetEyeWidth = 15; targetEyeHeight = 25;

    mouthWidth  = 10; mouthHeight  = 4;
    targetMouthWidth = 10; targetMouthHeight = 4;

    isBlinking    = false;
    nextBlinkTime = 0;
    blinkPhase    = 0.0f;
    saccadeX = 0.0f; saccadeY = 0.0f;
    nextSaccadeTime = 0;
    breathOffset = 0.0f;
    frameCount = 0;
}

void PetAnimator::init() {
    canvas.createSprite(128, 128);
    canvas.setSwapBytes(false);
    nextBlinkTime = millis() + random(2000, 5000);
}

float PetAnimator::lerp(float a, float b, float t) {
    return a + (b - a) * t;
}

float PetAnimator::easeOut(float a, float b, float t) {
    return a + (b - a) * t;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

void PetAnimator::drawHeart(int x, int y, int size, uint16_t color) {
    int r = size / 2;
    canvas.fillEllipse(x - r/2, y - r/2, r, r, color);
    canvas.fillEllipse(x + r/2, y - r/2, r, r, color);
    canvas.fillTriangle(x - r - r/2 + 2, y, x + r + r/2 - 2, y, x, y + size, color);
}

// Draw a star at (cx, cy) with inner/outer radius
void PetAnimator::drawStar(int cx, int cy, int outerR, int innerR, uint16_t color) {
    float step = PI / 5.0f;
    int px[10], py[10];
    for (int i = 0; i < 10; i++) {
        float angle = -PI / 2.0f + i * step;
        float r = (i % 2 == 0) ? outerR : innerR;
        px[i] = cx + (int)(cos(angle) * r);
        py[i] = cy + (int)(sin(angle) * r);
    }
    for (int i = 0; i < 10; i++) {
        int j = (i + 1) % 10;
        canvas.drawLine(px[i], py[i], px[j], py[j], color);
    }
}

// Draw a lightning bolt
void PetAnimator::drawLightning(int x, int y, int size, uint16_t color) {
    int s = size;
    canvas.fillTriangle(x,     y,     x+s,   y,     x,     y+s,   color);
    canvas.fillTriangle(x,     y+s,   x+s,   y+s,   x+s,   y+2*s, color);
}

// ── Target update ─────────────────────────────────────────────────────────────

void PetAnimator::updateTargets(float pitch, float roll) {
    unsigned long now = millis();
    frameCount++;
    PetEmotion emo = petState.getEmotion();

    // Base eye positions
    float baseLeftX  = 30;
    float baseRightX = 98;
    float baseY      = 40;

    // Breathing (slow sine wave)
    breathOffset = sin(now * 0.0015f) * 2.0f;

    // Saccades (random eye darting) — only for calm emotions
    if (now > nextSaccadeTime) {
        if (random(10) > 5 && (emo == PetEmotion::IDLE || emo == PetEmotion::THINKING || emo == PetEmotion::LISTENING)) {
            saccadeX = random(-6, 7);
            saccadeY = random(-4, 5);
        } else {
            saccadeX *= 0.5f;
            saccadeY *= 0.5f;
        }
        nextSaccadeTime = now + random(300, 2500);
    }

    // IMU parallax
    float parallaxX = constrain(roll  * 0.25f, -12.0f, 12.0f);
    float parallaxY = constrain(pitch * 0.25f, -12.0f, 12.0f);

    targetLeftEye.x  = baseLeftX  + parallaxX + saccadeX;
    targetRightEye.x = baseRightX + parallaxX + saccadeX;
    targetLeftEye.y  = baseY + parallaxY + saccadeY + breathOffset;
    targetRightEye.y = baseY + parallaxY + saccadeY + breathOffset;

    // Defaults
    targetEyeWidth   = 15;
    targetEyeHeight  = 25;
    targetMouthWidth = 10;
    targetMouthHeight = 4;

    switch (emo) {
        // ── HAPPY ──────────────────────────────────────────────────────────
        case PetEmotion::HAPPY:
            targetEyeHeight  = 8;   // Squinted happy
            targetEyeWidth   = 18;
            targetMouthWidth = 22;
            targetMouthHeight = 14;
            targetLeftEye.y  -= 4;
            targetRightEye.y -= 4;
            // Slight bounce
            targetLeftEye.y  += sin(now * 0.008f) * 3;
            targetRightEye.y += sin(now * 0.008f) * 3;
            break;

        // ── ANGRY ──────────────────────────────────────────────────────────
        case PetEmotion::ANGRY:
            targetEyeHeight  = 10;
            targetEyeWidth   = 13;
            targetMouthWidth = 18;
            targetMouthHeight = -10; // Frown
            // Vibrate (rage tremor)
            targetLeftEye.x  += (random(3) - 1) * 2;
            targetRightEye.x += (random(3) - 1) * 2;
            targetLeftEye.y  += (random(3) - 1);
            targetRightEye.y += (random(3) - 1);
            break;

        // ── PANIC ──────────────────────────────────────────────────────────
        case PetEmotion::PANIC:
            targetEyeHeight  = 30;
            targetEyeWidth   = 22;
            targetMouthWidth = 16;
            targetMouthHeight = 20;
            // Fast vibration
            targetLeftEye.x  += sin(now * 0.05f) * 3;
            targetRightEye.x += cos(now * 0.05f) * 3;
            targetLeftEye.y  += cos(now * 0.05f) * 2;
            targetRightEye.y += sin(now * 0.05f) * 2;
            break;

        // ── SWEAT ──────────────────────────────────────────────────────────
        case PetEmotion::SWEAT:
            targetEyeHeight  = 20;
            targetEyeWidth   = 14;
            targetMouthWidth = 12;
            targetMouthHeight = -4;
            break;

        // ── SLEEPING / SLEEPY ──────────────────────────────────────────────
        case PetEmotion::SLEEPING:
            targetEyeHeight  = 2;
            targetEyeWidth   = 18;
            targetMouthWidth = 6;
            targetMouthHeight = 5; // Small O snore
            break;

        // ── LOVE ───────────────────────────────────────────────────────────
        case PetEmotion::LOVE:
            targetEyeHeight  = 14; // big hearts
            targetEyeWidth   = 16;
            targetMouthWidth = 18;
            targetMouthHeight = 10;
            // Float up gently
            targetLeftEye.y  += sin(now * 0.003f) * 4 - 4;
            targetRightEye.y += sin(now * 0.003f) * 4 - 4;
            break;

        // ── SAD ────────────────────────────────────────────────────────────
        case PetEmotion::SAD:
            targetEyeHeight  = 16;
            targetEyeWidth   = 12;
            targetMouthWidth = 15;
            targetMouthHeight = -7;
            // Droop eyes
            targetLeftEye.y  += 5;
            targetRightEye.y += 5;
            break;

        // ── DIZZY ──────────────────────────────────────────────────────────
        case PetEmotion::DIZZY:
            // Spinning crazy eyes
            targetLeftEye.x  += sin(now * 0.012f) * 12;
            targetLeftEye.y  += cos(now * 0.012f) * 12;
            targetRightEye.x += sin(now * 0.012f + 3.14f) * 12;
            targetRightEye.y += cos(now * 0.012f + 3.14f) * 12;
            targetMouthWidth  = 5;
            targetMouthHeight = 12;
            break;

        // ── TALKING ────────────────────────────────────────────────────────
        case PetEmotion::TALKING:
            if ((now / 120) % 3 == 0)      { targetMouthHeight = 18; targetMouthWidth = 14; }
            else if ((now / 120) % 3 == 1) { targetMouthHeight = 8;  targetMouthWidth = 10; }
            else                            { targetMouthHeight = 2;  targetMouthWidth = 8;  }
            break;

        // ── LISTENING ──────────────────────────────────────────────────────
        case PetEmotion::LISTENING:
            targetEyeHeight  = 24 + sin(now * 0.01f) * 2; // Pulsing attentive eyes
            targetEyeWidth   = 16;
            targetMouthWidth = 10;
            targetMouthHeight = 4 + sin(now * 0.015f) * 2; // Slightly open listening mouth
            // Tilt head / eyes slightly upward
            targetLeftEye.y  -= 4 + sin(now * 0.005f) * 2;
            targetRightEye.y -= 4 + sin(now * 0.005f) * 2;
            targetLeftEye.x  += sin(now * 0.003f) * 3;
            targetRightEye.x += sin(now * 0.003f) * 3;
            break;

        // ── THINKING ───────────────────────────────────────────────────────
        case PetEmotion::THINKING:
            targetEyeHeight  = 18 + sin(now * 0.004f) * 3;
            targetEyeWidth   = 14;
            targetMouthWidth = 8;
            targetMouthHeight = -3; // Slight thinking pucker
            // Look up and to the top-right in a thoughtful posture
            {
                float glanceX = 8 + sin(now * 0.002f) * 4;
                float glanceY = -8 + cos(now * 0.002f) * 3;
                targetLeftEye.x  += glanceX;
                targetRightEye.x += glanceX;
                targetLeftEye.y  += glanceY;
                targetRightEye.y += glanceY;
            }
            break;

        // ── WORKING ────────────────────────────────────────────────────────
        case PetEmotion::WORKING:
            targetEyeHeight  = 18;
            targetEyeWidth   = 12;
            targetMouthWidth = 10;
            targetMouthHeight = 2;
            // Focused — eyes dart left/right slowly
            {
                float gaze = sin(now * 0.0006f) * 12;
                targetLeftEye.x  += gaze;
                targetRightEye.x += gaze;
            }
            break;

        // ── PARTY ──────────────────────────────────────────────────────────
        case PetEmotion::PARTY:
            targetEyeHeight  = 12;
            targetEyeWidth   = 16;
            targetMouthWidth = 20;
            targetMouthHeight = 14;
            // Bobbing
            targetLeftEye.y  += sin(now * 0.02f) * 5;
            targetRightEye.y += sin(now * 0.02f + 0.5f) * 5;
            break;

        default:
            break;
    }

    // ── Blink ─────────────────────────────────────────────────────────────
    if (emo != PetEmotion::SLEEPING && emo != PetEmotion::DIZZY) {
        if (!isBlinking && now > nextBlinkTime) {
            isBlinking    = true;
            nextBlinkTime = now + 120;
        } else if (isBlinking && now > nextBlinkTime) {
            isBlinking    = false;
            nextBlinkTime = now + random(2000, 7000);
        }
        if (isBlinking) targetEyeHeight = 1;
    }
}

// ── Render ────────────────────────────────────────────────────────────────────

void PetAnimator::renderFrame() {
    float t = 0.22f;

    leftEye.x  = easeOut(leftEye.x,  targetLeftEye.x,  t);
    leftEye.y  = easeOut(leftEye.y,  targetLeftEye.y,  t);
    rightEye.x = easeOut(rightEye.x, targetRightEye.x, t);
    rightEye.y = easeOut(rightEye.y, targetRightEye.y, t);

    float eyeT = (targetEyeHeight < eyeHeight) ? 0.75f : 0.18f;
    eyeWidth  = easeOut(eyeWidth,  targetEyeWidth,  t);
    eyeHeight = easeOut(eyeHeight, targetEyeHeight, eyeT);

    mouthWidth  = easeOut(mouthWidth,  targetMouthWidth,  t);
    mouthHeight = easeOut(mouthHeight, targetMouthHeight, t);

    drawBackground();
    drawPet();
    drawHUD();
    drawParticles();

    canvas.pushSprite(0, 0);
}

// ── Background ────────────────────────────────────────────────────────────────

void PetAnimator::drawBackground() {
    unsigned long now = millis();
    PetEmotion emo = petState.getEmotion();

    canvas.fillSprite(TFT_BLACK);

    switch (emo) {
        case PetEmotion::PANIC:
        case PetEmotion::SWEAT: {
            // Pulsating red alert
            uint8_t pulse = (uint8_t)((sin(now * 0.006f) + 1.0f) * 35);
            canvas.fillRect(0, 0, 128, 128, canvas.color565(40 + pulse, 0, 0));
            // Alert grid lines
            canvas.drawRect(2, 2, 124, 124, canvas.color565(180, 0, 0));
            canvas.drawRect(5, 5, 118, 118, canvas.color565(80, 0, 0));
            break;
        }
        case PetEmotion::WORKING: {
            // Deep blue focus
            canvas.fillRect(0, 0, 128, 128, canvas.color565(0, 15, 45));
            // Subtle scan lines
            for (int y = 0; y < 128; y += 4) {
                canvas.drawFastHLine(0, y, 128, canvas.color565(0, 20, 60));
            }
            break;
        }
        case PetEmotion::PARTY: {
            // Dynamic RGB wave
            float t = now * 0.005f;
            uint8_t r = (uint8_t)((sin(t)           + 1.0f) * 55);
            uint8_t g = (uint8_t)((sin(t + 2.094f)  + 1.0f) * 55);
            uint8_t b = (uint8_t)((sin(t + 4.189f)  + 1.0f) * 55);
            canvas.fillRect(0, 0, 128, 128, canvas.color565(r, g, b));
            // Diagonal stripes
            for (int i = -128; i < 256; i += 16) {
                int phase = ((int)(now / 50)) % 16;
                canvas.drawLine(i + phase, 0, i + phase + 128, 128, canvas.color565(r+30, g+30, b+30));
            }
            break;
        }
        case PetEmotion::LOVE: {
            // Warm deep pink
            canvas.fillRect(0, 0, 128, 128, canvas.color565(30, 0, 15));
            // Floating hearts background
            for (int i = 0; i < 3; i++) {
                int hx = 20 + i * 44;
                int hy = 10 + (int)(sin(now * 0.003f + i * 1.2f) * 8);
                uint8_t alpha = 30 + i * 10;
                drawHeart(hx, hy, 8, canvas.color565(alpha, 0, alpha / 2));
            }
            break;
        }
        case PetEmotion::SLEEPING: {
            // Dark purple night
            canvas.fillRect(0, 0, 128, 128, canvas.color565(5, 0, 15));
            // Stars
            srand(42);
            for (int i = 0; i < 12; i++) {
                int sx = rand() % 128;
                int sy = rand() % 80;
                uint8_t bright = (uint8_t)((sin(now * 0.002f + i * 0.8f) + 1.0f) * 60);
                canvas.drawPixel(sx, sy, canvas.color565(bright, bright, bright));
            }
            break;
        }
        case PetEmotion::HAPPY: {
            // Subtle warm background
            uint8_t glow = (uint8_t)((sin(now * 0.004f) + 1.0f) * 20);
            canvas.fillRect(0, 0, 128, 128, canvas.color565(glow, glow + 10, 0));
            break;
        }
        case PetEmotion::LISTENING: {
            // Cyber Cyan pulse
            uint8_t pulse = (uint8_t)((sin(now * 0.008f) + 1.0f) * 20);
            canvas.fillRect(0, 0, 128, 128, canvas.color565(0, 15 + pulse, 25 + pulse));
            // Soundwave concentric radar rings
            int ringR = (int)(now / 15) % 64;
            canvas.drawEllipse(64, 50, ringR, ringR / 2, canvas.color565(0, 120, 200));
            canvas.drawEllipse(64, 50, (ringR + 20) % 64, ((ringR + 20) % 64) / 2, canvas.color565(0, 80, 150));
            break;
        }
        case PetEmotion::THINKING: {
            // Deep Indigo / Matrix thinking grid
            canvas.fillRect(0, 0, 128, 128, canvas.color565(5, 5, 25));
            // Rotating circuit / thinking grid dots
            for (int i = 0; i < 8; i++) {
                float angle = now * 0.003f + i * (PI / 4.0f);
                int gx = 64 + (int)(cos(angle) * 52);
                int gy = 55 + (int)(sin(angle) * 40);
                canvas.fillEllipse(gx, gy, 2, 2, canvas.color565(0, 180, 255));
            }
            break;
        }
        case PetEmotion::SAD: {
            canvas.fillRect(0, 0, 128, 128, canvas.color565(0, 0, 20));
            // Rain effect
            srand(now / 200);
            for (int i = 0; i < 8; i++) {
                int rx = rand() % 128;
                int ry = (rand() % 100) + 10;
                canvas.drawFastVLine(rx, ry, 5, canvas.color565(40, 40, 100));
            }
            break;
        }
        case PetEmotion::ANGRY: {
            canvas.fillRect(0, 0, 128, 128, canvas.color565(20, 0, 0));
            // Zigzag border
            for (int x = 0; x < 128; x += 8) {
                canvas.drawLine(x,     0,   x + 4, 4,  canvas.color565(120, 0, 0));
                canvas.drawLine(x + 4, 4,   x + 8, 0,  canvas.color565(120, 0, 0));
                canvas.drawLine(x,     127, x + 4, 123, canvas.color565(120, 0, 0));
                canvas.drawLine(x + 4, 123, x + 8, 127, canvas.color565(120, 0, 0));
            }
            break;
        }
        default:
            // IDLE — subtle dark with a faint center glow (drawn as concentric dim circles)
            canvas.fillRect(0, 0, 128, 128, canvas.color565(0, 3, 8));
            canvas.drawEllipse(64, 64, 50, 50, canvas.color565(0, 10, 20));
            canvas.drawEllipse(64, 64, 40, 40, canvas.color565(0, 8, 15));
            break;
    }
}

// ── Pet face ──────────────────────────────────────────────────────────────────

void PetAnimator::drawPet() {
    unsigned long now = millis();
    PetEmotion emo = petState.getEmotion();

    int lx = (int)leftEye.x,  ly = (int)leftEye.y;
    int rx = (int)rightEye.x, ry = (int)rightEye.y;
    int ew = (int)eyeWidth,   eh = max(1, (int)eyeHeight);

    // ── Eyes ───────────────────────────────────────────────────────────────

    if (emo == PetEmotion::LOVE) {
        // Heart eyes (pulsating)
        int hSize = max(10, (int)(eyeHeight * 1.5f) + (int)(sin(now * 0.006f) * 3));
        drawHeart(lx, ly, hSize, canvas.color565(255, 60, 120));
        drawHeart(rx, ry, hSize, canvas.color565(255, 60, 120));
        // Glint
        canvas.fillEllipse(lx + 3, ly - 3, 2, 2, TFT_WHITE);
        canvas.fillEllipse(rx + 3, ry - 3, 2, 2, TFT_WHITE);

    } else if (emo == PetEmotion::DIZZY) {
        // X-X eyes (spinning circles)
        for (int i = 0; i < 2; i++) {
            int cx = (i == 0) ? lx : rx;
            int cy = (i == 0) ? ly : ry;
            canvas.drawEllipse(cx, cy, ew, eh, TFT_WHITE);
            float a = now * 0.01f + i * 3.14f;
            canvas.drawLine(cx - (int)(cos(a)*ew), cy - (int)(sin(a)*eh),
                            cx + (int)(cos(a)*ew), cy + (int)(sin(a)*eh), TFT_WHITE);
            canvas.drawLine(cx - (int)(cos(a+1.57f)*ew), cy - (int)(sin(a+1.57f)*eh),
                            cx + (int)(cos(a+1.57f)*ew), cy + (int)(sin(a+1.57f)*eh), TFT_WHITE);
        }

    } else if (emo == PetEmotion::SLEEPING) {
        // Flat closed eyes with ZZZ
        canvas.fillEllipse(lx, ly, ew, max(1, eh), canvas.color565(180, 180, 180));
        canvas.fillEllipse(rx, ry, ew, max(1, eh), canvas.color565(180, 180, 180));
        // ZZZ floating up
        int zPhase = (now % 3000);
        float zY = ly - 30 - (zPhase % 3000) / 60.0f;
        canvas.setTextColor(TFT_WHITE);
        canvas.setTextDatum(MC_DATUM);
        canvas.setTextSize(1);
        if (zPhase > 300)  canvas.drawString("z", lx + 20, (int)zY + 15);
        if (zPhase > 1000) canvas.drawString("Z", lx + 28, (int)zY);
        if (zPhase > 1800) canvas.drawString("Z", lx + 38, (int)zY - 14);

    } else {
        // Normal eyes — white sclera + dark pupil + glint
        uint16_t scleraColor = TFT_WHITE;
        if (emo == PetEmotion::ANGRY) scleraColor = canvas.color565(255, 180, 180);
        if (emo == PetEmotion::SAD)   scleraColor = canvas.color565(180, 180, 255);

        canvas.fillEllipse(lx, ly, ew, eh, scleraColor);
        canvas.fillEllipse(rx, ry, ew, eh, scleraColor);

        // Pupil (shrinks when blinking)
        if (eh > 4) {
            int pw = max(1, (int)(ew * 0.4f));
            int ph = max(1, (int)(eh * 0.45f));
            canvas.fillEllipse(lx, ly, pw, ph, TFT_BLACK);
            canvas.fillEllipse(rx, ry, pw, ph, TFT_BLACK);
            // Glint
            if (eh > 7) {
                canvas.fillEllipse(lx + 3, ly - 3, 2, 2, TFT_WHITE);
                canvas.fillEllipse(rx + 3, ry - 3, 2, 2, TFT_WHITE);
            }
        }

        // ── Eyelids ─────────────────────────────────────────────────────
        uint16_t bg = TFT_BLACK;
        if (emo == PetEmotion::PANIC || emo == PetEmotion::SWEAT) bg = canvas.color565(50, 0, 0);
        else if (emo == PetEmotion::WORKING) bg = canvas.color565(0, 15, 45);
        else if (emo == PetEmotion::PARTY) {
            float t2 = now * 0.005f;
            bg = canvas.color565((uint8_t)((sin(t2)+1)*50), (uint8_t)((sin(t2+2.1f)+1)*50), (uint8_t)((sin(t2+4.2f)+1)*50));
        }
        else if (emo == PetEmotion::HAPPY) bg = canvas.color565((uint8_t)((sin(now*0.004f)+1)*15), 20, 0);
        else if (emo == PetEmotion::SAD)   bg = canvas.color565(0, 0, 20);
        else if (emo == PetEmotion::ANGRY) bg = canvas.color565(20, 0, 0);

        if (emo == PetEmotion::ANGRY) {
            // Angry diagonal eyelids (steeper angle)
            canvas.fillTriangle(lx-20, ly-28, lx+16, ly-28, lx+16, ly-4, bg);
            canvas.fillTriangle(rx-16, ry-28, rx+20, ry-28, rx-16, ry-4, bg);
            // Bold red eyebrows
            for (int t2 = 0; t2 < 3; t2++) {
                canvas.drawLine(lx-13, ly-14+t2, lx+11, ly-5+t2,  canvas.color565(255, 30, 30));
                canvas.drawLine(rx-11, ry-5+t2,  rx+13, ry-14+t2, canvas.color565(255, 30, 30));
            }
        } else if (emo == PetEmotion::SAD) {
            // Sad drooping eyelids
            canvas.fillTriangle(lx-16, ly-28, lx+20, ly-28, lx-16, ly-4, bg);
            canvas.fillTriangle(rx-20, ry-28, rx+16, ry-28, rx+16, ry-4, bg);
        } else if (emo == PetEmotion::HAPPY) {
            // Happy squint (top half masked)
            canvas.fillRect(lx - ew - 2, ly - eh - 2, (ew+2)*2, eh + 2, bg);
            canvas.fillRect(rx - ew - 2, ry - eh - 2, (ew+2)*2, eh + 2, bg);
        }
    }

    // ── Cheeks ──────────────────────────────────────────────────────────────
    if (emo == PetEmotion::LOVE || emo == PetEmotion::HAPPY || emo == PetEmotion::PARTY) {
        uint8_t blush = (uint8_t)(140 + (int)(sin(now * 0.005f) * 30));
        canvas.fillEllipse(lx - 14, ly + 16, 7, 4, canvas.color565(blush, 60, 80));
        canvas.fillEllipse(rx + 14, ry + 16, 7, 4, canvas.color565(blush, 60, 80));
    }

    // ── Mouth ───────────────────────────────────────────────────────────────
    int mouthX = 64;
    int mouthY = 88 + (int)breathOffset;
    int mw = max(2, (int)mouthWidth);
    int mh = (int)mouthHeight;

    if (emo == PetEmotion::TALKING) {
        // Animated open mouth with tongue
        canvas.fillEllipse(mouthX, mouthY, mw, max(1, abs(mh)), TFT_WHITE);
        if (abs(mh) > 5) {
            canvas.fillEllipse(mouthX, mouthY + max(1, abs(mh)) / 2, mw - 4, max(1, abs(mh)) / 3, canvas.color565(255, 80, 100));
        }
    } else if (mh > 0) {
        // Open / smile filled ellipse
        canvas.fillEllipse(mouthX, mouthY, mw, mh, TFT_WHITE);
        // Teeth line
        if (mh > 5) {
            canvas.drawFastHLine(mouthX - mw + 2, mouthY, (mw - 2) * 2, canvas.color565(200, 200, 200));
        }
    } else {
        // Frown / line
        canvas.drawLine(mouthX - mw, mouthY,     mouthX + mw, mouthY - mh,     TFT_WHITE);
        canvas.drawLine(mouthX - mw, mouthY - 1, mouthX + mw, mouthY - mh - 1, TFT_WHITE);
        canvas.drawLine(mouthX - mw, mouthY - 2, mouthX + mw, mouthY - mh - 2, canvas.color565(160, 160, 160));
    }

    // ── Extras per emotion ──────────────────────────────────────────────────

    // Sweat drop (PANIC / SWEAT)
    if (emo == PetEmotion::PANIC || emo == PetEmotion::SWEAT) {
        int sweatY = 8 + (int)((now % 1800) / 45);
        if (sweatY < 40) {
            canvas.fillEllipse(lx - 24, sweatY, 3, 5, canvas.color565(80, 160, 255));
            canvas.fillEllipse(lx - 24, sweatY - 4, 2, 2, canvas.color565(80, 160, 255));
        }
    }

    // Thinking bubble (THINKING)
    if (emo == PetEmotion::THINKING) {
        canvas.fillEllipse(rx + 20, ry - 10, 3, 3, canvas.color565(80, 80, 80));
        canvas.fillEllipse(rx + 26, ry - 17, 4, 4, canvas.color565(80, 80, 80));
        canvas.fillEllipse(rx + 34, ry - 26, 7, 7, canvas.color565(80, 80, 80));
        canvas.drawString("?", rx + 34, ry - 26);
    }

    // Music notes (PARTY)
    if (emo == PetEmotion::PARTY) {
        int noteX = 10 + (int)(now / 30) % 110;
        int noteY = 10 + (int)(sin(now * 0.01f + noteX) * 10);
        canvas.setTextColor(canvas.color565(255, 255, 0));
        canvas.setTextDatum(MC_DATUM);
        canvas.drawString((now / 400) % 2 == 0 ? "♪" : "♫", noteX, noteY);
    }

    // Lightning bolts for ANGRY
    if (emo == PetEmotion::ANGRY && (now / 300) % 3 == 0) {
        drawLightning(5,  5, 8, canvas.color565(255, 220, 0));
        drawLightning(110, 5, 8, canvas.color565(255, 220, 0));
    }
}

// ── HUD ───────────────────────────────────────────────────────────────────────

void PetAnimator::drawHUD() {
    canvas.setTextColor(TFT_WHITE);
    canvas.setTextDatum(MC_DATUM);
    canvas.setTextSize(1);

    const char* text = petState.getEmotionText();
    if (text && strlen(text) > 0) {
        canvas.fillRect(0, 110, 128, 18, canvas.color565(20, 20, 30));
        canvas.drawRect(0, 110, 128, 18, canvas.color565(40, 40, 60));
        canvas.drawString(text, 64, 119);
    }

    if (pcTracker.isActive()) {
        canvas.fillRect(0, 0, 128, 12, canvas.color565(20, 20, 30));
        canvas.drawRect(0, 0, 128, 12, canvas.color565(40, 40, 60));
        char hudStr[32];
        snprintf(hudStr, sizeof(hudStr), "C:%d%% R:%d%%", pcTracker.getCpu(), pcTracker.getRam());
        canvas.drawString(hudStr, 64, 6);
    }

    if (pcTracker.isSpotifyPlaying()) {
        canvas.fillRect(0, 12, 128, 12, canvas.color565(0, 40, 0));
        canvas.drawString(pcTracker.getSpotifyTrack(), 64, 18);
    }
}

// ── Particles ─────────────────────────────────────────────────────────────────

void PetAnimator::drawParticles() {
    unsigned long now = millis();
    PetEmotion emo = petState.getEmotion();

    if (emo == PetEmotion::HAPPY) {
        // Floating stars
        for (int i = 0; i < 4; i++) {
            float phase = now * 0.002f + i * 1.57f;
            int px = 10 + i * 30 + (int)(sin(phase * 0.7f) * 8);
            int py = 100 - (int)((now / 20 + i * 30) % 90);
            uint8_t bright = (uint8_t)((sin(phase) + 1.0f) * 100 + 55);
            canvas.fillEllipse(px, py, 2, 2, canvas.color565(bright, bright, 0));
        }
    } else if (emo == PetEmotion::LOVE) {
        // Rising hearts
        for (int i = 0; i < 3; i++) {
            int elapsed = (now + i * 1000) % 2500;
            int px = 25 + i * 38;
            int py = 105 - elapsed / 22;
            uint8_t alpha = (uint8_t)(255 - elapsed / 10);
            if (alpha > 30) {
                drawHeart(px, py, 6, canvas.color565(alpha, 30, alpha / 2));
            }
        }
    } else if (emo == PetEmotion::SAD) {
        // Falling teardrops
        for (int i = 0; i < 3; i++) {
            int elapsed = (now + i * 800) % 2000;
            int px = 30 + i * 30;
            int py = 50 + elapsed / 18;
            if (py < 110) {
                canvas.fillEllipse(px, py, 2, 3, canvas.color565(60, 60, 200));
                canvas.fillEllipse(px, py - 3, 1, 1, canvas.color565(80, 80, 220));
            }
        }
    } else if (emo == PetEmotion::ANGRY) {
        // Sparks at corners
        for (int i = 0; i < 3; i++) {
            int elapsed = (now * 2 + i * 300) % 600;
            if (elapsed < 300) {
                int px = (i == 0) ? 10 : (i == 1 ? 118 : 64);
                int py = 20 + elapsed / 10;
                canvas.fillEllipse(px, py, 2, 2, canvas.color565(255, 100 + elapsed / 3, 0));
            }
        }
    } else if (emo == PetEmotion::PANIC) {
        // Exploding sparks from center
        for (int i = 0; i < 5; i++) {
            float angle = (now * 0.005f + i * 1.257f);
            float dist  = (float)((now / 5 + i * 100) % 50);
            int px = 64 + (int)(cos(angle) * dist);
            int py = 64 + (int)(sin(angle) * dist);
            if (px > 0 && px < 128 && py > 0 && py < 108) {
                canvas.fillEllipse(px, py, 2, 2, canvas.color565(255, 200, 0));
            }
        }
    } else if (emo == PetEmotion::LISTENING) {
        // Equalizer / Audio Waveform Bars at bottom
        for (int i = 0; i < 7; i++) {
            int barX = 12 + i * 16;
            int barH = 3 + (int)(abs(sin(now * 0.015f + i * 0.8f)) * 16);
            canvas.fillRect(barX, 105 - barH, 8, barH, canvas.color565(0, 220, 255));
            canvas.drawRect(barX, 105 - barH, 8, barH, canvas.color565(255, 255, 255));
        }
    } else if (emo == PetEmotion::THINKING) {
        // Floating loading/thinking dots around head
        for (int i = 0; i < 3; i++) {
            float angle = now * 0.005f + i * (2.0f * PI / 3.0f);
            int orbX = 64 + (int)(cos(angle) * 42);
            int orbY = 40 + (int)(sin(angle) * 24);
            uint8_t b = (uint8_t)(150 + sin(now * 0.01f + i) * 105);
            canvas.fillEllipse(orbX, orbY, 3, 3, canvas.color565(b, 100, 255));
        }
        // Animated thinking ellipsis "..."
        int dotCount = ((now / 400) % 4);
        char dotsStr[8] = "";
        for (int d = 0; d < dotCount; d++) strcat(dotsStr, ".");
        canvas.setTextColor(canvas.color565(0, 220, 255));
        canvas.setTextDatum(MC_DATUM);
        canvas.drawString(dotsStr, 100, 20);
    }
}
