# gui/workers.py
"""
ファイル読み込みなど、時間のかかる処理をメインスレッド (UI) をブロックせずに
実行するためのバックグラウンドワーカー。
"""
import logging
import pandas as pd
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)

# CSV読み込み時に順番に試す文字コード。
# 'utf-8-sig' は BOM 付き/なし どちらの UTF-8 も正しく読めるため、
# 単純な 'utf-8' より先に (かつそれを兼ねて) 試す。
# 'latin-1' は全バイト列を必ずデコードできる最終フォールバック
# (文字化けする可能性はあるが、読み込み自体が失敗することはない)。
#
# ★ 'utf-16' はこのリストに含めない: UTF-16 のバイト列 (0x00 を大量に含む) を
#   cp932/latin-1 で読むと、例外を出さずに文字化けした結果を返してしまうことが
#   あるため、ブラインドな順次試行では正しく検出できない。
#   UTF-16 は BOM (バイト順マーク) の有無で個別に検出する (_detect_bom_encoding)。
CSV_ENCODING_FALLBACKS = ['utf-8-sig', 'cp932', 'latin-1']


def _detect_bom_encoding(file_path):
    """
    ファイル先頭のBOM (バイト順マーク) から文字コードを判定する。
    BOMが無ければ None を返し、通常のフォールバック処理に委ねる。
    """
    with open(file_path, 'rb') as f:
        head = f.read(4)
    if head.startswith(b'\xff\xfe') or head.startswith(b'\xfe\xff'):
        return 'utf-16'
    if head.startswith(b'\xef\xbb\xbf'):
        return 'utf-8-sig'
    return None


def read_data_file(file_path):
    """
    CSV/Excelファイルを読み込み、DataFrame を返す。
    CSVはまずBOMから文字コードを検出し、判定できなければ複数の文字コードを
    順に試して、最初に成功したものを採用する。
    """
    ext = file_path.lower().split('.')[-1]

    if ext == 'csv':
        bom_encoding = _detect_bom_encoding(file_path)
        if bom_encoding is not None:
            try:
                return pd.read_csv(file_path, header=0, encoding=bom_encoding)
            except (UnicodeDecodeError, pd.errors.ParserError):
                pass  # BOMはあるが読めない場合は、通常のフォールバックへ

        last_error = None
        for encoding in CSV_ENCODING_FALLBACKS:
            try:
                return pd.read_csv(file_path, header=0, encoding=encoding)
            except (UnicodeDecodeError, pd.errors.ParserError) as e:
                last_error = e
                continue
        raise ValueError(
            f"CSVファイルの文字コードを判定できませんでした "
            f"(試行: {', '.join(CSV_ENCODING_FALLBACKS)})。詳細: {last_error}"
        )
    elif ext in ('xls', 'xlsx'):
        return pd.read_excel(file_path, engine='openpyxl')
    else:
        raise ValueError(f"未対応のファイル形式です: {ext}")


class DataLoadWorker(QThread):
    """
    CSV/Excelファイルの読み込みをバックグラウンドスレッドで行うワーカー。
    大きなファイルを開いてもメインスレッド (UI) がフリーズしないようにする。
    """
    load_succeeded = Signal(object, str)  # (DataFrame, file_path)
    load_failed = Signal(str, str)        # (エラーメッセージ, file_path)

    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = file_path

    def run(self):
        try:
            df = read_data_file(self.file_path)

            if len(df.columns) < 2:
                raise ValueError("データには少なくとも2列必要です。")

            self.load_succeeded.emit(df, self.file_path)
        except Exception as e:
            logger.exception("ファイル読み込みに失敗しました: %s", self.file_path)
            self.load_failed.emit(str(e), self.file_path)
