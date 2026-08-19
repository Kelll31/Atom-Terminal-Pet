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
    WORKING,    // помодоро / долгая задача
    LISTENING,  // слушает микрофон
    TALKING,    // говорит
    THINKING,   // агент думает
    PANIC,      // перегрев/авария
    SWEAT,
    PARTY
};

/**
 * Настроение питомца.
 *
 * Есть базовое состояние (к нему всегда возвращаемся — слушаю/жду/сплю)
 * и временные эмоции с таймером: обрадовался, испугался, закружилась голова.
 * Раньше любая эмоция висела ровно 5 секунд и перебивала важные состояния;
 * теперь у каждой свой срок, а TALKING/LISTENING не сбрасываются по таймеру.
 */
class PetState {
public:
    PetState();

    void update();
    void setEmotion(PetEmotion emotion, const char* text = nullptr, uint32_t holdMs = 0);
    void setBaseEmotion(PetEmotion emotion, const char* text = nullptr);

    PetEmotion getEmotion() const { return currentEmotion; }
    PetEmotion getBaseEmotion() const { return baseEmotion; }
    const char* getEmotionText() const { return emotionText.c_str(); }
    uint32_t timeInState() const { return millis() - stateStartTime; }

    void addAttention(int amount);
    int  getAttention() const { return attentionLevel; }
    void resetIdleTimer();
    bool isSleeping() const { return currentEmotion == PetEmotion::SLEEPING; }

private:
    PetEmotion currentEmotion;
    PetEmotion baseEmotion;
    String emotionText;

    uint32_t stateStartTime;
    uint32_t holdUntil;        // 0 — держать бессрочно
    uint32_t lastAttentionTime;
    int attentionLevel;        // 0..100
};

extern PetState petState;
