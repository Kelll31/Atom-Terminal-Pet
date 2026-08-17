#include "PetAnimator.h"
#include "PCTracker.h"

PetAnimator petAnimator;

PetAnimator::PetAnimator() : canvas(&M5.Display) {
    leftEye = {30, 40};
    rightEye = {98, 40};
    targetLeftEye = {30, 40};
    targetRightEye = {98, 40};
    
    eyeWidth = 15; eyeHeight = 25;
    targetEyeWidth = 15; targetEyeHeight = 25;
    
    mouthWidth = 10; mouthHeight = 4;
    targetMouthWidth = 10; targetMouthHeight = 4;
    
    isBlinking = false;
    nextBlinkTime = 0;
}

void PetAnimator::init() {
    canvas.createSprite(128, 128);
    canvas.setSwapBytes(false);
    nextBlinkTime = millis() + random(2000, 5000);
}

float PetAnimator::lerp(float a, float b, float t) {
    return a + (b - a) * t;
}

void PetAnimator::updateTargets(float pitch, float roll) {
    unsigned long now = millis();
    PetEmotion currentEmotion = petState.getEmotion();
    
    // Base target positions (center)
    float baseLeftX = 30;
    float baseRightX = 98;
    float baseY = 40;
    
    // Apply Parallax based on IMU tilt (Roll -> X, Pitch -> Y)
    // Clamp tilt effects
    float parallaxX = constrain(roll * 0.3f, -15.0f, 15.0f);
    float parallaxY = constrain(pitch * 0.3f, -15.0f, 15.0f);
    
    targetLeftEye.x = baseLeftX + parallaxX;
    targetRightEye.x = baseRightX + parallaxX;
    targetLeftEye.y = baseY + parallaxY;
    targetRightEye.y = baseY + parallaxY;

    // Emotion-based overrides
    targetEyeWidth = 15;
    targetEyeHeight = 25;
    targetMouthWidth = 10;
    targetMouthHeight = 4;
    
    switch (currentEmotion) {
        case PetEmotion::SLEEPING:
            targetEyeHeight = 2; // Eyes closed
            targetMouthWidth = 8;
            targetMouthHeight = 8; // O shape
            break;
        case PetEmotion::HAPPY:
        case PetEmotion::LOVE:
            targetEyeHeight = 10;
            targetMouthWidth = 20;
            targetMouthHeight = 12; // Big smile
            targetLeftEye.y -= 5;
            targetRightEye.y -= 5;
            break;
        case PetEmotion::SAD:
            targetEyeHeight = 15;
            targetMouthWidth = 15;
            targetMouthHeight = -5; // Frown
            break;
        case PetEmotion::TALKING:
            // Random mouth movement for talking
            if (now % 200 < 100) targetMouthHeight = 15;
            else targetMouthHeight = 2;
            break;
        case PetEmotion::DIZZY:
            // Crazy eyes
            targetLeftEye.x += sin(now * 0.01) * 10;
            targetLeftEye.y += cos(now * 0.01) * 10;
            targetRightEye.x += sin(now * 0.01 + 3.14) * 10;
            targetRightEye.y += cos(now * 0.01 + 3.14) * 10;
            targetMouthWidth = 5;
            targetMouthHeight = 15; // Open mouth
            break;
        case PetEmotion::PARTY:
            // Bobbing head
            targetLeftEye.y += sin(now * 0.02) * 5;
            targetRightEye.y += sin(now * 0.02) * 5;
            break;
        default:
            break;
    }

    // Blinking logic (override target if blinking)
    if (currentEmotion != PetEmotion::SLEEPING && currentEmotion != PetEmotion::DIZZY) {
        if (!isBlinking && now > nextBlinkTime) {
            isBlinking = true;
            nextBlinkTime = now + 150; // Blink duration
        } else if (isBlinking && now > nextBlinkTime) {
            isBlinking = false;
            nextBlinkTime = now + random(2000, 6000);
        }
        
        if (isBlinking) {
            targetEyeHeight = 2;
        }
    }
}

void PetAnimator::renderFrame() {
    // Lerp values for smooth animation
    float t = 0.3f; // Lerp speed
    leftEye.x = lerp(leftEye.x, targetLeftEye.x, t);
    leftEye.y = lerp(leftEye.y, targetLeftEye.y, t);
    rightEye.x = lerp(rightEye.x, targetRightEye.x, t);
    rightEye.y = lerp(rightEye.y, targetRightEye.y, t);
    
    eyeWidth = lerp(eyeWidth, targetEyeWidth, t);
    eyeHeight = lerp(eyeHeight, targetEyeHeight, t);
    
    mouthWidth = lerp(mouthWidth, targetMouthWidth, t);
    mouthHeight = lerp(mouthHeight, targetMouthHeight, t);

    // 1. Background Layer
    drawBackground();
    
    // 2. Pet Entity Layer
    drawPet();
    
    // 3. HUD/UI Layer
    drawHUD();
    
    // Push to display
    canvas.pushSprite(0, 0);
}

void PetAnimator::drawBackground() {
    canvas.fillSprite(TFT_BLACK);
    PetEmotion emo = petState.getEmotion();
    
    if (emo == PetEmotion::PANIC || emo == PetEmotion::SWEAT) {
        // Red alert background
        canvas.fillRect(0, 0, 128, 128, canvas.color565(50, 0, 0));
    } else if (emo == PetEmotion::WORKING) {
        // Pomodoro focus background
        canvas.fillRect(0, 0, 128, 128, canvas.color565(0, 20, 50));
    }
}

void PetAnimator::drawPet() {
    PetEmotion emo = petState.getEmotion();
    
    // Draw Eyes
    canvas.fillEllipse(leftEye.x, leftEye.y, eyeWidth, eyeHeight, TFT_WHITE);
    canvas.fillEllipse(rightEye.x, rightEye.y, eyeWidth, eyeHeight, TFT_WHITE);
    
    // Pupils
    if (eyeHeight > 5) {
        canvas.fillEllipse(leftEye.x, leftEye.y, eyeWidth * 0.4, eyeHeight * 0.4, TFT_BLACK);
        canvas.fillEllipse(rightEye.x, rightEye.y, eyeWidth * 0.4, eyeHeight * 0.4, TFT_BLACK);
    }
    
    // Draw Mouth
    int mouthY = 85;
    int mouthX = 64;
    
    if (mouthHeight > 0) {
        canvas.fillEllipse(mouthX, mouthY, mouthWidth, mouthHeight, TFT_WHITE);
    } else {
        // Frown/Line
        canvas.drawLine(mouthX - mouthWidth, mouthY, mouthX + mouthWidth, mouthY - mouthHeight, TFT_WHITE);
        canvas.drawLine(mouthX - mouthWidth, mouthY - 1, mouthX + mouthWidth, mouthY - mouthHeight - 1, TFT_WHITE);
    }
    
    // Cheeks for LOVE or HAPPY
    if (emo == PetEmotion::LOVE || emo == PetEmotion::HAPPY) {
        canvas.fillEllipse(leftEye.x - 15, leftEye.y + 15, 6, 4, canvas.color565(255, 100, 100));
        canvas.fillEllipse(rightEye.x + 15, rightEye.y + 15, 6, 4, canvas.color565(255, 100, 100));
    }
    
    // Sleeping Zzz
    if (emo == PetEmotion::SLEEPING) {
        canvas.setTextColor(TFT_WHITE);
        canvas.setTextDatum(MC_DATUM);
        canvas.drawString("Z", 100, 20);
        canvas.drawString("z", 110, 10);
    }
}

void PetAnimator::drawHUD() {
    canvas.setTextColor(TFT_WHITE);
    canvas.setTextDatum(MC_DATUM);
    
    // Draw emotion text at bottom
    const char* text = petState.getEmotionText();
    if (text && strlen(text) > 0) {
        canvas.fillRect(0, 110, 128, 18, canvas.color565(30, 30, 30));
        canvas.drawString(text, 64, 119);
    }
    
    // PC Stats Overlay
    if (pcTracker.isActive()) {
        // Small HUD at the top
        canvas.fillRect(0, 0, 128, 12, canvas.color565(30, 30, 30));
        char hudStr[32];
        snprintf(hudStr, sizeof(hudStr), "C:%d%% R:%d%%", pcTracker.getCpu(), pcTracker.getRam());
        canvas.drawString(hudStr, 64, 6);
    }
    
    // Spotify Now Playing
    if (pcTracker.isSpotifyPlaying()) {
        canvas.fillRect(0, 12, 128, 12, canvas.color565(0, 50, 0));
        // simple marquee could be implemented here, static for now
        canvas.drawString(pcTracker.getSpotifyTrack(), 64, 18);
    }
}
