#include "PCTracker.h"

PCTracker pcTracker;

PCTracker::PCTracker()
    : cpuUsage(0), ramUsage(0), gpuUsage(0), temperature(0),
      spotifyPlaying(false), currentTrack(""),
      pomodoroTimeLeft(0), lastPomodoroTick(0), lastUpdateTime(0) {}

void PCTracker::setMetrics(int cpu, int ram, int gpu, int temp) {
    cpuUsage = cpu;
    ramUsage = ram;
    gpuUsage = gpu;
    temperature = temp;
    lastUpdateTime = millis();
}

void PCTracker::setSpotify(const char* track) {
    if (!track || !track[0]) {
        clearSpotify();
        return;
    }
    spotifyPlaying = true;
    currentTrack = track;
}

void PCTracker::clearSpotify() {
    spotifyPlaying = false;
    currentTrack = "";
}

void PCTracker::setPomodoro(int secondsLeft) {
    pomodoroTimeLeft = secondsLeft > 0 ? secondsLeft : 0;
    lastPomodoroTick = millis();
}

bool PCTracker::isActive() const {
    return lastUpdateTime != 0 && (millis() - lastUpdateTime < 10000);
}

void PCTracker::update() {
    unsigned long now = millis();

    // Помодоро тикает локально, даже если сервер молчит
    if (pomodoroTimeLeft > 0 && now - lastPomodoroTick >= 1000) {
        int elapsed = (int)((now - lastPomodoroTick) / 1000);
        lastPomodoroTick += (unsigned long)elapsed * 1000;
        pomodoroTimeLeft = pomodoroTimeLeft > elapsed ? pomodoroTimeLeft - elapsed : 0;
    }

    // Данные устарели — показываем прочерки, а не последние известные значения
    if (!isActive() && cpuUsage != 0) {
        cpuUsage = ramUsage = gpuUsage = temperature = 0;
        spotifyPlaying = false;
    }
}
