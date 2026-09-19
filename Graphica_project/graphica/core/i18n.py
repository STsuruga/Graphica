"""簡単な翻訳の仕組み: 日本語の原文をキーに、言語ごとの辞書を引く。

Qt の .ts / .qm は外部のツールが要るので使わない。訳の無い文字列は原文のまま返る。
対象はメニューや主なボタンなど目に触れる所だけ。言語の切り替えは次の起動から(作った画面は訳し直さない)。
"""
import logging

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {"ja": "日本語", "en": "English"}
DEFAULT_LANGUAGE = "ja"

_current_language = DEFAULT_LANGUAGE
_translations = {}  # {言語コード: {原文: 訳文}}


def register_translations(lang_code, mapping):
    _translations.setdefault(lang_code, {}).update(mapping)


def set_language(lang_code):
    """対応していない言語なら日本語にする。"""
    global _current_language
    if lang_code not in SUPPORTED_LANGUAGES:
        lang_code = DEFAULT_LANGUAGE
    _current_language = lang_code


def get_language():
    return _current_language


def tr(text):
    """日本語のとき、または訳が無いときは原文のまま。"""
    if _current_language == DEFAULT_LANGUAGE:
        return text
    return _translations.get(_current_language, {}).get(text, text)


try:
    from graphica.core.translations_en import TRANSLATIONS as _EN_TRANSLATIONS
    register_translations("en", _EN_TRANSLATIONS)
except ImportError:
    logger.warning("英語翻訳辞書 (core/translations_en.py) の読み込みに失敗しました。")
