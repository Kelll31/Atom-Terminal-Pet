#pragma once
#include <Arduino.h>

/**
 * Снимок состояния компьютера, который присылает сервер.
 * Класс только хранит данные: решения об эмоциях принимает main.cpp,
 * иначе питомец переключал настроение на каждый пакет метрик.
 */
class PCTracker {
public:
    PCTracker();

    void setMetrics(int cpu, int ram, int gpu, int temp);
    void setSpotify(const char* track);
    void clearSpotify();
    void setPomodoro(int secondsLeft);

    int getCpu() const { return cpuUsage; }
    int getRam() const { return ramUsage; }
    int getGpu() const { return gpuUsage; }
    int getTemp() const { return temperature; }

    bool isSpotifyPlaying() const { return spotifyPlaying; }
    // Название трека читает задача отрисовки, а пишет основной цикл. Буфер
    // фиксированный именно поэтому: у String при переприсваивании освобождается
    // старая память, и указатель под задачей отрисовки становился висячим.
    const char* getSpotifyTrack() const { return currentTrack; }

    int  getPomodoroLeft() const { return pomodoroTimeLeft; }
    bool isPomodoroActive() const { return pomodoroTimeLeft > 0; }

    bool isActive() const;   // метрики приходили недавно
    void update();           // отсчёт помодоро и сброс устаревших данных

private:
    int cpuUsage;
    int ramUsage;
    int gpuUsage;
    int temperature;

    bool spotifyPlaying;
    char currentTrack[64];

    int pomodoroTimeLeft;
    unsigned long lastPomodoroTick;
    unsigned long lastUpdateTime;
};

extern PCTracker pcTracker;
