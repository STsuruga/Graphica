"""データファイルの読み込み(TaskRunner で別スレッドで動かす関数)と、文字コード・区切り文字の判定。"""
import csv
import dataclasses
import re
import warnings

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


# 測定装置の書き出し(JASCO の TXT など)は、数値の表の前後に測定条件の行が付く。そういうファイルでだけ数値の表を探す
NUMERIC_TABLE_DELIMITERS = ('\t', ',', ';', ' ')
MIN_NUMERIC_TABLE_ROWS = 3


@dataclasses.dataclass
class NumericTable:
    first_line: int  # 0 始まり、表の最初の数値の行
    stop_line: int  # 表の最後の行の次
    delimiter: str
    header: list | None  # 表の直前の行が同じ列数の文字なら列名


def _split_numeric_row(line, delimiter):
    """2 列以上がすべて数値として読めれば、その列の文字列。読めなければ None。"""
    text = line.strip()
    fields = text.split() if delimiter == ' ' else [f.strip() for f in text.split(delimiter)]
    if len(fields) < 2:
        return None
    try:
        for field in fields:
            float(field)
    except ValueError:
        return None
    return fields


def find_numeric_table(lines):
    """列数のそろった数値の行が最も長く続くところ。MIN_NUMERIC_TABLE_ROWS 行に満たなければ None。"""
    best = None
    for delimiter in NUMERIC_TABLE_DELIMITERS:
        start, columns = None, 0
        for index, line in enumerate([*lines, '']):
            fields = _split_numeric_row(line, delimiter)
            if fields is not None and start is not None and len(fields) == columns:
                continue
            if start is not None and (best is None or index - start > best.stop_line - best.first_line):
                best = NumericTable(start, index, delimiter, None)
            start, columns = (index, len(fields)) if fields is not None else (None, 0)
    if best is None or best.stop_line - best.first_line < MIN_NUMERIC_TABLE_ROWS:
        return None
    if best.first_line > 0:
        above = lines[best.first_line - 1].strip()
        names = above.split() if best.delimiter == ' ' else [f.strip() for f in above.split(best.delimiter)]
        column_count = len(_split_numeric_row(lines[best.first_line], best.delimiter))
        if above and len(names) == column_count and _split_numeric_row(above, best.delimiter) is None:
            best.header = names
    return best


def read_numeric_table(file_path, encoding):
    """前後の説明の行を除いた数値の表を DataFrame にする。(DataFrame, NumericTable)、見つからなければ None。"""
    import io

    with open(file_path, encoding=encoding) as f:
        lines = f.read().splitlines()
    table = find_numeric_table(lines)
    if table is None:
        return None
    sep, engine = pandas_separator(table.delimiter)
    body = '\n'.join(line.strip() for line in lines[table.first_line:table.stop_line])
    df = pd.read_csv(io.StringIO(body), sep=sep, engine=engine, header=None)
    names = table.header or [f"列{i + 1}" for i in range(df.shape[1])]
    # 同じ列名は read_csv と同じく .1, .2 を付けて分ける
    seen = {}
    unique = []
    for name in names:
        count = seen.get(name, 0)
        unique.append(name if count == 0 else f"{name}.{count}")
        seen[name] = count + 1
    df.columns = unique
    return df, table


def has_numeric_column(df):
    return any(pd.api.types.is_numeric_dtype(df[column]) for column in df.columns)


# 年(4 桁の数字)を含む値だけを日付とみなす。"12:30" のような時刻だけの文字は、読んだ日の日付が補われてしまう
_YEAR_PATTERN = re.compile(r"\d{4}")


def parse_date_columns(df):
    """文字の列のうち、空でない値がすべて日付として読める列を日付型にする(Excel の日付の列と同じ扱い)。"""
    for column in df.columns:
        series = df[column]
        if series.dtype != object:
            continue
        text = series.dropna().astype(str).str.strip()
        text = text[text != ""]
        if text.empty or not text.map(lambda value: _YEAR_PATTERN.search(value) is not None).all():
            continue
        with warnings.catch_warnings():
            # 書式を推測できない警告と、タイムゾーンが混ざった列の将来の仕様変更の警告(その列は下で日付にしない)
            warnings.simplefilter("ignore", UserWarning)
            warnings.simplefilter("ignore", FutureWarning)
            try:
                # 書式は値ごとに読む(先頭の値の書式に合わせると、時刻のある値と無い値が混ざった列を読めない)
                parsed = pd.to_datetime(text, errors="coerce", format="mixed")
            except (ValueError, TypeError):
                continue
        # タイムゾーンが混ざると日付型にならない(object のまま)
        if parsed.isna().any() or not pd.api.types.is_datetime64_any_dtype(parsed):
            continue
        converted = pd.Series(pd.NaT, index=series.index, dtype=parsed.dtype)
        converted.loc[parsed.index] = parsed
        df[column] = converted
    return df


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
                df = pd.read_csv(file_path, header=0, encoding=encoding, sep=sep, engine=engine)
            except UnicodeDecodeError as e:
                last_error = e
                continue
            except pd.errors.ParserError as e:
                try:
                    found = read_numeric_table(file_path, encoding)
                except UnicodeDecodeError:
                    found = None
                if found is not None:
                    return parse_date_columns(found[0])
                last_error = e
                continue
            # 普通に読めて数値の列があるファイルは今までどおり。どの列も数値にならないときだけ、前後の説明の行を疑う
            if not has_numeric_column(df):
                found = read_numeric_table(file_path, encoding)
                if found is not None:
                    return parse_date_columns(found[0])
            return parse_date_columns(df)
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
