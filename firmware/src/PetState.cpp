#include "PetState.h"

PetState petState;

// Через сколько без единого касания, слова и движения питомец засыпает.
static constexpr uint32_t SLEEP_AFTER_MS = 10UL * 60UL * 1000UL;
// Как часто тает шкала внимания, пока с питомцем не общаются.
static constexpr uint32_t ATTENTION_DECAY_MS = 60UL * 1000UL;

// Сколько держится каждая временная эмоция, если срок не задан явно
static uint32_t defaultHold(PetEmotion emotion) {
    switch (emotion) {
        case PetEmotion::HAPPY:
        case PetEmotion::LOVE:
        case PetEmotion::ANGRY:
        case PetEmotion::SAD:
        case PetEmotion::PARTY:   return 4000;
        case PetEmotion::DIZZY:   return 3000;
        case PetEmotion::PANIC:
        case PetEmotion::SWEAT:   return 8000;
        case PetEmotion::THINKING:return 30000;   // страховка, если сервер замолчал
        case PetEmotion::TALKING:
        case PetEmotion::LISTENING:
        case PetEmotion::WORKING:
        case PetEmotion::SLEEPING:
        case PetEmotion::IDLE:    return 0;       // держим, пока не сменят
        default:                  return 0;
    }
}

PetState::PetState()
    : currentEmotion(PetEmotion::INIT), baseEmotion(PetEmotion::IDLE),
      emotionText("Boot..."), stateStartTime(millis()), holdUntil(0),
      lastAttentionTime(millis()), lastDecayTime(millis()), attentionLevel(60) {}

void PetState::setEmotion(PetEmotion emotion, const char* text, uint32_t holdMs) {
    if (currentEmotion != emotion) {
        currentEmotion = emotion;
        stateStartTime = millis();
    }
    emotionText = text ? text : "";

    uint32_t hold = holdMs ? holdMs : defaultHold(emotion);
    holdUntil = hold ? millis() + hold : 0;
}

void PetState::setBaseEmotion(PetEmotion emotion, const char* text) {
    baseEmotion = emotion;
    // Если сейчас ничего важного не происходит — переходим сразу
    if (holdUntil == 0 && currentEmotion != PetEmotion::TALKING &&
        currentEmotion != PetEmotion::THINKING) {
        setEmotion(emotion, text);
    }
}

void PetState::addAttention(int amount) {
    attentionLevel += amount;
    if (attentionLevel > 100) attentionLevel = 100;
    if (attentionLevel < 0) attentionLevel = 0;
    resetIdleTimer();
}

// Питомца потрогали, услышали или сдвинули — считаем это общением.
// Раньше таймер сбрасывала любая смена эмоции, в том числе служебная
// («слушаю» после каждого ответа), поэтому уснуть он не мог никогда.
void PetState::resetIdleTimer() {
    lastAttentionTime = millis();
    lastDecayTime = lastAttentionTime;
    if (currentEmotion == PetEmotion::SLEEPING) {
        setEmotion(baseEmotion, "");
    }
}

void PetState::update() {
    uint32_t now = millis();

    // Загрузка закончилась
    if (currentEmotion == PetEmotion::INIT && now - stateStartTime > 2500) {
        setEmotion(baseEmotion, "");
        return;
    }

    // Временная эмоция отыграла — возвращаемся к базовой
    if (holdUntil != 0 && now > holdUntil) {
        holdUntil = 0;
        setEmotion(baseEmotion, "");
    }

    if (now - lastDecayTime >= ATTENTION_DECAY_MS) {
        lastDecayTime = now;
        attentionLevel -= 4;
        if (attentionLevel < 0) attentionLevel = 0;
    }

    // Долго никто не подходил — питомец задремал. Просыпается от любого
    // касания, тряски или голоса (см. resetIdleTimer).
    if (currentEmotion != PetEmotion::SLEEPING &&
        currentEmotion != PetEmotion::TALKING &&
        currentEmotion != PetEmotion::WORKING &&
        holdUntil == 0 &&
        now - lastAttentionTime > SLEEP_AFTER_MS) {
        setEmotion(PetEmotion::SLEEPING, "zzz");
    }
}
