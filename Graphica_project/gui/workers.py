# gui/workers.py
"""
ファイル読み込みなど、時間のかかる処理をメインスレッド (UI) をブロックせずに
実行するための処理をまとめたモジュール。実行自体は gui/task_runner.py の
TaskRunner(汎用バックグラウンドワーカー)に委ねる(項目C-004フェーズ4)。
以前はここに専用の DataLoadWorker(QThread)クラスがあったが、TaskRunner導入後
不要になったため削除し、TaskRunnerへ注入する薄い関数(load_data_file_task)に
置き換えた。
"""
import pandas as pd

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
    データファイルを読み込み、DataFrame を返す。

    プラグインが register_importer() (項目B-1) で対応拡張子を登録している場合は
    それを優先し、ビルトインのCSV/Excel読み込みは行わない(プラグイン未登録の
    拡張子・プラグイン0件の場合は、従来通りのビルトイン処理のみが動く)。
    CSVはまずBOMから文字コードを検出し、判定できなければ複数の文字コードを
    順に試して、最初に成功したものを採用する。
    """
    ext = file_path.lower().split('.')[-1]

    from core.plugin_api import get_plugin_api
    from core.plugin_types import PluginExecutionError
    api = get_plugin_api()
    importer = api.get_importer_for_extension(ext) if api is not None else None
    if importer is not None:
        try:
            result = importer.loader(file_path)
        except Exception as e:
            raise PluginExecutionError(importer.name, f"「{file_path}」の読み込みに失敗しました: {e}") from e
        if not isinstance(result, pd.DataFrame):
            raise PluginExecutionError(
                importer.name,
                "現在サポートされているのは単一のDataFrameを返すインポーターのみです"
                "(複数シートを返す形式は未対応です)。"
            )
        return result

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


def load_data_file_task(file_path, report_progress=None, is_cancelled=None):
    """
    read_data_file() + 列数バリデーションをまとめた、TaskRunner
    (gui/task_runner.py)に注入するための薄いラッパー(項目C-004フェーズ4)。
    read_data_file()自体はループを持たない単一のブロッキング呼び出しで
    自然な中断チェックポイントが存在しないため、report_progress/is_cancelled
    は(TaskRunner.run()が必ず渡してくるため)受け取るだけで使わない
    (gui/mixins/dataset_mixin.pyのfit_curve_task/_batch_fit_workerのうち
    単発フィット相当の「中断不能タスク」と同じ扱い)。
    """
    df = read_data_file(file_path)
    if len(df.columns) < 2:
        raise ValueError("データには少なくとも2列必要です。")
    return df
