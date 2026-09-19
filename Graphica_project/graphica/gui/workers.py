"""データファイルの読み込み(TaskRunner で別スレッドで動かす関数)と、文字コード・区切り文字の判定。"""
import csv
import pandas as pd

# 順に試す文字コード。utf-8-sig は BOM の有無どちらの UTF-8 も読める。latin-1 は必ず読める最後の手段。
# UTF-16 は入れない(cp932 や latin-1 が例外を出さずに化けた結果を返す)。BOM で別に見分ける。
CSV_ENCODING_FALLBACKS = ['utf-8-sig', 'cp932', 'latin-1']

# 組み込みで読める拡張子。開くダイアログ、ドラッグ&ドロップ、フォルダ一括取り込み、プレビューがすべてここを見る。
# 区切り文字付きテキストは CSV と同じく文字コードと区切りを判定する。.xlsx は openpyxl、.xls は xlrd。
DELIMITED_TEXT_EXTENSIONS = ('.csv', '.txt')
EXCEL_EXTENSIONS = ('.xlsx', '.xls')
BUILTIN_DATA_FILE_EXTENSIONS = DELIMITED_TEXT_EXTENSIONS + EXCEL_EXTENSIONS


def is_delimited_text_file(file_path):
    return bool(file_path) and file_path.lower().endswith(DELIMITED_TEXT_EXTENSIONS)


def is_excel_file(file_path):
    return bool(file_path) and file_path.lower().endswith(EXCEL_EXTENSIONS)


def excel_engine_for(file_path):
    """openpyxl は .xls を読めないので、拡張子で xlrd と使い分ける。"""
    return 'xlrd' if file_path.lower().endswith('.xls') else 'openpyxl'


def pandas_separator(delimiter):
    """(sep, engine)。空白は空白の連続とみなす(桁揃えの空白で空の列が大量にできないように)。正規表現は python エンジン。"""
    if delimiter == ' ':
        return r'\s+', 'python'
    if len(delimiter) == 1:
        return delimiter, 'c'
    return delimiter, 'python'


def _detect_bom_encoding(file_path):
    """BOM から文字コードを判定する。無ければ None。"""
    with open(file_path, 'rb') as f:
        head = f.read(4)
    if head.startswith(b'\xff\xfe') or head.startswith(b'\xfe\xff'):
        return 'utf-16'
    if head.startswith(b'\xef\xbb\xbf'):
        return 'utf-8-sig'
    return None


def _csv_encoding_candidates(file_path):
    """BOM の判定を先頭に、CSV_ENCODING_FALLBACKS を並べた候補(読み込みと判定で順序を共有する)。"""
    bom_encoding = _detect_bom_encoding(file_path)
    candidates = [bom_encoding] if bom_encoding else []
    candidates += [e for e in CSV_ENCODING_FALLBACKS if e not in candidates]
    return candidates


def detect_csv_encoding(file_path):
    """テキストとしてデコードできる最初の文字コード。DataFrame にはしないので軽い。"""
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
    """カンマ・タブ・セミコロン・空白のどれかを推測する。判定できなければカンマ。"""
    if not sample_text.strip():
        return ','
    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters=',\t; ')
        return dialect.delimiter
    except csv.Error:
        return ','


def detect_csv_delimiter(file_path, encoding, sample_lines=50):
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
    """クリップボードの区切り文字(Excel からのコピーはタブ、CSV の文字列ならカンマなど)。"""
    sample = ''.join(text.splitlines(keepends=True)[:sample_lines])
    return _sniff_delimiter_from_text(sample)


def read_data_file(file_path):
    """データファイルを DataFrame にする。プラグインがその拡張子を登録していればそちらを使う。"""
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
        # 区切り文字もここで推測する(カンマで読むとタブ区切りが1列に潰れ、「2列以上必要」で弾かれる)
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
    """TaskRunner 用。読み込みは中断できないので、report_progress と is_cancelled は受け取るだけ。"""
    df = read_data_file(file_path)
    if len(df.columns) < 2:
        raise ValueError("データには少なくとも2列必要です。")
    return df
