#pragma once
#include <M5Unified.h>
#include "PetFace.h"
#include "PetState.h"

// Экраны питомца — переключаются двойным нажатием кнопки
enum class PetScreen : uint8_t {
    FACE = 0,   // мордочка Патрика
    STATS,      // метрики ПК с графиком
    CLOCK,      // часы, помодоро, что играет
    INFO,       // сеть, датчики, состояние
    COUNT
};

class PetAnimator {
public:
    PetAnimator();

    void init();
    void updateTargets(float pitch, float roll);  // считает целевую позу
    void renderFrame();                           // рисует кадр в спрайт и выводит на экран

    // Экраны
    void setScreen(PetScreen screen);
    void nextScreen();
    PetScreen getScreen() const { return screen; }

    // Реплика питомца поверх мордочки
    void showBubble(const char* text, uint32_t durationMs = 7000);
    void clearBubble();

    // Данные для анимации и экранов
    void setAudioLevel(float level) { audioLevel = level; }   // 0..1 — рот шевелится в такт речи
    void setMicLevel(float level)   { micLevel = level; }     // 0..1 — индикатор слушания
    void setNetworkInfo(const char* ssid, const char* ip, int rssi);
    void setFlags(bool micMuted, bool wifiOk, bool serverOk, bool sensorsOk);
    void setClock(bool valid) { clockValid = valid; }
    void setPetName(const char* name);
    void poke();  // короткая реакция «меня трогают»: подпрыгнуть

    float getFps() const { return fps; }

private:
    M5Canvas canvas;

    FacePose pose;        // текущая (сглаженная) поза
    FacePose target;      // куда стремимся
    PetEmotion lastEmotion;
    uint32_t emotionChangedAt;

    PetScreen screen;
    uint32_t screenChangedAt;

    // Микроанимации
    float saccadeX, saccadeY;
    uint32_t nextSaccadeTime;
    bool blinking;
    uint32_t nextBlinkTime;
    float pokeEnergy;

    // Внешние данные
    float audioLevel;
    float micLevel;
    char bubbleText[128];
    uint32_t bubbleUntil;
    char ssidText[33];
    char ipText[17];
    char petName[17];
    int rssi;
    bool micMuted, wifiOk, serverOk, sensorsOk, clockValid;

    // История метрик для графика
    static constexpr int HISTORY = 56;
    uint8_t cpuHistory[HISTORY];
    uint8_t ramHistory[HISTORY];
    int historyIndex;
    uint32_t lastHistoryTime;

    // FPS
    float fps;
    uint32_t lastFrameTime;

    void applyEmotionPose(PetEmotion emotion, uint32_t now);
    void smoothPose();
    void drawBubble();
    void drawStatusStrip();
    void renderStatsScreen(uint32_t now);
    void renderClockScreen(uint32_t now);
    void renderInfoScreen(uint32_t now);
    void pushHistory(uint32_t now);
};

extern PetAnimator petAnimator;
