# tests/test_i18n.py
"""core/i18n.py の軽量翻訳レイヤーに対するテスト。"""
import importlib
import sys

import pytest

import core.i18n as i18n_module
from core.i18n import (
    DEFAULT_LANGUAGE,
    get_language,
    register_translations,
    set_language,
    tr,
)


@pytest.fixture(autouse=True)
def _restore_language_state():
    """_current_language/_translations はモジュールグローバルなので、
    他のテストへ状態が漏れないようテスト前後でリセットする。"""
    original_language = i18n_module._current_language
    original_translations = {k: dict(v) for k, v in i18n_module._translations.items()}
    yield
    i18n_module._current_language = original_language
    i18n_module._translations = original_translations


def test_default_language_is_japanese():
    assert DEFAULT_LANGUAGE == "ja"
    assert get_language() == "ja"


def test_set_language_to_supported_code_switches_current_language():
    set_language("en")
    assert get_language() == "en"


def test_set_language_with_unsupported_code_falls_back_to_default():
    """未対応の言語コードを渡すと既定言語(日本語)にフォールバックする。"""
    set_language("en")
    assert get_language() == "en"
    set_language("fr")  # 未対応
    assert get_language() == DEFAULT_LANGUAGE


def test_tr_returns_original_text_when_language_is_default():
    set_language("ja")
    assert tr("こんにちは") == "こんにちは"


def test_tr_returns_translation_when_registered_for_current_language():
    register_translations("en", {"こんにちは": "Hello"})
    set_language("en")
    assert tr("こんにちは") == "Hello"


def test_tr_falls_back_to_original_text_when_untranslated_in_current_language():
    register_translations("en", {"こんにちは": "Hello"})
    set_language("en")
    assert tr("未登録の文字列") == "未登録の文字列"


def test_english_translations_module_is_registered_on_import():
    """モジュール読み込み時に core/translations_en.py の辞書が自動登録されている。"""
    assert "en" in i18n_module._translations
    assert len(i18n_module._translations["en"]) > 0


def test_import_error_fallback_when_translations_en_unavailable(caplog):
    """core.translations_en の読み込みに失敗した場合でも、モジュール自体は
    例外を出さずに読み込め、警告ログのみ出力される(except ImportErrorパス)。"""
    sys.modules.pop("core.translations_en", None)
    sentinel_removed = False
    try:
        sys.modules["core.translations_en"] = None  # importをImportErrorにさせる
        sentinel_removed = True
        with caplog.at_level("WARNING"):
            importlib.reload(i18n_module)
        assert "en" not in i18n_module._translations
        assert any("翻訳辞書" in record.message for record in caplog.records)
    finally:
        if sentinel_removed:
            sys.modules.pop("core.translations_en", None)
        importlib.reload(i18n_module)  # 実物のtranslations_enで正常な状態に復元
