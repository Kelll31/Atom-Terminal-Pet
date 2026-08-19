#pragma once
#include <Arduino.h>

enum class PetEmotion {
    INIT,
    IDLE,
    HAPPY,
    ANGRY,
    SAD,
    LOVE,
    DIZZY,
    SLEEPING,
    SLEEPY = SLEEPING,
    WORKING,   // Pomodoro
    LISTENING, // Voice input
    TALKING,   // Voice output
    THINKING,
    PANIC,     // PC hot
    SWEAT,
    PARTY      // Spotify playing
};

class PetState {
public:
    PetState();

    void update(); // Called from Core 1 to process state logic
    void setEmotion(PetEmotion emotion, const char* text = nullptr);
    PetEmotion getEmotion() const { return currentEmotion; }
    const char* getEmotionText() const { return emotionText.c_str(); }

    void addAttention(int amount); // Patting/Interaction
    void resetIdleTimer();
    bool isSleeping() const { return currentEmotion == PetEmotion::SLEEPING; }

private:
    PetEmotion currentEmotion;
    String emotionText;
    
    unsigned long stateStartTime;
    unsigned long lastAttentionTime;
    int attentionLevel; // 0 to 100
};

extern PetState petState;
