"""Тесты голосового конвейера: детектор речи, обращение по имени,
живой диалог и перебивание."""

import struct
import time

import pytest

from ai.voice import (
    VoicePipeline,
    contains_stop_word,
    matches_wake_word,
    normalize,
    rms_level,
)
from core.events import split_sentences, to_display_text
from core.settings import settings_store


def tone(amplitude: int, samples: int = 512) -> bytes:
    return b"".join(struct.pack("<h", amplitude if i % 2 else -amplitude) for i in range(samples))


# ── Громкость и VAD ────────────────────────────────────────────────────────
def test_rms_distinguishes_silence_from_speech():
    assert rms_level(tone(0)) == 0.0
    assert rms_level(tone(300)) < 0.02      # шум комнаты
    assert rms_level(tone(9000)) > 0.2      # речь рядом с микрофоном


def test_rms_of_empty_chunk_is_zero():
    assert rms_level(b"") == 0.0


# ── Обращение по имени ─────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "phrase",
    [
        "Патрик открой проект",   # чисто распознанное имя
        "патрик!",                # со знаками препинания
        "потрик что там с диском",  # частая ошибка распознавания
        "пат рик привет",         # имя разбито на два слова
        "эй патрык стой",         # опечатка распознавателя
    ],
)
def test_wake_word_survives_misrecognition(phrase):
    assert matches_wake_word(phrase, ["патрик", "patrick"])


@pytest.mark.parametrize("phrase", ["надо бы кофе", "открой браузер", "привет мир"])
def test_wake_word_not_triggered_by_unrelated_speech(phrase):
    assert not matches_wake_word(phrase, ["Патрик", "atom"])


def test_wake_word_ignores_punctuation_and_case():
    assert matches_wake_word("ПАТРИК, слушай!", ["патрик"])
    assert normalize("ПАТРИК, слушай!") == "патрик  слушай"


def test_strip_wake_word_keeps_the_command():
    assert VoicePipeline._strip_wake_word("Патрик открой проект", ["Патрик"]) == "открой проект"
    assert VoicePipeline._strip_wake_word("открой проект", ["Патрик"]) == "открой проект"
    assert VoicePipeline._strip_wake_word("Патрик, напомни через час", ["Патрик"]) == "напомни через час"


def test_strip_wake_word_handles_split_name():
    """Vosk часто слышит «Патрик» как два слова — команда не должна пострадать."""
    assert (
        VoicePipeline._strip_wake_word("а там покажи загрузку", ["Патрик", "а том"])
        == "покажи загрузку"
    )
    # Первое слово команды не должно съедаться вместе с именем
    assert VoicePipeline._strip_wake_word("Патрик открой браузер", ["Патрик"]) == "открой браузер"


# ── Стоп-слова ─────────────────────────────────────────────────────────────
def test_stop_words_detected():
    assert contains_stop_word("стоп")
    assert contains_stop_word("хватит уже")
    assert not contains_stop_word("останови сервер")


# ── Живой диалог ───────────────────────────────────────────────────────────
def test_conversation_window_opens_and_expires():
    pipeline = VoicePipeline()
    assert not pipeline.conversation_open

    pipeline.open_conversation(1.0)
    assert pipeline.conversation_open
    assert pipeline.state.dict()["conversation_left"] <= 1.0

    pipeline.state.conversation_until = time.time() - 1
    assert not pipeline.conversation_open


def test_conversation_can_be_closed_manually():
    pipeline = VoicePipeline()
    pipeline.open_conversation(30)
    pipeline.close_conversation()
    assert not pipeline.conversation_open


# ── Сборка фразы ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_pipeline_collects_speech_and_finalizes_on_silence(monkeypatch):
    pipeline = VoicePipeline()
    finished: list[bytes] = []

    async def fake_finish(pcm, duration):
        finished.append(pcm)

    monkeypatch.setattr(pipeline, "_finish_utterance", fake_finish)
    monkeypatch.setattr(settings_store.current, "endpoint_silence_sec", 0.0)
    monkeypatch.setattr(settings_store.current, "vad_min_level", 0.05)

    class SilentBus:
        is_speaking = False

        async def emit(self, action, **payload):
            pass

    monkeypatch.setattr("core.events.bus", SilentBus())

    await pipeline.feed(tone(0))          # тишина — фраза не началась
    assert not pipeline.state.speaking

    await pipeline.feed(tone(12000))      # человек заговорил
    assert pipeline.state.speaking

    await pipeline.feed(tone(0))          # пауза закрывает фразу
    assert not pipeline.state.speaking


@pytest.mark.asyncio
async def test_pipeline_ignores_audio_when_voice_disabled(monkeypatch):
    pipeline = VoicePipeline()
    monkeypatch.setattr(settings_store.current, "voice_enabled", False)

    class SilentBus:
        is_speaking = False

        async def emit(self, action, **payload):
            pass

    monkeypatch.setattr("core.events.bus", SilentBus())

    await pipeline.feed(tone(15000))
    assert not pipeline.state.speaking


# ── Подготовка ответа к озвучке и экрану ───────────────────────────────────
def test_sentences_are_split_for_streaming_speech():
    parts = split_sentences("Готово. Нашёл два процесса! Что дальше?")
    assert parts == ["Готово.", "Нашёл два процесса!", "Что дальше?"]


def test_long_sentence_is_chunked():
    long_text = "слово " * 60
    parts = split_sentences(long_text)
    assert all(len(part) <= 160 for part in parts)
    assert len(parts) > 1


def test_display_text_is_transliterated_for_device_screen():
    assert to_display_text("Привет, хозяин!").startswith("Privet")
    assert all(ch.isascii() for ch in to_display_text("Проверка щётки ёжика"))
