#pragma once
#include <Arduino.h>

class PCTracker {
public:
    PCTracker();

    void setMetrics(int cpu, int ram, int gpu, int temp);
    void setSpotify(const char* track);
    void setPomodoro(int timeLeft);
    void clearSpotify();

    int getCpu() const { return cpuUsage; }
    int getRam() const { return ramUsage; }
    int getGpu() const { return gpuUsage; }
    int getTemp() const { return temperature; }
    
    bool isSpotifyPlaying() const { return spotifyPlaying; }
    const char* getSpotifyTrack() const { return currentTrack.c_str(); }

    bool isActive() const; // Returns true if we received metrics recently
    void update(); // Handle timeouts

private:
    int cpuUsage;
    int ramUsage;
    int gpuUsage;
    int temperature;

    bool spotifyPlaying;
    String currentTrack;

    int pomodoroTimeLeft;

    unsigned long lastUpdateTime;
};

extern PCTracker pcTracker;
