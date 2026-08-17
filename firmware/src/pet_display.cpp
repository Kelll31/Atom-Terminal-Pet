#include "pet_display.h"
#include <math.h>

M5Canvas canvas(&M5.Display);

String current_emotion = "happy";
String speech_bubble_text = "";
unsigned long bubble_expire_time = 0;
unsigned long last_blink_time = 0;
bool is_blinking = false;
int anim_frame = 0;

// Custom 16-bit Colors (RGB565)
#define COLOR_PINK 0xFD20
#define COLOR_CYBER 0x0210
#define COLOR_EMERALD 0x03E0
#define COLOR_AMBER 0xE200
#define COLOR_CRIMSON 0x7800
#define COLOR_NAVY 0x0810
#define COLOR_NIGHT 0x0008
#define COLOR_FIRE 0xFA20
#define COLOR_PURPLE 0x780F
#define COLOR_GOLD 0xFEA0

void initPetDisplay()
{
    canvas.createSprite(128, 128);
}

void setPetEmotion(const char *emotion, const char *bubble_msg, unsigned long duration_ms)
{
    current_emotion = emotion;
    if (bubble_msg && strlen(bubble_msg) > 0)
    {
        speech_bubble_text = bubble_msg;
        bubble_expire_time = millis() + duration_ms;
    }
    else
    {
        speech_bubble_text = "";
        bubble_expire_time = 0;
    }
    anim_frame = 0; // Reset animation on new emotion
}

void drawSpeechBubble(const char *text)
{
    if (!text || strlen(text) == 0)
        return;

    int bw = 120;
    int bh = 32;
    int bx = (128 - bw) / 2;
    int by = 4;

    // Smooth rounded speech bubble
    canvas.fillRoundRect(bx, by, bw, bh, 8, TFT_WHITE);
    canvas.drawRoundRect(bx, by, bw, bh, 8, TFT_BLACK);
    canvas.drawRoundRect(bx + 1, by + 1, bw - 2, bh - 2, 7, TFT_LIGHTGREY); // Subtle 3D effect

    // Tail pointing down to pet
    canvas.fillTriangle(60, by + bh - 1, 68, by + bh - 1, 58, by + bh + 8, TFT_WHITE);
    canvas.drawLine(60, by + bh, 58, by + bh + 8, TFT_BLACK);
    canvas.drawLine(68, by + bh, 58, by + bh + 8, TFT_BLACK);

    // Text formatting
    canvas.setTextColor(TFT_BLACK, TFT_WHITE);
    canvas.setTextSize(1);
    canvas.setTextDatum(MC_DATUM);
    canvas.drawString(text, 64, by + (bh / 2));
}

void drawStar(int x, int y, int radius, uint16_t color)
{
    // A simple 5-pointed star approximation using triangles
    for (int i = 0; i < 5; i++)
    {
        float a1 = (i * 72 - 18) * PI / 180.0;
        float a2 = ((i + 1) * 72 - 18) * PI / 180.0;
        float a_mid = (i * 72 + 18) * PI / 180.0;

        int x1 = x + cos(a1) * radius;
        int y1 = y + sin(a1) * radius;
        int x2 = x + cos(a2) * radius;
        int y2 = y + sin(a2) * radius;
        int xm = x + cos(a_mid) * (radius / 2.5);
        int ym = y + sin(a_mid) * (radius / 2.5);

        canvas.fillTriangle(x, y, x1, y1, xm, ym, color);
        canvas.fillTriangle(x, y, x2, y2, xm, ym, color);
    }
}

void drawComplexBackground()
{
    if (current_emotion == "love" || current_emotion == "pat")
    {
        canvas.fillScreen(COLOR_PINK);
        // Floating bubbly hearts
        for (int i = 0; i < 6; i++)
        {
            int hx = (i * 25 + (anim_frame)) % 138 - 10;
            int hy = 130 - ((anim_frame * (i % 3 + 2) + i * 20) % 150);
            int size = 3 + (i % 3);
            canvas.fillCircle(hx, hy, size, TFT_RED);
            canvas.fillCircle(hx + size * 1.2, hy, size, TFT_RED);
            canvas.fillTriangle(hx - size, hy + size * 0.5, hx + size * 2.2, hy + size * 0.5, hx + size * 0.6, hy + size * 2.5, TFT_RED);
        }
    }
    else if (current_emotion == "angry")
    {
        // Flickering fire background
        canvas.fillScreen(COLOR_CRIMSON);
        for (int i = 0; i < 8; i++)
        {
            int fx = i * 16;
            int f_height = 20 + abs(sin(anim_frame * 0.5 + i)) * 30;
            canvas.fillTriangle(fx, 128, fx + 16, 128, fx + 8, 128 - f_height, COLOR_FIRE);
            canvas.fillTriangle(fx + 4, 128, fx + 12, 128, fx + 8, 128 - f_height + 10, TFT_YELLOW);
        }
    }
    else if (current_emotion == "dizzy" || current_emotion == "confused")
    {
        canvas.fillScreen(COLOR_PURPLE);
        // Hypnotic rotating spiral/rings
        for (int i = 5; i > 0; i--)
        {
            int r = i * 15 + (anim_frame % 15);
            uint16_t color = (i % 2 == 0) ? COLOR_PURPLE : 0x4810;
            canvas.fillCircle(64, 64, r, color);
        }
    }
    else if (current_emotion == "cool")
    {
        // Synthwave 80s Grid Retro Background
        canvas.fillScreen(COLOR_NIGHT);
        canvas.fillCircle(64, 70, 30, COLOR_PINK); // Retro Sun
        for (int i = 0; i < 6; i++)
        {
            int sy = 70 + (i * i * 2 + anim_frame % 10);
            if (sy < 128)
                canvas.drawLine(0, sy, 128, sy, TFT_CYAN);
        }
        for (int i = 0; i < 7; i++)
        {
            int sx = 64 + (i - 3) * 30;
            canvas.drawLine(64, 70, sx, 128, TFT_CYAN);
        }
    }
    else if (current_emotion == "sleepy")
    {
        canvas.fillScreen(COLOR_NIGHT);
        // Twinkling stars and moving Zzz
        for (int i = 0; i < 8; i++)
        {
            int sx = (i * 45 + 12) % 128;
            int sy = (i * 23 + 5) % 80;
            if ((anim_frame / 5 + i) % 3 != 0)
                canvas.drawPixel(sx, sy, TFT_WHITE);
        }
        // Floating Zzz
        int z_y = 60 - (anim_frame % 40);
        int z_x = 90 + sin(anim_frame * 0.1) * 10;
        canvas.setTextColor(TFT_LIGHTGREY);
        canvas.setTextSize((anim_frame % 40 > 20) ? 2 : 1);
        if (anim_frame % 40 < 35)
            canvas.drawString("Z", z_x, z_y);
    }
    else if (current_emotion == "party")
    {
        canvas.fillScreen(COLOR_GOLD);
        // Falling Confetti
        for (int i = 0; i < 15; i++)
        {
            int cx = (i * 37 + (anim_frame / 2)) % 128;
            int cy = (i * 21 + anim_frame * (1 + i % 3)) % 128;
            uint16_t colors[] = {TFT_RED, TFT_BLUE, TFT_GREEN, TFT_MAGENTA, TFT_CYAN};
            canvas.fillRect(cx, cy, 4, 4, colors[i % 5]);
        }
    }
    else if (current_emotion == "sad" || current_emotion == "error")
    {
        canvas.fillScreen(COLOR_NAVY);
        // Heavy rain or data matrix effect
        for (int i = 0; i < 12; i++)
        {
            int rx = (i * 11) % 128;
            int ry = (i * 33 + anim_frame * 6) % 128;
            int len = (current_emotion == "error") ? 10 : 6;
            uint16_t c = (current_emotion == "error") ? TFT_GREEN : TFT_CYAN;
            canvas.drawLine(rx, ry, rx, ry + len, c);
        }
        // Glitch effect on error
        if (current_emotion == "error" && anim_frame % 10 < 3)
        {
            canvas.drawLine(0, 60, 128, 60, TFT_WHITE);
            canvas.drawLine(0, 80, 128, 80, TFT_RED);
        }
    }
    else if (current_emotion == "tool" || current_emotion == "thinking")
    {
        canvas.fillScreen(COLOR_CYBER);
        // Complex Radar / Scanning HUD
        int angle = anim_frame * 5;
        canvas.drawCircle(64, 64, 45, TFT_CYAN);
        canvas.drawCircle(64, 64, 44, TFT_CYAN);
        int scan_x = 64 + cos(angle * PI / 180.0) * 45;
        int scan_y = 64 + sin(angle * PI / 180.0) * 45;
        canvas.drawLine(64, 64, scan_x, scan_y, TFT_GREEN);

        // Data nodes
        for (int i = 0; i < 4; i++)
        {
            canvas.fillCircle(30 + i * 22, 110, 3 + abs(sin((anim_frame + i) * 0.2)) * 3, 0x07FF);
        }
    }
    else
    {
        // Happy / Default: Gentle breathing space background
        canvas.fillScreen(COLOR_NAVY);
        int breath = sin(anim_frame * 0.05) * 10;
        canvas.drawCircle(64, 64, 50 + breath, 0x1024);
        canvas.drawCircle(64, 64, 30 + breath / 2, 0x1848);
    }
}

void drawComplexEyes(int eye_y, int face_y_offset)
{
    int left_eye_x = 38;
    int right_eye_x = 90;

    // Global Shake effect for angry or error
    if (current_emotion == "angry" || (current_emotion == "error" && anim_frame % 5 == 0))
    {
        left_eye_x += (anim_frame % 3) - 1;
        right_eye_x += (anim_frame % 3) - 1;
        eye_y += (anim_frame % 2);
    }

    if (is_blinking)
    {
        // Thicker, smoother blink arcs
        canvas.drawArc(left_eye_x, eye_y, 15, 11, 190, 350, TFT_WHITE);
        canvas.drawArc(right_eye_x, eye_y, 15, 11, 190, 350, TFT_WHITE);
        return;
    }

    if (current_emotion == "cool")
    {
        // Thug Life Pixel Sunglasses dropping down
        int drop_y = min(eye_y, 20 + anim_frame * 2);
        // Bridge
        canvas.fillRect(45, drop_y - 2, 38, 4, TFT_BLACK);
        // Lenses
        canvas.fillRect(20, drop_y - 6, 30, 16, TFT_BLACK);
        canvas.fillRect(78, drop_y - 6, 30, 16, TFT_BLACK);
        // Glare
        canvas.fillRect(24, drop_y - 4, 8, 4, TFT_WHITE);
        canvas.fillRect(82, drop_y - 4, 8, 4, TFT_WHITE);
    }
    else if (current_emotion == "angry")
    {
        // Angry sharp eyes
        canvas.fillCircle(left_eye_x, eye_y, 14, TFT_WHITE);
        canvas.fillCircle(left_eye_x + 3, eye_y, 5, TFT_BLACK);                                                              // Pupil looking center
        canvas.fillTriangle(left_eye_x - 20, eye_y - 18, left_eye_x + 15, eye_y + 2, left_eye_x - 5, eye_y - 22, TFT_BLACK); // Eyebrow

        canvas.fillCircle(right_eye_x, eye_y, 14, TFT_WHITE);
        canvas.fillCircle(right_eye_x - 3, eye_y, 5, TFT_BLACK);
        canvas.fillTriangle(right_eye_x + 20, eye_y - 18, right_eye_x - 15, eye_y + 2, right_eye_x + 5, eye_y - 22, TFT_BLACK);
    }
    else if (current_emotion == "sleepy")
    {
        // Sleepy / Drooping eyelids
        canvas.fillCircle(left_eye_x, eye_y, 14, TFT_WHITE);
        canvas.fillCircle(right_eye_x, eye_y, 14, TFT_WHITE);
        // Half closed lids
        int lid_y = eye_y + 2 + sin(anim_frame * 0.05) * 4;
        canvas.fillRect(left_eye_x - 15, eye_y - 15, 30, lid_y - (eye_y - 15), COLOR_NIGHT);
        canvas.fillRect(right_eye_x - 15, eye_y - 15, 30, lid_y - (eye_y - 15), COLOR_NIGHT);
        // Pupils
        canvas.fillCircle(left_eye_x, eye_y + 6, 4, TFT_BLACK);
        canvas.fillCircle(right_eye_x, eye_y + 6, 4, TFT_BLACK);
    }
    else if (current_emotion == "party")
    {
        // Star eyes that spin slightly
        drawStar(left_eye_x, eye_y, 18, TFT_YELLOW);
        drawStar(right_eye_x, eye_y, 18, TFT_YELLOW);
        // Inner highlights
        drawStar(left_eye_x, eye_y, 6, TFT_WHITE);
        drawStar(right_eye_x, eye_y, 6, TFT_WHITE);
    }
    else if (current_emotion == "dizzy")
    {
        // Swirling eye effect (Shifted concentric circles)
        for (int i = 3; i > 0; i--)
        {
            int ox = cos(anim_frame * 0.3 * i) * 3;
            int oy = sin(anim_frame * 0.3 * i) * 3;
            canvas.drawCircle(left_eye_x + ox, eye_y + oy, i * 4 + 2, TFT_WHITE);
            canvas.drawCircle(right_eye_x - ox, eye_y - oy, i * 4 + 2, TFT_WHITE);
        }
    }
    else if (current_emotion == "sad" || current_emotion == "error")
    {
        canvas.fillCircle(left_eye_x, eye_y, 15, TFT_WHITE);
        canvas.fillCircle(right_eye_x, eye_y, 15, TFT_WHITE);
        // Sad eyebrows
        canvas.fillRect(left_eye_x - 15, eye_y - 16, 30, 8, COLOR_NAVY);
        canvas.fillTriangle(left_eye_x - 15, eye_y - 8, left_eye_x, eye_y - 8, left_eye_x - 15, eye_y - 16, COLOR_NAVY);
        canvas.fillRect(right_eye_x - 15, eye_y - 16, 30, 8, COLOR_NAVY);
        canvas.fillTriangle(right_eye_x + 15, eye_y - 8, right_eye_x, eye_y - 8, right_eye_x + 15, eye_y - 16, COLOR_NAVY);
        // Pupils
        canvas.fillCircle(left_eye_x + 3, eye_y + 4, 6, TFT_BLACK);
        canvas.fillCircle(right_eye_x - 3, eye_y + 4, 6, TFT_BLACK);

        // Tears
        int tear_y = eye_y + 10 + (anim_frame * 2) % 30;
        if (tear_y < 110)
        {
            canvas.fillCircle(left_eye_x, tear_y, 3, TFT_CYAN);
            canvas.fillCircle(right_eye_x, tear_y, 3, TFT_CYAN);
            canvas.fillTriangle(left_eye_x - 3, tear_y, left_eye_x + 3, tear_y, left_eye_x, tear_y - 5, TFT_CYAN);
            canvas.fillTriangle(right_eye_x - 3, tear_y, right_eye_x + 3, tear_y, right_eye_x, tear_y - 5, TFT_CYAN);
        }
    }
    else
    {
        // Default / Happy / Talking - Standard detailed eyes
        int shift_x = (current_emotion == "thinking") ? (sin(anim_frame * 0.15) * 8) : (cos(anim_frame * 0.08) * 3);
        int shift_y = (current_emotion == "eating") ? (sin(anim_frame * 0.4) * 2) : 0;

        canvas.fillCircle(left_eye_x, eye_y, 16, TFT_WHITE);
        canvas.fillCircle(left_eye_x + shift_x, eye_y + shift_y, 8, TFT_BLACK);
        canvas.fillCircle(left_eye_x + shift_x + 3, eye_y + shift_y - 3, 3, TFT_WHITE); // Highlight

        canvas.fillCircle(right_eye_x, eye_y, 16, TFT_WHITE);
        canvas.fillCircle(right_eye_x + shift_x, eye_y + shift_y, 8, TFT_BLACK);
        canvas.fillCircle(right_eye_x + shift_x + 3, eye_y + shift_y - 3, 3, TFT_WHITE); // Highlight
    }
}

void drawComplexMouth(int mouth_y)
{
    if (current_emotion == "talking")
    {
        // Fluid talking mouth using ellipse varying in height
        int mouth_h = (int)(abs(sin(anim_frame * 0.3)) * 18) + 4;
        int mouth_w = 20 - (mouth_h / 3);
        canvas.fillEllipse(64, mouth_y, mouth_w, mouth_h / 2, TFT_WHITE);
        if (mouth_h > 10)
        {
            // Tongue
            canvas.fillEllipse(64, mouth_y + mouth_h / 4, mouth_w - 4, mouth_h / 4, TFT_RED);
        }
    }
    else if (current_emotion == "eating")
    {
        // Chomping animation
        int open_amt = abs(sin(anim_frame * 0.4)) * 12;
        canvas.fillCircle(64, mouth_y, 14, TFT_BLACK);
        canvas.fillCircle(64, mouth_y + 4, 10, TFT_RED); // tongue
        // Upper and lower lips shutting
        canvas.fillRect(48, mouth_y - 15, 32, 15 - open_amt, COLOR_NAVY); // Assuming default bg color for eating
        canvas.fillRect(48, mouth_y + open_amt, 32, 15, COLOR_NAVY);

        // Food particle moving in
        int food_x = 100 - (anim_frame * 5) % 40;
        if (open_amt > 4)
        {
            canvas.fillCircle(food_x, mouth_y, 4, 0xCE40);            // Cookie/Food
            canvas.fillCircle(food_x - 1, mouth_y - 1, 1, TFT_BLACK); // Choc chip
        }
    }
    else if (current_emotion == "angry")
    {
        // Gritting teeth / Zigzag
        canvas.fillRoundRect(50, mouth_y - 4, 28, 10, 2, TFT_WHITE);
        for (int i = 1; i < 4; i++)
        {
            canvas.drawLine(50 + i * 7, mouth_y - 4, 50 + i * 7, mouth_y + 6, TFT_BLACK);
        }
        canvas.drawLine(50, mouth_y + 1, 78, mouth_y + 1, TFT_BLACK);
    }
    else if (current_emotion == "sleepy" || current_emotion == "dizzy")
    {
        // Wobbly or breathing small mouth
        int w = (current_emotion == "sleepy") ? 6 + sin(anim_frame * 0.1) * 2 : 10;
        canvas.fillCircle(64, mouth_y, w, TFT_WHITE);
        canvas.fillCircle(64, mouth_y, w - 2, TFT_BLACK);
    }
    else if (current_emotion == "party" || current_emotion == "happy")
    {
        // Big wide open happy smile
        canvas.fillCircle(64, mouth_y, 16, TFT_WHITE);
        // Cut off the top half to make a bowl shape
        uint16_t bg = (current_emotion == "party") ? COLOR_GOLD : COLOR_NAVY;
        canvas.fillRect(45, mouth_y - 18, 38, 20, bg);
        // Cheeks overlaps
        canvas.fillCircle(48, mouth_y - 2, 6, bg);
        canvas.fillCircle(80, mouth_y - 2, 6, bg);
    }
    else if (current_emotion == "sad" || current_emotion == "error")
    {
        // Frowning
        canvas.fillCircle(64, mouth_y + 8, 14, TFT_WHITE);
        canvas.fillRect(48, mouth_y + 8, 32, 16, COLOR_NAVY); // cut bottom half
    }
    else if (current_emotion == "cool")
    {
        // Smirk
        canvas.drawLine(54, mouth_y, 74, mouth_y - 4, TFT_WHITE);
        canvas.drawLine(54, mouth_y + 1, 74, mouth_y - 3, TFT_WHITE);
        canvas.drawLine(74, mouth_y - 4, 76, mouth_y - 8, TFT_WHITE);
    }
    else
    {
        // Default flat cute mouth
        canvas.fillRoundRect(54, mouth_y, 20, 4, 2, TFT_WHITE);
    }
}

void renderPetFrame()
{
    anim_frame++;
    unsigned long now = millis();

    // Blink Logic (Randomized natural blinking)
    if (!is_blinking && (now - last_blink_time > 3000 + (rand() % 2000)))
    {
        is_blinking = true;
        last_blink_time = now;
    }
    else if (is_blinking && (now - last_blink_time > 150))
    {
        is_blinking = false;
        last_blink_time = now;
    }

    // Speech Bubble Expiry Logic
    if (bubble_expire_time > 0 && now > bubble_expire_time)
    {
        speech_bubble_text = "";
        bubble_expire_time = 0;
    }

    // 1. Draw Layered Background
    drawComplexBackground();

    // Compute Face Y Offset (Move face down slightly if bubble exists)
    int face_y_offset = (speech_bubble_text.length() > 0) ? 16 : 0;

    // Add breathing effect to face offset
    if (current_emotion != "angry" && current_emotion != "error")
    {
        face_y_offset += sin(anim_frame * 0.1) * 2;
    }

    // 2. Draw Cheeks (drawn behind eyes/mouth for depth)
    int eye_y = 56 + face_y_offset;
    if (current_emotion == "happy" || current_emotion == "love" || current_emotion == "party" || current_emotion == "talking")
    {
        int cheek_y = eye_y + 14;
        int cheek_bounce = sin(anim_frame * 0.2) * 2;
        canvas.fillCircle(24, cheek_y + cheek_bounce, 8, 0xFD6B); // Soft Pink
        canvas.fillCircle(104, cheek_y + cheek_bounce, 8, 0xFD6B);
    }

    // 3. Draw Complex Eyes
    drawComplexEyes(eye_y, face_y_offset);

    // 4. Draw Dynamic Mouth
    int mouth_y = eye_y + 26;
    drawComplexMouth(mouth_y);

    // 5. Draw Speech Bubble on top of everything
    if (speech_bubble_text.length() > 0)
    {
        drawSpeechBubble(speech_bubble_text.c_str());
    }
}