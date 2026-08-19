#include "PetState.h"

PetState petState;

PetState::PetState() {
    currentEmotion = PetEmotion::INIT;
    emotionText = "Booting...";
    stateStartTime = millis();
    lastAttentionTime = millis();
    attentionLevel = 50;
}

void PetState::setEmotion(PetEmotion emotion, const char* text) {
    if (currentEmotion != emotion) {
        currentEmotion = emotion;
        stateStartTime = millis();
    }
    if (text) {
        emotionText = text;
    } else {
        emotionText = "";
    }
}

void PetState::addAttention(int amount) {
    attentionLevel += amount;
    if (attentionLevel > 100) attentionLevel = 100;
    lastAttentionTime = millis();
}

void PetState::resetIdleTimer() {
    lastAttentionTime = millis();
}

void PetState::update() {
    unsigned long now = millis();
    
    // Boredom decay
    if (now - lastAttentionTime > 60000) { // Decay every 60 seconds of inactivity
        attentionLevel -= 5;
        if (attentionLevel < 0) attentionLevel = 0;
        lastAttentionTime = now;
        
        if (attentionLevel < 20 && currentEmotion == PetEmotion::IDLE) {
            setEmotion(PetEmotion::SAD, "Bored...");
        }
    }

    // Transitions from temporary states back to IDLE
    if (currentEmotion == PetEmotion::INIT && (now - stateStartTime > 3000)) {
        setEmotion(PetEmotion::IDLE, "");
    }
    
    if ((currentEmotion == PetEmotion::LOVE || 
         currentEmotion == PetEmotion::HAPPY || 
         currentEmotion == PetEmotion::ANGRY || 
         currentEmotion == PetEmotion::SAD || 
         currentEmotion == PetEmotion::DIZZY ||
         currentEmotion == PetEmotion::PANIC ||
         currentEmotion == PetEmotion::SWEAT ||
         currentEmotion == PetEmotion::PARTY) 
        && (now - stateStartTime > 5000)) {
        setEmotion(PetEmotion::IDLE, "");
    }
}
