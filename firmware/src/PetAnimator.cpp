#include "PetAnimator.h"
#include "PCTracker.h"
#include "HardwareIO.h"
#include "Sensors.h"
#include <math.h>
#include <time.h>

PetAnimator petAnimator;

static inline float lerpf(float a, float b, float t) { return a + (b - a) * t; }
static inline float clampf(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }

PetAnimator::PetAnimator()
    : canvas(&M5.Display),
      lastEmotion(PetEmotion::INIT), emotionChangedAt(0),
      screen(PetScreen::FACE), screenChangedAt(0),
      saccadeX(0), saccadeY(0), nextSaccadeTime(0),
      blinking(false), nextBlinkTime(0), pokeEnergy(0),
      audioLevel(0), micLevel(0), bubbleUntil(0), rssi(0),
      micMuted(false), wifiOk(false), serverOk(false), sensorsOk(false), clockValid(false),
      historyIndex(0), lastHistoryTime(0), fps(0), lastFrameTime(0) {
    bubbleText[0] = '\0';
    strncpy(ssidText, "—", sizeof(ssidText));
    strncpy(ipText, "—", sizeof(ipText));
    strncpy(petName, "Atom", sizeof(petName));
    memset(cpuHistory, 0, sizeof(cpuHistory));
    memset(ramHistory, 0, sizeof(ramHistory));
}

void PetAnimator::init() {
    canvas.setPsram(true);
    canvas.createSprite(128, 128);
    canvas.setTextWrap(false);
    nextBlinkTime = millis() + random(2000, 5000);
}

void PetAnimator::setScreen(PetScreen next) {
    screen = next;
    screenChangedAt = millis();
}

void PetAnimator::nextScreen() {
    setScreen((PetScreen)(((uint8_t)screen + 1) % (uint8_t)PetScreen::COUNT));
}

void PetAnimator::showBubble(const char* text, uint32_t durationMs) {
    if (!text || !text[0]) return;
    strncpy(bubbleText, text, sizeof(bubbleText) - 1);
    bubbleText[sizeof(bubbleText) - 1] = '\0';
    bubbleUntil = millis() + durationMs;
    screen = PetScreen::FACE;  // реплику всегда показываем на мордочке
}

void PetAnimator::clearBubble() {
    bubbleText[0] = '\0';
    bubbleUntil = 0;
}

void PetAnimator::setNetworkInfo(const char* ssid, const char* ip, int strength) {
    if (ssid) { strncpy(ssidText, ssid, sizeof(ssidText) - 1); ssidText[sizeof(ssidText) - 1] = '\0'; }
    if (ip)   { strncpy(ipText, ip, sizeof(ipText) - 1); ipText[sizeof(ipText) - 1] = '\0'; }
    rssi = strength;
}

void PetAnimator::setFlags(bool muted, bool wifi, bool server, bool sensorsPresent) {
    micMuted = muted;
    wifiOk = wifi;
    serverOk = server;
    sensorsOk = sensorsPresent;
}

void PetAnimator::setPetName(const char* name) {
    if (!name || !name[0]) return;
    strncpy(petName, name, sizeof(petName) - 1);
    petName[sizeof(petName) - 1] = '\0';
}

void PetAnimator::poke() {
    pokeEnergy = 1.0f;
}

// ── Целевая поза по эмоции ──────────────────────────────────────────────────
void PetAnimator::applyEmotionPose(PetEmotion emotion, uint32_t now) {
    const float t = now * 0.001f;

    // Базовая поза: спокойный Патрик с приоткрытым ртом
    target = FacePose();
    target.eyeOpen    = 1.0f;
    target.mouthOpen  = 0.32f;
    target.mouthWidth = 0.45f;
    target.drool      = 0.55f;
    target.bob        = sinf(t * 1.6f) * 1.8f;
    target.armSwing   = sinf(t * 1.2f) * 0.35f;

    switch (emotion) {
        case PetEmotion::HAPPY:
            target.eyeOpen = 0.55f; target.eyeSquint = 0.45f;
            target.browRaise = 4; target.mouthOpen = 0.75f; target.mouthWidth = 0.95f;
            target.mouthCurve = 1.0f; target.blush = 0.8f; target.drool = 0.0f;
            target.bob = sinf(t * 7.0f) * 5.0f;
            target.squash = sinf(t * 7.0f) * 0.12f;
            target.armSwing = sinf(t * 7.0f) * 0.9f;
            break;

        case PetEmotion::ANGRY:
            target.eyeOpen = 0.75f; target.browAngle = -1.0f; target.browRaise = -3;
            target.mouthOpen = 0.5f; target.mouthWidth = 0.8f; target.mouthCurve = -1.0f;
            target.drool = 0.0f;
            target.lean = sinf(t * 22.0f) * 3.0f;
            target.bob = sinf(t * 26.0f) * 1.5f;
            break;

        case PetEmotion::SAD:
            target.eyeOpen = 0.8f; target.browAngle = 1.0f; target.browRaise = -2;
            target.mouthOpen = 0.0f; target.mouthCurve = -0.9f; target.mouthWidth = 0.5f;
            target.drool = 0.0f; target.squash = -0.12f;
            target.bob = 4 + sinf(t * 1.1f) * 1.5f;
            target.lookY = 3;
            break;

        case PetEmotion::LOVE:
            target.mouthOpen = 0.5f; target.mouthWidth = 0.8f; target.mouthCurve = 1.0f;
            target.blush = 1.0f; target.drool = 0.0f;
            target.bob = sinf(t * 2.2f) * 4.0f - 2.0f;
            target.armSwing = sinf(t * 2.2f) * 0.6f;
            break;

        case PetEmotion::DIZZY:
            target.eyeOpen = 1.0f; target.mouthOpen = 0.45f; target.mouthWidth = 0.3f;
            target.drool = 0.9f;
            target.lean = sinf(t * 3.0f) * 9.0f;
            target.bob = cosf(t * 3.0f) * 3.0f;
            break;

        case PetEmotion::SLEEPING:
            target.eyeOpen = 0.0f; target.mouthOpen = 0.22f; target.mouthWidth = 0.2f;
            target.drool = 1.0f; target.browRaise = 2;
            target.bob = sinf(t * 0.8f) * 3.5f;
            target.squash = sinf(t * 0.8f) * 0.08f;
            target.armSwing = 0;
            break;

        case PetEmotion::WORKING:
            target.eyeOpen = 0.7f; target.eyeSquint = 0.25f; target.browAngle = -0.35f;
            target.mouthOpen = 0.12f; target.mouthWidth = 0.35f; target.drool = 0.0f;
            target.lookX = sinf(t * 0.9f) * 7.0f;
            target.bob = sinf(t * 3.2f) * 2.0f;
            break;

        case PetEmotion::LISTENING:
            target.eyeOpen = 1.15f; target.browRaise = 5;
            target.mouthOpen = 0.2f + micLevel * 0.25f;
            target.mouthWidth = 0.4f;
            target.drool = 0.5f;
            target.lookY = -2;
            target.bob = sinf(t * 2.0f) * 2.5f;
            break;

        case PetEmotion::TALKING:
            // Рот открывается ровно настолько, насколько громкий звук идёт в динамик
            target.eyeOpen = 0.95f;
            target.mouthOpen = 0.25f + audioLevel * 0.75f;
            target.mouthWidth = 0.5f + audioLevel * 0.4f;
            target.drool = 0.35f;
            target.bob = sinf(t * 6.0f) * 2.0f;
            target.armSwing = sinf(t * 5.0f) * 0.5f;
            break;

        case PetEmotion::THINKING:
            target.eyeOpen = 0.85f; target.browRaise = 3; target.browAngle = -0.2f;
            target.mouthOpen = 0.08f; target.mouthWidth = 0.3f; target.drool = 0.0f;
            target.lookX = 7 + sinf(t * 0.7f) * 3.0f;
            target.lookY = -5;
            target.lean = sinf(t * 0.6f) * 2.5f;
            break;

        case PetEmotion::PANIC:
            target.eyeOpen = 1.35f; target.browRaise = 7; target.browAngle = 0.6f;
            target.mouthOpen = 0.95f; target.mouthWidth = 0.6f; target.drool = 0.0f;
            target.lean = sinf(t * 40.0f) * 4.0f;
            target.bob = cosf(t * 37.0f) * 2.5f;
            target.armSwing = sinf(t * 18.0f) * 1.0f;
            break;

        case PetEmotion::SWEAT:
            target.eyeOpen = 0.6f; target.eyeSquint = 0.35f; target.browAngle = 0.5f;
            target.mouthOpen = 0.3f; target.mouthCurve = -0.6f; target.mouthWidth = 0.5f;
            target.blush = 0.5f; target.drool = 0.0f;
            target.bob = sinf(t * 2.5f) * 2.0f;
            break;

        case PetEmotion::PARTY:
            target.eyeOpen = 0.5f; target.eyeSquint = 0.5f; target.browRaise = 5;
            target.mouthOpen = 0.8f; target.mouthWidth = 1.0f; target.mouthCurve = 1.0f;
            target.blush = 0.9f; target.drool = 0.0f;
            target.bob = sinf(t * 9.0f) * 6.0f;
            target.lean = sinf(t * 4.5f) * 5.0f;
            target.squash = sinf(t * 9.0f) * 0.18f;
            target.armSwing = sinf(t * 9.0f) * 1.0f;
            break;

        case PetEmotion::INIT:
            target.eyeOpen = 0.2f; target.mouthOpen = 0.1f; target.drool = 0.0f;
            break;

        default:  // IDLE
            target.lookX = saccadeX;
            target.lookY = saccadeY;
            break;
    }
}

// ── Обновление целей ────────────────────────────────────────────────────────
void PetAnimator::updateTargets(float pitch, float roll) {
    uint32_t now = millis();
    PetEmotion emotion = petState.getEmotion();

    if (emotion != lastEmotion) {
        lastEmotion = emotion;
        emotionChangedAt = now;
        // Небольшой «щелчок» при смене настроения — оживляет переход
        pokeEnergy = fmaxf(pokeEnergy, 0.45f);
    }

    // Случайные микродвижения глаз в спокойных состояниях
    if (now > nextSaccadeTime) {
        bool calm = emotion == PetEmotion::IDLE || emotion == PetEmotion::LISTENING ||
                    emotion == PetEmotion::THINKING;
        if (calm && random(10) > 4) {
            saccadeX = random(-6, 7);
            saccadeY = random(-3, 4);
        } else {
            saccadeX *= 0.4f;
            saccadeY *= 0.4f;
        }
        nextSaccadeTime = now + random(400, 2600);
    }

    applyEmotionPose(emotion, now);

    // Наклон корпуса и взгляд следуют за наклоном самого устройства
    target.lean  += clampf(roll * 0.18f, -10.0f, 10.0f);
    target.lookX += clampf(roll * 0.12f, -5.0f, 5.0f);
    target.lookY += clampf(pitch * 0.10f, -4.0f, 4.0f);

    // Моргание
    if (emotion != PetEmotion::SLEEPING && emotion != PetEmotion::DIZZY && target.eyeOpen > 0.2f) {
        if (!blinking && now > nextBlinkTime) {
            blinking = true;
            nextBlinkTime = now + 110;
        } else if (blinking && now > nextBlinkTime) {
            blinking = false;
            nextBlinkTime = now + random(1800, 6000);
        }
        if (blinking) target.eyeOpen = 0.05f;
    }

    // Реакция на прикосновение: подпрыгнуть и сжаться
    if (pokeEnergy > 0.01f) {
        target.squash += pokeEnergy * 0.25f;
        target.bob    -= pokeEnergy * 6.0f;
        pokeEnergy *= 0.90f;
    }
}

void PetAnimator::smoothPose() {
    // Разные скорости: глаза щёлкают быстро, тело двигается плавно
    pose.eyeOpen    = lerpf(pose.eyeOpen,    target.eyeOpen,    target.eyeOpen < pose.eyeOpen ? 0.6f : 0.3f);
    pose.eyeSquint  = lerpf(pose.eyeSquint,  target.eyeSquint,  0.25f);
    pose.browAngle  = lerpf(pose.browAngle,  target.browAngle,  0.2f);
    pose.browRaise  = lerpf(pose.browRaise,  target.browRaise,  0.2f);
    pose.mouthOpen  = lerpf(pose.mouthOpen,  target.mouthOpen,  0.45f);
    pose.mouthWidth = lerpf(pose.mouthWidth, target.mouthWidth, 0.3f);
    pose.mouthCurve = lerpf(pose.mouthCurve, target.mouthCurve, 0.25f);
    pose.lookX      = lerpf(pose.lookX,      target.lookX,      0.25f);
    pose.lookY      = lerpf(pose.lookY,      target.lookY,      0.25f);
    pose.lean       = lerpf(pose.lean,       target.lean,       0.25f);
    pose.squash     = lerpf(pose.squash,     target.squash,     0.3f);
    pose.bob        = lerpf(pose.bob,        target.bob,        0.35f);
    pose.blush      = lerpf(pose.blush,      target.blush,      0.15f);
    pose.drool      = lerpf(pose.drool,      target.drool,      0.12f);
    pose.armSwing   = lerpf(pose.armSwing,   target.armSwing,   0.25f);
}

// ── Кадр ────────────────────────────────────────────────────────────────────
void PetAnimator::renderFrame() {
    uint32_t now = millis();
    smoothPose();
    pushHistory(now);

    switch (screen) {
        case PetScreen::STATS: renderStatsScreen(now); break;
        case PetScreen::CLOCK: renderClockScreen(now); break;
        case PetScreen::INFO:  renderInfoScreen(now);  break;
        default:
            PetFace::draw(canvas, pose, petState.getEmotion(), now);
            drawStatusStrip();
            drawBubble();
            break;
    }

    canvas.pushSprite(0, 0);

    uint32_t frameTime = now - lastFrameTime;
    lastFrameTime = now;
    if (frameTime > 0) fps = fps * 0.9f + (1000.0f / frameTime) * 0.1f;
}

// ── Верхняя строка состояния ────────────────────────────────────────────────
void PetAnimator::drawStatusStrip() {
    // Компактные индикаторы в углах, чтобы не закрывать мордочку
    uint16_t ok   = canvas.color565(80, 230, 140);
    uint16_t warn = canvas.color565(255, 190, 60);
    uint16_t bad  = canvas.color565(255, 90, 90);
    uint16_t dim  = canvas.color565(90, 100, 120);

    // Связь
    canvas.fillSmoothCircle(6, 6, 3, serverOk ? ok : (wifiOk ? warn : bad));

    // Микрофон
    if (micMuted) {
        canvas.fillSmoothCircle(18, 6, 3, bad);
        canvas.drawLine(15, 3, 21, 9, canvas.color565(255, 255, 255));
    } else {
        int level = (int)(hardwareIO.getMicLevel() * 6);
        canvas.fillSmoothCircle(18, 6, 2 + (level > 2 ? 2 : level), ok);
    }

    // Нагрузка ПК — маленькой полоской справа
    if (pcTracker.isActive()) {
        int cpu = pcTracker.getCpu();
        uint16_t color = cpu > 85 ? bad : (cpu > 60 ? warn : dim);
        canvas.fillRoundRect(96, 3, 28, 7, 3, canvas.color565(20, 24, 34));
        canvas.fillRoundRect(96, 3, 28 * cpu / 100, 7, 3, color);
    }
}

// ── Реплика ─────────────────────────────────────────────────────────────────
void PetAnimator::drawBubble() {
    if (!bubbleText[0] || millis() > bubbleUntil) return;

    canvas.setTextSize(1);
    canvas.setTextDatum(top_left);
    canvas.setTextColor(canvas.color565(20, 24, 34));

    // Перенос по словам под ширину 116 px
    const int maxWidth = 112;
    char lines[3][32];
    int lineCount = 0;
    int lineLen = 0;
    lines[0][0] = '\0';

    const char* p = bubbleText;
    char word[24];
    while (*p && lineCount < 3) {
        int wl = 0;
        while (*p == ' ') p++;
        while (*p && *p != ' ' && wl < (int)sizeof(word) - 1) word[wl++] = *p++;
        word[wl] = '\0';
        if (wl == 0) break;

        int candidate = lineLen + (lineLen ? 1 : 0) + wl;
        if (candidate * 6 > maxWidth && lineLen > 0) {
            lineCount++;
            if (lineCount >= 3) break;
            lines[lineCount][0] = '\0';
            lineLen = 0;
            candidate = wl;
        }
        if (lineLen) strncat(lines[lineCount], " ", 2);
        strncat(lines[lineCount], word, sizeof(lines[0]) - strlen(lines[lineCount]) - 1);
        lineLen = candidate;
    }
    if (lineCount < 3 && lines[lineCount][0]) lineCount++;
    if (lineCount == 0) return;

    int height = 8 + lineCount * 10;
    int top = 128 - height - 4;

    canvas.fillSmoothRoundRect(4, top, 120, height, 6, canvas.color565(236, 240, 248));
    canvas.drawRoundRect(4, top, 120, height, 6, canvas.color565(120, 130, 150));

    for (int i = 0; i < lineCount; i++) {
        canvas.drawString(lines[i], 10, top + 5 + i * 10);
    }
}

// ── Экран метрик ────────────────────────────────────────────────────────────
void PetAnimator::pushHistory(uint32_t now) {
    if (now - lastHistoryTime < 1000) return;
    lastHistoryTime = now;
    cpuHistory[historyIndex] = (uint8_t)pcTracker.getCpu();
    ramHistory[historyIndex] = (uint8_t)pcTracker.getRam();
    historyIndex = (historyIndex + 1) % HISTORY;
}

void PetAnimator::renderStatsScreen(uint32_t now) {
    canvas.fillSprite(canvas.color565(6, 10, 18));
    canvas.setTextDatum(top_left);
    canvas.setTextSize(1);

    struct Row { const char* label; int value; uint16_t color; const char* unit; };
    Row rows[4] = {
        {"CPU",  pcTracker.getCpu(),  canvas.color565(0, 220, 255), "%"},
        {"RAM",  pcTracker.getRam(),  canvas.color565(180, 130, 255), "%"},
        {"GPU",  pcTracker.getGpu(),  canvas.color565(255, 200, 60), "%"},
        {"TEMP", pcTracker.getTemp(), canvas.color565(90, 230, 150), "C"},
    };

    canvas.setTextColor(canvas.color565(150, 160, 180));
    canvas.drawString("SYSTEM", 6, 5);
    canvas.drawString(pcTracker.isActive() ? "online" : "no data", 78, 5);

    for (int i = 0; i < 4; i++) {
        int y = 20 + i * 17;
        canvas.setTextColor(canvas.color565(200, 210, 230));
        canvas.drawString(rows[i].label, 6, y + 2);

        int value = rows[i].value;
        if (value < 0) value = 0;
        if (value > 100) value = 100;

        canvas.fillRoundRect(40, y, 60, 10, 4, canvas.color565(18, 24, 36));
        canvas.fillRoundRect(40, y, 60 * value / 100, 10, 4, rows[i].color);

        char buf[8];
        snprintf(buf, sizeof(buf), "%d%s", rows[i].value, rows[i].unit);
        canvas.setTextColor(rows[i].color);
        canvas.drawString(buf, 104, y + 2);
    }

    // График истории CPU/RAM
    canvas.setTextColor(canvas.color565(120, 130, 150));
    canvas.drawString("60 sec", 6, 92);
    for (int i = 0; i < HISTORY; i++) {
        int idx = (historyIndex + i) % HISTORY;
        int x = 8 + i * 2;
        int cpuH = cpuHistory[idx] * 20 / 100;
        int ramH = ramHistory[idx] * 20 / 100;
        canvas.drawFastVLine(x, 124 - ramH, ramH, canvas.color565(70, 50, 120));
        canvas.drawFastVLine(x, 124 - cpuH, cpuH, canvas.color565(0, 200, 235));
    }
}

// ── Экран часов ─────────────────────────────────────────────────────────────
void PetAnimator::renderClockScreen(uint32_t now) {
    canvas.fillSprite(canvas.color565(4, 6, 14));
    canvas.setTextDatum(middle_center);

    char timeStr[16] = "--:--";
    char dateStr[24] = "";
    if (clockValid) {
        time_t rawTime = time(nullptr);
        struct tm* t = localtime(&rawTime);
        static const char* WEEKDAYS[7] = {"SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"};
        if (t) {
            snprintf(timeStr, sizeof(timeStr), "%02d:%02d", t->tm_hour, t->tm_min);
            snprintf(dateStr, sizeof(dateStr), "%02d.%02d  %s", t->tm_mday, t->tm_mon + 1,
                     WEEKDAYS[t->tm_wday % 7]);
        }
    }

    canvas.setTextColor(canvas.color565(0, 220, 255));
    canvas.setTextSize(3);
    canvas.drawString(timeStr, 64, 40);

    canvas.setTextSize(1);
    canvas.setTextColor(canvas.color565(150, 160, 180));
    canvas.drawString(dateStr, 64, 66);

    // Помодоро
    int pomodoro = pcTracker.getPomodoroLeft();
    if (pomodoro > 0) {
        char buf[24];
        snprintf(buf, sizeof(buf), "FOCUS %d:%02d", pomodoro / 60, pomodoro % 60);
        canvas.setTextColor(canvas.color565(90, 230, 150));
        canvas.drawString(buf, 64, 86);

        int total = 25 * 60;
        int width = 100 * (total - pomodoro) / total;
        canvas.fillRoundRect(14, 96, 100, 6, 3, canvas.color565(18, 24, 36));
        canvas.fillRoundRect(14, 96, width, 6, 3, canvas.color565(90, 230, 150));
    }

    // Что играет
    if (pcTracker.isSpotifyPlaying()) {
        canvas.setTextColor(canvas.color565(200, 210, 230));
        char track[26];
        strncpy(track, pcTracker.getSpotifyTrack(), sizeof(track) - 1);
        track[sizeof(track) - 1] = '\0';
        canvas.drawString(track, 64, 116);
    }
}

// ── Экран состояния ─────────────────────────────────────────────────────────
void PetAnimator::renderInfoScreen(uint32_t now) {
    canvas.fillSprite(canvas.color565(4, 8, 16));
    canvas.setTextDatum(top_left);
    canvas.setTextSize(1);

    canvas.setTextColor(canvas.color565(0, 220, 255));
    canvas.drawString(petName, 6, 6);
    canvas.setTextColor(canvas.color565(120, 130, 150));
    canvas.drawString("AtomS3R", 74, 6);

    auto line = [&](int y, const char* label, const char* value, uint16_t color) {
        canvas.setTextColor(canvas.color565(120, 130, 150));
        canvas.drawString(label, 6, y);
        canvas.setTextColor(color);
        canvas.drawString(value, 46, y);
    };

    uint16_t ok  = canvas.color565(90, 230, 150);
    uint16_t bad = canvas.color565(255, 110, 110);

    line(24, "WiFi",  wifiOk ? ssidText : "нет", wifiOk ? ok : bad);
    line(36, "IP",    ipText, canvas.color565(200, 210, 230));
    line(48, "Server", serverOk ? "online" : "offline", serverOk ? ok : bad);
    line(60, "Mic",   micMuted ? "muted" : "live", micMuted ? bad : ok);
    line(72, "Audio", hardwareIO.isAudioReady() ? "ES8311" : "нет", hardwareIO.isAudioReady() ? ok : bad);
    line(84, "Sense", sensorsOk ? "LTR553" : "нет", sensorsOk ? ok : canvas.color565(120, 130, 150));
    line(96, "PSRAM", hardwareIO.hasPsram() ? "8 MB" : "нет", hardwareIO.hasPsram() ? ok : bad);

    char buf[24];
    snprintf(buf, sizeof(buf), "%d fps  %d dBm", (int)fps, rssi);
    canvas.setTextColor(canvas.color565(100, 110, 130));
    canvas.drawString(buf, 6, 112);
}
