#include "PCTracker.h"
#include "PetState.h"

PCTracker pcTracker;

PCTracker::PCTracker() {
    cpuUsage = 0;
    ramUsage = 0;
    gpuUsage = 0;
    temperature = 0;
    spotifyPlaying = false;
    currentTrack = "";
    pomodoroTimeLeft = 0;
    lastUpdateTime = 0;
}

void PCTracker::setMetrics(int cpu, int ram, int gpu, int temp) {
    cpuUsage = cpu;
    ramUsage = ram;
    gpuUsage = gpu;
    temperature = temp;
    lastUpdateTime = millis();

    if (temperature > 85) {
        petState.setEmotion(PetEmotion::PANIC, "TOO HOT!");
    } else if (temperature > 70) {
        petState.setEmotion(PetEmotion::SWEAT, "Hot...");
    }
}

void PCTracker::setSpotify(const char* track) {
    spotifyPlaying = true;
    currentTrack = track;
    petState.setEmotion(PetEmotion::PARTY, "Listening");
}

void PCTracker::clearSpotify() {
    spotifyPlaying = false;
    currentTrack = "";
}

void PCTracker::setPomodoro(int timeLeft) {
    pomodoroTimeLeft = timeLeft;
    petState.setEmotion(PetEmotion::WORKING, "Focus");
}

bool PCTracker::isActive() const {
    return (millis() - lastUpdateTime < 10000); // Active if updated in last 10 seconds
}

void PCTracker::update() {
    // Handle timeouts, like if PC disconnected
    if (isActive() == false && cpuUsage != 0) {
        // Reset stats if stale
        cpuUsage = 0;
        ramUsage = 0;
        gpuUsage = 0;
        temperature = 0;
        spotifyPlaying = false;
    }
}
