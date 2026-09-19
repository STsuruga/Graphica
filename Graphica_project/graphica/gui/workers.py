# gui/workers.py
"""
ファイル読み込みなど、時間のかかる処理をメインスレッド (UI) をブロックせずに
実行するための処理をまとめたモジュール。実行自体は gui/task_runner.py の
TaskRunner(汎用バックグラウンドワーカー)に委ねる(項目C-004フェーズ4)。
以前はここに専用の DataLoadWorker(QThread)クラスがあったが、TaskRunner導入後
不要になったため削除し、TaskRunnerへ注入する薄い関数(load_data_file_task)に
置き換えた。
"""
import csv
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

# ビルトインで読める拡張子(小文字・ドット付き)。ファイルダイアログのフィルタ、
# ドラッグ&ドロップ/フォルダ一括インポートの振り分け(gui/main_window.py の
# SUPPORTED_DATA_FILE_EXTENSIONS)、ColumnPreviewDialog の形式判定が
# すべてここを参照する。以前はダイアログのフィルタだけが *.txt を含み、
# 読み込み側が非対応という食い違いがあった(v1.4.2 で .txt/.xls に対応)。
#
# - 区切り文字付きテキスト: CSV と同じ経路で、文字コードと区切り文字を自動判定する。
# - Excel: .xlsx は openpyxl、旧形式の .xls は xlrd で読む(excel_engine_for)。
DELIMITED_TEXT_EXTENSIONS = ('.csv', '.txt')
EXCEL_EXTENSIONS = ('.xlsx', '.xls')
BUILTIN_DATA_FILE_EXTENSIONS = DELIMITED_TEXT_EXTENSIONS + EXCEL_EXTENSIONS


def is_delimited_text_file(file_path):
    return bool(file_path) and file_path.lower().endswith(DELIMITED_TEXT_EXTENSIONS)


def is_excel_file(file_path):
    return bool(file_path) and file_path.lower().endswith(EXCEL_EXTENSIONS)


def excel_engine_for(file_path):
    """
    pandas.read_excel / ExcelFile に渡すエンジン名。openpyxl は .xls
    (BIFF 形式)を読めないため、拡張子で xlrd と使い分ける。
    """
    return 'xlrd' if file_path.lower().endswith('.xls') else 'openpyxl'


def pandas_separator(delimiter):
    """
    推測/指定された区切り文字を pandas.read_csv の sep に渡す形にする。
    空白区切りは「空白1文字」ではなく「空白の連続」とみなす(桁揃えのために
    複数の空白を入れたテキストで、空の列が大量にできるのを防ぐ)。
    戻り値は (sep, engine)。正規表現の sep は python エンジンが必要。
    """
    if delimiter == ' ':
        return r'\s+', 'python'
    if len(delimiter) == 1:
        return delimiter, 'c'
    return delimiter, 'python'


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


def _csv_encoding_candidates(file_path):
    """
    BOM検出結果を先頭に、CSV_ENCODING_FALLBACKSを順に並べた候補リストを返す。
    read_data_file()(初回読み込み)と detect_csv_encoding()(項目C-101、
    gui/dialogs.py の ColumnPreviewDialog がエンコーディング欄の「自動判定」表示・
    区切り文字推測のサンプル読み取りに使う)が同じ判定順序を共有するための共通処理。
    """
    bom_encoding = _detect_bom_encoding(file_path)
    candidates = [bom_encoding] if bom_encoding else []
    candidates += [e for e in CSV_ENCODING_FALLBACKS if e not in candidates]
    return candidates


def detect_csv_encoding(file_path):
    """
    CSVファイルの文字コードを判定し、成功した1つを返す(項目C-101)。
    read_data_file()と違い実際にDataFrameとしてパースはせず、テキストとして
    デコードできるかどうかのみを見る軽量な判定(ColumnPreviewDialogの
    エンコーディング欄の初期値・区切り文字自動判定のサンプル読み取りに使うため、
    ファイル全体のパースコストをかけずに済ませる)。
    """
    last_error = None
    for encoding in _csv_encoding_candidates(file_path):
        try:
            with open(file_path, encoding=encoding) as f:
                f.read()
            return encoding
        except UnicodeDecodeError as e:
            last_error = e
            continue
    raise ValueError(
        f"CSVファイルの文字コードを判定できませんでした "
        f"(試行: {', '.join(CSV_ENCODING_FALLBACKS)})。詳細: {last_error}"
    )


def _sniff_delimiter_from_text(sample_text):
    """
    csv.Sniffer を使い、テキストサンプルから区切り文字を推測する共通ロジック
    (項目C-101/C-102)。カンマ/タブ/セミコロン/空白のいずれかを想定し、
    判定できない場合(1列のみのデータ等)はカンマにフォールバックする。
    detect_csv_delimiter(ファイル用)とdetect_clipboard_delimiter
    (クリップボード用)の両方から、同じ判定ロジックとして共有される。
    """
    if not sample_text.strip():
        return ','
    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters=',\t; ')
        return dialect.delimiter
    except csv.Error:
        return ','


def detect_csv_delimiter(file_path, encoding, sample_lines=50):
    """
    ファイル先頭付近のサンプルから区切り文字を推測する(項目C-101)。
    実際の判定ロジックは_sniff_delimiter_from_textに委譲する。
    """
    lines = []
    try:
        with open(file_path, encoding=encoding, errors='replace') as f:
            for _ in range(sample_lines):
                line = f.readline()
                if not line:
                    break
                lines.append(line)
    except OSError:
        return ','
    return _sniff_delimiter_from_text(''.join(lines))


def detect_clipboard_delimiter(text, sample_lines=50):
    """
    クリップボードのテキストから区切り文字を推測する(項目C-102、
    クリップボードのスマート貼り付け)。detect_csv_delimiterと同じ
    Snifferロジックを共有するが、ファイルI/Oを経由せず、既にメモリ上にある
    テキストをそのまま使う(Excel等からのコピーは通常タブ区切りになるが、
    プレーンテキストのCSV/セミコロン区切りデータが貼り付けられた場合にも
    対応するため)。
    """
    sample = ''.join(text.splitlines(keepends=True)[:sample_lines])
    return _sniff_delimiter_from_text(sample)


def read_data_file(file_path):
    """
    データファイルを読み込み、DataFrame を返す。

    プラグインが register_importer() (項目B-1) で対応拡張子を登録している場合は
    それを優先し、ビルトインのCSV/Excel読み込みは行わない(プラグイン未登録の
    拡張子・プラグイン0件の場合は、従来通りのビルトイン処理のみが動く)。
    CSVはまずBOMから文字コードを検出し、判定できなければ複数の文字コードを
    順に試して、最初に成功したものを採用する(区切り文字は既定のカンマ固定。
    実際と異なる場合はColumnPreviewDialog、項目C-101、で読み直せる)。
    """
    ext = file_path.lower().split('.')[-1]

    from graphica.core.plugin_api import get_plugin_api
    from graphica.core.plugin_types import PluginExecutionError
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

    if is_delimited_text_file(file_path):
        # ★ 区切り文字もここで推測する。以前はカンマ固定で読み、区切り文字の
        #   推測は ColumnPreviewDialog に任せていたが、タブ区切りのファイルは
        #   カンマで読むと1列に潰れ、プレビューに届く前に
        #   load_data_file_task の「少なくとも2列必要」で弾かれていた。
        last_error = None
        for encoding in _csv_encoding_candidates(file_path):
            try:
                sep, engine = pandas_separator(detect_csv_delimiter(file_path, encoding))
                return pd.read_csv(file_path, header=0, encoding=encoding, sep=sep, engine=engine)
            except (UnicodeDecodeError, pd.errors.ParserError) as e:
                last_error = e
                continue
        raise ValueError(
            f"テキストファイルの文字コードを判定できませんでした "
            f"(試行: {', '.join(CSV_ENCODING_FALLBACKS)})。詳細: {last_error}"
        )
    elif is_excel_file(file_path):
        return pd.read_excel(file_path, engine=excel_engine_for(file_path))
    else:
        raise ValueError(f"未対応のファイル形式です: {ext}")


def load_data_file_task(file_path, report_progress=None, is_cancelled=None):
    """
    read_data_file() + 列数バリデーションをまとめた、TaskRunner
    (gui/task_runner.py)に注入するための薄いラッパー(項目C-004フェーズ4)。
    read_data_file()自体はループを持たない単一のブロッキング呼び出しで
    自然な中断チェックポイントが存在しないため、report_progress/is_cancelled
    は(TaskRunner.run()が必ず渡してくるため)受け取るだけで使わない
    (core.analysis の fit_curve_task / gui/datasets/fitting.py の batch_fit_workerのうち
    単発フィット相当の「中断不能タスク」と同じ扱い)。
    """
    df = read_data_file(file_path)
    if len(df.columns) < 2:
        raise ValueError("データには少なくとも2列必要です。")
    return df
