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
    float eyeWidth, targetEyeWidth;
    
    float mouthWidth, targetMouthWidth;
    float mouthHeight, targetMouthHeight;
    
    bool isBlinking;
    unsigned long nextBlinkTime;
    
    // Layer rendering
    void drawBackground();
    void drawPet();
    void drawHUD();
    
    // Helper
    float lerp(float a, float b, float t);
};

extern PetAnimator petAnimator;
