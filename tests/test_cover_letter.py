#!/usr/bin/env python3
"""
test_cover_letter.py — автотесты для cover_letter.py

Запуск:
  pytest test_cover_letter.py -v
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Мокаем anthropic до импорта модуля (он проверяет import при загрузке)
anthropic_mock = MagicMock()
sys.modules.setdefault("anthropic", anthropic_mock)

import cover_letter  # noqa: E402


# ── detect_language ────────────────────────────────────────────────────────

class TestDetectLanguage:
    def test_russian_text(self):
        assert cover_letter.detect_language("Ищем опытного C++ разработчика в команду") == "ru"

    def test_english_text(self):
        assert cover_letter.detect_language("Looking for a senior C++ developer") == "en"

    def test_mostly_latin_is_english(self):
        # 2% кириллицы — ниже порога 5%
        text = "A" * 98 + "Ра"
        assert cover_letter.detect_language(text) == "en"

    def test_above_threshold_is_russian(self):
        # 6% кириллицы — выше порога
        text = "A" * 94 + "РРРРРР"
        assert cover_letter.detect_language(text) == "ru"

    def test_empty_string_no_crash(self):
        result = cover_letter.detect_language("")
        assert result in ("ru", "en")

    def test_pure_cyrillic(self):
        assert cover_letter.detect_language("Привет мир") == "ru"

    def test_pure_latin(self):
        assert cover_letter.detect_language("Hello world") == "en"


# ── extract_title ──────────────────────────────────────────────────────────

class TestExtractTitle:
    def test_extracts_first_line(self):
        text = "Senior C++ Developer\nОпыт от 3 лет\nРемоут"
        assert cover_letter.extract_title(text) == "Senior C++ Developer"

    def test_truncates_at_80_chars(self):
        text = "X" * 100 + "\nSecond line"
        assert len(cover_letter.extract_title(text)) <= 80

    def test_empty_text_returns_fallback(self):
        assert cover_letter.extract_title("") == "Без названия"

    def test_whitespace_only_returns_fallback(self):
        assert cover_letter.extract_title("   ") == "Без названия"

    def test_strips_whitespace(self):
        result = cover_letter.extract_title("  C++ Dev  \nLine 2")
        assert result == "C++ Dev"


# ── build_prompt ───────────────────────────────────────────────────────────

class TestBuildPrompt:
    def test_russian_lang_in_system(self):
        system, _ = cover_letter.build_prompt("вакансия", "formal", "standard", "ru")
        assert "РУССКОМ" in system

    def test_english_lang_in_system(self):
        system, _ = cover_letter.build_prompt("vacancy", "formal", "standard", "en")
        assert "ENGLISH" in system

    def test_word_count_short(self):
        system, _ = cover_letter.build_prompt("text", "formal", "short", "ru")
        assert "150" in system

    def test_word_count_standard(self):
        system, _ = cover_letter.build_prompt("text", "formal", "standard", "ru")
        assert "250" in system

    def test_word_count_full(self):
        system, _ = cover_letter.build_prompt("text", "formal", "full", "ru")
        assert "400" in system

    def test_upwork_style_mentioned(self):
        system, _ = cover_letter.build_prompt("text", "upwork", "standard", "en")
        assert "Upwork" in system or "upwork" in system.lower()

    def test_vacancy_text_in_user_prompt(self):
        _, user = cover_letter.build_prompt("unique vacancy content 12345", "formal", "standard", "ru")
        assert "unique vacancy content 12345" in user

    def test_candidate_profile_in_system(self):
        system, _ = cover_letter.build_prompt("text", "formal", "standard", "ru")
        assert "Станислав" in system
        assert "C++" in system

    def test_all_styles_work(self):
        for style in ("formal", "technical", "upwork"):
            system, user = cover_letter.build_prompt("text", style, "standard", "ru")
            assert len(system) > 100
            assert len(user) > 5

    def test_all_lengths_work(self):
        for length in ("short", "standard", "full"):
            system, user = cover_letter.build_prompt("text", "formal", length, "ru")
            assert str(cover_letter.LENGTH_WORDS[length]) in system


# ── История ────────────────────────────────────────────────────────────────

class TestHistory:
    def test_save_and_load_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cover_letter, "HISTORY_FILE", tmp_path / "hist.json")
        rec = {"date": "2026-01-01 10:00", "vacancy_title": "C++ Dev", "letter": "Текст"}
        cover_letter.append_to_history(rec)
        history = cover_letter.load_history()
        assert len(history) == 1
        assert history[0]["vacancy_title"] == "C++ Dev"

    def test_load_nonexistent_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cover_letter, "HISTORY_FILE", tmp_path / "missing.json")
        assert cover_letter.load_history() == []

    def test_multiple_appends(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cover_letter, "HISTORY_FILE", tmp_path / "hist.json")
        for i in range(5):
            cover_letter.append_to_history({"date": "2026-01-01", "vacancy_title": f"Job {i}"})
        history = cover_letter.load_history()
        assert len(history) == 5

    def test_corrupted_json_returns_empty(self, tmp_path, monkeypatch):
        f = tmp_path / "hist.json"
        f.write_text("{broken", encoding="utf-8")
        monkeypatch.setattr(cover_letter, "HISTORY_FILE", f)
        assert cover_letter.load_history() == []

    def test_saved_file_is_valid_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cover_letter, "HISTORY_FILE", tmp_path / "hist.json")
        cover_letter.append_to_history({"date": "2026-01-01", "vacancy_title": "Test", "letter": "Письмо"})
        raw = (tmp_path / "hist.json").read_text(encoding="utf-8")
        parsed = json.loads(raw)
        assert isinstance(parsed, list)
        assert parsed[0]["vacancy_title"] == "Test"

    def test_cyrillic_preserved_in_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cover_letter, "HISTORY_FILE", tmp_path / "hist.json")
        cover_letter.append_to_history({"vacancy_title": "Разработчик", "letter": "Уважаемые коллеги"})
        raw = (tmp_path / "hist.json").read_text(encoding="utf-8")
        assert "Разработчик" in raw  # ensure_ascii=False проверка
        assert "\\u" not in raw


# ── generate (мок Claude API) ─────────────────────────────────────────────

class TestGenerate:
    def _make_mock_client(self, text: str = "Сопроводительное письмо"):
        fake_content = MagicMock()
        fake_content.text = text
        fake_msg = MagicMock()
        fake_msg.content = [fake_content]
        fake_client = MagicMock()
        fake_client.messages.create.return_value = fake_msg
        return fake_client

    def test_returns_letter_text(self, monkeypatch):
        fake_client = self._make_mock_client("Уважаемый работодатель")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        with patch("cover_letter.anthropic.Anthropic", return_value=fake_client):
            result = cover_letter.generate("вакансия", "formal", "standard", "ru")
        assert result == "Уважаемый работодатель"

    def test_uses_correct_model(self, monkeypatch):
        fake_client = self._make_mock_client()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        with patch("cover_letter.anthropic.Anthropic", return_value=fake_client):
            cover_letter.generate("vacancy", "upwork", "short", "en")
        kwargs = fake_client.messages.create.call_args.kwargs
        assert kwargs["model"] == cover_letter.MODEL

    def test_calls_api_once(self, monkeypatch):
        fake_client = self._make_mock_client()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        with patch("cover_letter.anthropic.Anthropic", return_value=fake_client):
            cover_letter.generate("text", "formal", "standard", "ru")
        fake_client.messages.create.assert_called_once()

    def test_no_api_key_exits(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(SystemExit):
            cover_letter.generate("text", "formal", "standard", "ru")

    def test_api_error_exits(self, monkeypatch):
        # cover_letter.anthropic — тот же объект что anthropic_mock (MagicMock).
        # Патчим его Anthropic-атрибут напрямую, чтобы клиент поднял исключение.
        fake_client = MagicMock()
        fake_client.messages.create.side_effect = RuntimeError("rate_limit_test")

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setattr(cover_letter.anthropic, "Anthropic",
                            MagicMock(return_value=fake_client))
        with pytest.raises(SystemExit):
            cover_letter.generate("text", "formal", "standard", "ru")

    def test_strips_whitespace_from_response(self, monkeypatch):
        fake_client = self._make_mock_client("  Письмо с пробелами  ")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        with patch("cover_letter.anthropic.Anthropic", return_value=fake_client):
            result = cover_letter.generate("text", "formal", "standard", "ru")
        assert result == "Письмо с пробелами"


# ── fetch_url (мок httpx) ─────────────────────────────────────────────────

class TestFetchUrl:
    def _mock_response(self, html: str):
        resp = MagicMock()
        resp.text = html
        resp.raise_for_status = MagicMock()
        return resp

    def test_strips_html_tags(self):
        resp = self._mock_response("<h1>C++ Developer</h1><p>Опыт Qt</p>")
        with patch("cover_letter.httpx.Client") as mc:
            mc.return_value.__enter__.return_value.get.return_value = resp
            result = cover_letter.fetch_url("https://example.com")
        assert "<h1>" not in result
        assert "C++ Developer" in result

    def test_truncates_to_8000(self):
        resp = self._mock_response("A" * 20000)
        with patch("cover_letter.httpx.Client") as mc:
            mc.return_value.__enter__.return_value.get.return_value = resp
            result = cover_letter.fetch_url("https://example.com")
        assert len(result) <= 8000

    def test_http_error_exits(self):
        import httpx as real_httpx
        with patch("cover_letter.httpx.Client") as mc:
            mc.return_value.__enter__.return_value.get.side_effect = (
                real_httpx.HTTPError("Connection refused")
            )
            with pytest.raises(SystemExit):
                cover_letter.fetch_url("https://example.com")

    def test_collapses_whitespace(self):
        resp = self._mock_response("word1   \n\n  word2")
        with patch("cover_letter.httpx.Client") as mc:
            mc.return_value.__enter__.return_value.get.return_value = resp
            result = cover_letter.fetch_url("https://example.com")
        assert "\n\n" not in result


# ── LENGTH_WORDS / STYLE_DESCRIPTIONS integrity ───────────────────────────

class TestConstants:
    def test_length_words_keys(self):
        assert set(cover_letter.LENGTH_WORDS.keys()) == {"short", "standard", "full"}

    def test_length_words_values(self):
        assert cover_letter.LENGTH_WORDS["short"] < cover_letter.LENGTH_WORDS["standard"]
        assert cover_letter.LENGTH_WORDS["standard"] < cover_letter.LENGTH_WORDS["full"]

    def test_style_descriptions_keys(self):
        assert set(cover_letter.STYLE_DESCRIPTIONS.keys()) == {"formal", "technical", "upwork"}

    def test_all_style_descriptions_non_empty(self):
        for key, val in cover_letter.STYLE_DESCRIPTIONS.items():
            assert len(val) > 10, f"Style '{{key}}' description is too short"

    def test_model_string(self):
        assert "haiku" in cover_letter.MODEL


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
