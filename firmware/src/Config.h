#pragma once
#include <Arduino.h>

/**
 * Все константы прошивки в одном месте: пины, тайминги, размеры буферов.
 * Раньше они были размазаны по пяти файлам, и подобрать, например, задержку
 * микрофона после речи можно было только перебором.
 */

#define FW_VERSION "3.0.0"

// ── Аудио ───────────────────────────────────────────────────────────────────
// Atomic Echo Base: кодек ES8311 + I2S. Пины одинаковы у AtomS3 и AtomS3R.
static constexpr int AUDIO_SAMPLE_RATE = 16000;
static constexpr int PIN_I2C_SDA = 38;
static constexpr int PIN_I2C_SCL = 39;
static constexpr int PIN_I2S_DI  = 7;
static constexpr int PIN_I2S_WS  = 6;
static constexpr int PIN_I2S_DO  = 5;
static constexpr int PIN_I2S_BCK = 8;

// Один блок вывода = 256 моно-сэмплов = 16 мс. Совпадает с dma_buf_len кодека,
// поэтому i2s_write отдаёт ровно один DMA-буфер и не дробит запись.
static constexpr size_t PLAY_BLOCK_SAMPLES = 256;

// Кольцевой буфер речи. В PSRAM берём 6 секунд — целая реплика влезает целиком
// и не рвётся, если Wi-Fi моргнул. Без PSRAM хватает на полторы секунды.
static constexpr size_t PLAY_RING_PSRAM    = 192 * 1024;
static constexpr size_t PLAY_RING_INTERNAL = 48 * 1024;

// Кадр микрофона: 512 сэмплов моно = 32 мс. Столько же ждёт детектор речи на
// сервере (ai/voice.py держит преролл из 8 кадров ≈ 0.25 с).
static constexpr size_t MIC_CHUNK_BYTES = 1024;
static constexpr int    MIC_CHUNK_SLOTS = 4;

// За один заход из I2S забираем 256 стереокадров — те же 16 мс, что и на выводе.
static constexpr size_t MIC_RAW_BYTES = 1024;

// Сколько молчать микрофоном после того, как динамик замолк: за это время
// затухает эхо от корпуса, иначе питомец слышит собственный хвост фразы.
static constexpr uint32_t MIC_RESUME_DELAY_MS = 220;

// Речь считается идущей, пока в буфере есть данные или прошло меньше этого
// времени с последнего ненулевого блока.
static constexpr uint32_t PLAY_TAIL_MS = 200;

// ── Экран ───────────────────────────────────────────────────────────────────
static constexpr int SCREEN_W = 128;
static constexpr int SCREEN_H = 128;
static constexpr int RENDER_PERIOD_MS = 33;   // ~30 кадров в секунду

// ── Сеть ────────────────────────────────────────────────────────────────────
static constexpr uint16_t WS_PORT = 8000;
static constexpr const char* WS_PATH = "/ws/pet";
static constexpr uint32_t WIFI_RETRY_MIN_MS = 5000;
static constexpr uint32_t WIFI_RETRY_MAX_MS = 60000;
static constexpr uint32_t STATUS_PERIOD_MS  = 20000;

// ── Serial ──────────────────────────────────────────────────────────────────
static constexpr uint32_t SERIAL_BAUD = 115200;
static constexpr size_t SERIAL_RX_BUFFER = 16384;   // аудио идёт кусками по 4 КБ
static constexpr size_t SERIAL_TX_BUFFER = 4096;
static constexpr size_t SERIAL_MAX_PAYLOAD = 8192;

// ── Приоритеты и стеки задач ────────────────────────────────────────────────
// Реальное время — на ядре 1 рядом с основным циклом; отрисовка — на ядре 0,
// где ей мешает только драйвер Wi-Fi (он короткий и с высоким приоритетом).
static constexpr int PRIO_AUDIO_TX = 6;
static constexpr int PRIO_AUDIO_RX = 6;
static constexpr int PRIO_SERIAL   = 4;
static constexpr int PRIO_RENDER   = 2;

static constexpr uint32_t STACK_AUDIO = 4096;
static constexpr uint32_t STACK_SERIAL = 4096;
static constexpr uint32_t STACK_RENDER = 8192;
