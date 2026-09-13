# plugins/jcamp_dx_importer/parser.py
"""
JCAMP-DX (.jdx/.dx) パーサ本体(項目P-101)。GUI/plugin機構いずれにも依存しない
プレーンなPythonモジュール(register_importer()に渡すloaderからimportして使う)。

JCAMP-DXは分光データ交換の標準形式(公開仕様)。データブロック(##XYDATA=(X++(Y..Y))
または##XYPOINTS=(XY..XY))を、ASDF(ASCII Squeezed Difference Format)という
文字圧縮方式で保持することが多く、正しく展開しないとY値が静かに壊れる
(誤ったスペクトルとして読み込まれる)ため、ASDFの疑似digitテーブルは
実際に公開・広く使われているRパッケージreadJDX(bryanhanson/readJDX、
175件超のファイルでテスト済みと明記)のソースコードと突き合わせて検証済みの
値を使っている(SQZ/DIF/DUPそれぞれのASCII文字→数値対応表)。
"""
import re

import pandas as pd

# --- ASDF疑似digitテーブル(readJDXのunSQZ.R/unDIF.R/repDUPs.Rで検証済み) ---

_SQZ_DIGITS = {
    '@': '0', 'A': '1', 'B': '2', 'C': '3', 'D': '4',
    'E': '5', 'F': '6', 'G': '7', 'H': '8', 'I': '9',
    'a': '-1', 'b': '-2', 'c': '-3', 'd': '-4', 'e': '-5',
    'f': '-6', 'g': '-7', 'h': '-8', 'i': '-9',
}
_DIF_DIGITS = {
    '%': '0', 'J': '1', 'K': '2', 'L': '3', 'M': '4',
    'N': '5', 'O': '6', 'P': '7', 'Q': '8', 'R': '9',
    'j': '-1', 'k': '-2', 'l': '-3', 'm': '-4', 'n': '-5',
    'o': '-6', 'p': '-7', 'q': '-8', 'r': '-9',
}
# DUPは「直前の値がこの回数ぶん出現する(元の1回分を含む)」という意味
# (readJDXのinsertDUPs.Rコメント: "T means repeat the value 2x, but this
# includes the original value"、McDonald 1988 sec.5.9参照)。
_DUP_LEADING_DIGIT = {
    'S': 1, 'T': 2, 'U': 3, 'V': 4, 'W': 5, 'X': 6, 'Y': 7, 'Z': 8, 's': 9,
}

_SQZ_CHARS = set(_SQZ_DIGITS)
_DIF_CHARS = set(_DIF_DIGITS)
_DUP_CHARS = set(_DUP_LEADING_DIGIT)
_ASDF_SPECIAL_CHARS = _SQZ_CHARS | _DIF_CHARS | _DUP_CHARS

# ASDF行を「符号付き数値」または「1文字の疑似digit(+続く数字、DUPの複数桁対応)」に
# 分割する正規表現。数値トークンは行頭以外では符号(+/-)の直前で新しいトークンとして
# 区切られる(JCAMP-DXの慣例通り、符号無し継続はPACの空白区切りのみ許容)。
_TOKEN_PATTERN = re.compile(
    r'[+-]?\d+\.?\d*(?:[eE][+-]?\d+)?'  # 符号付き数値(PAC/AFFN)
    r'|[' + re.escape(''.join(_ASDF_SPECIAL_CHARS)) + r']\d*'  # 疑似digit(+続く数字、DUPの多桁対応)
)


class JcampDxParseError(ValueError):
    """JCAMP-DXファイルの解析に失敗したことを表す例外。"""


def _parse_header(text):
    """
    ##KEY=VALUE 形式のヘッダ行を辞書にする(キーは大文字・空白/アンダースコア
    除去で正規化、JCAMP-DXの慣例に合わせる: ##XUNITS= と##X UNITS=は同じキー扱い)。
    """
    header = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith('##'):
            continue
        if '=' not in line:
            continue
        key, _, value = line[2:].partition('=')
        normalized_key = re.sub(r'[\s_]', '', key).upper()
        header[normalized_key] = value.strip()
    return header


def _decode_asdf_line(line):
    """
    1行分のASDFデータ("X値 Y値... "の並び、SQZ/DIF/DUP/PAC混在可)を、
    数値のリストに展開する。先頭は必ずX値(PAC/AFFNの生数値)。
    """
    tokens = _TOKEN_PATTERN.findall(line)
    if not tokens:
        return []

    values = []
    for i, token in enumerate(tokens):
        first_char = token[0]
        if first_char in _DUP_CHARS:
            if not values:
                raise JcampDxParseError(f"DUPコードの直前に値がありません: {line!r}")
            count_str = str(_DUP_LEADING_DIGIT[first_char]) + token[1:]
            count = int(count_str)
            # ★ DUPは「直前の値を、元の1回分を含めて合計count回出現させる」ため、
            #   既にvaluesへ追加済みの直前の1件を除いた残り(count - 1)件を追加する。
            previous_value = values[-1]
            values.extend([previous_value] * (count - 1))
            continue

        if first_char in _SQZ_CHARS:
            numeric_str = _SQZ_DIGITS[first_char] + token[1:]
            values.append(float(numeric_str))
            continue

        if first_char in _DIF_CHARS:
            if not values:
                raise JcampDxParseError(f"DIFコードの直前に値がありません: {line!r}")
            delta_str = _DIF_DIGITS[first_char] + token[1:]
            values.append(values[-1] + float(delta_str))
            continue

        # PAC/AFFN: 符号付きの通常の数値
        values.append(float(token))

    return values


def _parse_xydata_block(lines, x_factor, y_factor):
    """
    ##XYDATA=(X++(Y..Y)) ブロックを展開する。各行は「その行の先頭Y値に対応する
    X値(生値、x_factor適用前)」+「Y値の並び(ASDF混在可)」という構成。
    先頭のX値はデコード後の値の並びの中の1番目として扱われる(X++(Y..Y)の
    "X++"はX値がその行の最初のYと対になっていることを示す慣例のため)。
    """
    all_y_raw = []
    for raw_line in lines:
        raw_line = raw_line.strip()
        if not raw_line or raw_line.startswith('##') or raw_line.startswith('$$'):
            continue
        decoded = _decode_asdf_line(raw_line)
        if not decoded:
            continue
        # 各行の先頭要素はX値(チェック用、Y値ではない)なので除いて残りをY値とする。
        all_y_raw.extend(decoded[1:])
    return [value * y_factor for value in all_y_raw]


def _parse_xypoints_block(lines, x_factor, y_factor):
    """
    ##XYPOINTS=(XY..XY) ブロック(圧縮無しの明示的な x,y ペア羅列)を展開する。
    カンマまたは空白区切り、1行に複数ペアが並ぶこともある。
    """
    x_values, y_values = [], []
    text = ' '.join(
        raw_line.strip() for raw_line in lines
        if raw_line.strip() and not raw_line.strip().startswith('##') and not raw_line.strip().startswith('$$')
    )
    pair_pattern = re.compile(r'([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)\s*,\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)')
    for match in pair_pattern.finditer(text):
        x_values.append(float(match.group(1)) * x_factor)
        y_values.append(float(match.group(2)) * y_factor)
    return x_values, y_values


def parse_jcamp_dx(text):
    """
    JCAMP-DXファイルの内容(文字列)を解析し、2列(X/Y)のpandas.DataFrameを返す。
    複数ブロック(LINK形式)のファイルは、最初に見つかったデータブロックのみを
    対象とする(項目P-101の初版スコープ。複数スペクトルの分離は将来の拡張点)。
    """
    header = _parse_header(text)
    lines = text.splitlines()

    x_factor = float(header.get('XFACTOR', '1') or '1')
    y_factor = float(header.get('YFACTOR', '1') or '1')

    xydata_start = None
    xypoints_start = None
    block_kind = None
    for i, line in enumerate(lines):
        stripped = line.strip().upper()
        if stripped.startswith('##XYDATA'):
            xydata_start = i
            block_kind = 'XYDATA'
            break
        if stripped.startswith('##XYPOINTS'):
            xypoints_start = i
            block_kind = 'XYPOINTS'
            break

    if block_kind is None:
        raise JcampDxParseError("##XYDATA または ##XYPOINTS ブロックが見つかりませんでした。")

    block_start = xydata_start if block_kind == 'XYDATA' else xypoints_start
    block_lines = []
    for line in lines[block_start + 1:]:
        if line.strip().startswith('##'):
            break  # 次のヘッダ/ブロックに到達したら終了
        block_lines.append(line)

    x_label = header.get('XUNITS', 'X')
    y_label = header.get('YUNITS', 'Y')

    if block_kind == 'XYPOINTS':
        x_values, y_values = _parse_xypoints_block(block_lines, x_factor, y_factor)
        if not x_values:
            raise JcampDxParseError("##XYPOINTS ブロックからデータ点を抽出できませんでした。")
        return pd.DataFrame({x_label: x_values, y_label: y_values})

    # XYDATA: X値はFIRSTX/LASTX/NPOINTSから等間隔に再構成する(各行先頭のX値は
    # チェック用としてのみ使い、実際のX配列生成には使わない — 実装を単純化しつつ、
    # 標準的なJCAMP-DXパーサ(readJDX等)でも広く採られている方式)。
    try:
        first_x = float(header['FIRSTX']) * x_factor
        last_x = float(header['LASTX']) * x_factor
        n_points = int(float(header['NPOINTS']))
    except (KeyError, ValueError) as e:
        raise JcampDxParseError(f"FIRSTX/LASTX/NPOINTSヘッダが不足または不正です: {e}") from e

    y_values = _parse_xydata_block(block_lines, x_factor, y_factor)
    if len(y_values) != n_points:
        raise JcampDxParseError(
            f"展開後のY値の点数({len(y_values)})がNPOINTS({n_points})と一致しません"
            "(ASDFの展開に失敗している可能性があります)。"
        )

    if n_points == 1:
        x_values = [first_x]
    else:
        step = (last_x - first_x) / (n_points - 1)
        x_values = [first_x + i * step for i in range(n_points)]

    return pd.DataFrame({x_label: x_values, y_label: y_values})
