# core/i18n.py
"""
UIの多言語対応(項目41)のための軽量な翻訳レイヤー。

Qt標準の QTranslator/.ts・.qm 方式は、翻訳ファイルのコンパイルに
pylupdate6/lrelease 等の外部ツール一式が必要になるため、代わりに
「原文(日本語)をキーとして、言語ごとの訳文辞書を引く」だけのシンプルな
自前の仕組みにしている。未登録の文字列は原文がそのまま返るため、
翻訳を少しずつ追加していける(未翻訳箇所が空文字列や例外になることはない)。

対応範囲(スコープ): メニュー・主要ボタン・代表的なダイアログのタイトルなど、
最も目に触れる「主要UI」を対象に英訳を整備している。データエディタの
細かいツールチップ等、露出の少ない文言は日本語のまま残る部分がある。

言語切り替えは実行中のウィジェットを動的に再翻訳するのではなく、
次回起動時に反映される(環境設定ダイアログでその旨を案内する)。
"""
import logging

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {"ja": "日本語", "en": "English"}
DEFAULT_LANGUAGE = "ja"

_current_language = DEFAULT_LANGUAGE
_translations = {}  # {lang_code: {原文: 訳文}}


def register_translations(lang_code, mapping):
    """指定した言語コードの翻訳辞書に、{原文: 訳文} のマッピングを追加登録する。"""
    _translations.setdefault(lang_code, {}).update(mapping)


def set_language(lang_code):
    """現在の表示言語を切り替える。未対応の言語コードなら既定言語(日本語)にフォールバックする。"""
    global _current_language
    if lang_code not in SUPPORTED_LANGUAGES:
        lang_code = DEFAULT_LANGUAGE
    _current_language = lang_code


def get_language():
    """現在の表示言語コードを返す。"""
    return _current_language


def tr(text):
    """
    現在の表示言語設定に応じて text を翻訳して返す。
    既定言語(日本語)のとき、または該当言語に訳文が登録されていない文字列は、
    原文(text)をそのまま返す。
    """
    if _current_language == DEFAULT_LANGUAGE:
        return text
    return _translations.get(_current_language, {}).get(text, text)


# モジュール読み込み時に、同梱の英語翻訳辞書を自動登録しておく。
# (呼び出し側が個別に import・登録する手間を無くすため)
try:
    from core.translations_en import TRANSLATIONS as _EN_TRANSLATIONS
    register_translations("en", _EN_TRANSLATIONS)
except ImportError:
    logger.warning("英語翻訳辞書 (core/translations_en.py) の読み込みに失敗しました。")
