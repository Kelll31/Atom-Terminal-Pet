#ifndef PET_DISPLAY_H
#define PET_DISPLAY_H

#include <M5Unified.h>

extern M5Canvas canvas;

void initPetDisplay();
void setPetEmotion(const char* emotion, const char* bubble_msg = nullptr, unsigned long duration_ms = 3500);
void drawSpeechBubble(const char* text);
void renderPetFrame();

#endif // PET_DISPLAY_H
