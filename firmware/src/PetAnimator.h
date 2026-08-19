#pragma once
#include <M5Unified.h>
#include "PetState.h"

// Simple Point struct for animation
struct Point2D {
    float x, y;
};

class PetAnimator {
public:
    PetAnimator();
    void init();

    // Call this in the rendering task (Core 0)
    void renderFrame();

    // Update target parameters based on state and inputs
    void updateTargets(float pitch, float roll);

private:
    M5Canvas canvas;

    // Animation state variables (current and target for lerp)
    Point2D leftEye, rightEye;
    Point2D targetLeftEye, targetRightEye;

    float eyeHeight, targetEyeHeight;
    float eyeWidth,  targetEyeWidth;

    float mouthWidth,  targetMouthWidth;
    float mouthHeight, targetMouthHeight;

    bool isBlinking;
    unsigned long nextBlinkTime;
    float blinkPhase;   // reserved for multi-phase blink

    // Micro-animations
    float saccadeX, saccadeY;
    unsigned long nextSaccadeTime;

    // Breathing
    float breathOffset;

    // Frame counter (for frame-based effects)
    unsigned long frameCount;

    // ── Layer rendering
    void drawBackground();
    void drawPet();
    void drawHUD();
    void drawParticles();  // NEW: emotion particle effects

    // ── Helpers
    float lerp(float a, float b, float t);
    float easeOut(float a, float b, float t);
    void  drawHeart(int x, int y, int size, uint16_t color);
    void  drawStar(int cx, int cy, int outerR, int innerR, uint16_t color);
    void  drawLightning(int x, int y, int size, uint16_t color);
};

extern PetAnimator petAnimator;
