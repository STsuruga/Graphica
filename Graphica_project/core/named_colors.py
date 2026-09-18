"""
名前付きの色の登録簿。試料名や条件名に色を1つ結び付け、同じ物質をどのプロジェクトでも
同じ色で描けるようにする。

配色パレット(core/color_palettes.py)とは別物で、QSettings のキーも分けている。
パレットは系列に順に割り当てる色のリスト、こちらは名前1つに色1つ。1つにまとめると
パレット管理の「アクティブなパレット」の意味が壊れる。

Qt に依存しない(settings は value()/setValue() を持つものとしてだけ扱う)ので、
QApplication なしで単体テストできる。
"""
import json
import re

# プロジェクトをまたいで効かせるため、ユーザー単位の QSettings に置く。
# 並び順がポップアップの表示順なので、辞書ではなく JSON の配列で保存する。
NAMED_COLORS_SETTINGS_KEY = "named_colors_json"

MAX_NAME_LENGTH = 60  # 長い名前はポップアップメニューの幅を壊す

# ポップアップに直接並べる件数。超えた分は「すべての登録色...」から検索して選ぶ。
POPUP_LIMIT = 5

_HEX_RE = re.compile(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$')


class NamedColorError(ValueError):
    """登録名・色コードが不正。メッセージはそのまま利用者に表示できる。"""


def normalize_color(value):
    """色コードを `#rrggbb`(小文字)にする。`#rgb` も受け付ける。"""
    text = (value or "").strip()
    if not _HEX_RE.match(text):
        raise NamedColorError(f"色コードが不正です: {value!r}(例: #1f77b4)")
    text = text.lower()
    if len(text) == 4:
        text = "#" + "".join(ch * 2 for ch in text[1:])
    return text


def normalize_name(value):
    """登録名の前後の空白を落として検証する。"""
    name = (value or "").strip()
    if not name:
        raise NamedColorError("登録名を入力してください。")
    if len(name) > MAX_NAME_LENGTH:
        raise NamedColorError(f"登録名が長すぎます({MAX_NAME_LENGTH}文字まで)。")
    return name


def load_named_colors(settings):
    """
    登録済みの色を `[{'name': str, 'color': '#rrggbb'}, ...]` で返す。

    壊れたエントリは1件ずつ捨て、読めたものだけ返す。設定ファイルが壊れても
    起動できなくなるより、登録が一部消える方が復帰しやすい。
    """
    raw = settings.value(NAMED_COLORS_SETTINGS_KEY, "")
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []

    entries = []
    seen = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            name = normalize_name(item.get("name"))
            color = normalize_color(item.get("color"))
        except NamedColorError:
            continue
        if name in seen:
            continue
        seen.add(name)
        entries.append({"name": name, "color": color})
    return entries


def save_named_colors(settings, entries):
    payload = [{"name": e["name"], "color": e["color"]} for e in entries]
    settings.setValue(NAMED_COLORS_SETTINGS_KEY, json.dumps(payload, ensure_ascii=False))


def find_index_by_name(entries, name):
    """登録名の位置を返す(前後の空白を除いた完全一致)。なければ -1。"""
    target = (name or "").strip()
    for index, entry in enumerate(entries):
        if entry["name"] == target:
            return index
    return -1


# 以下の編集関数は、引数のリストを変えずに新しいリストを返す。


def add_named_color(entries, name, color):
    """名前の重複は禁止。名前と色が1対1でないと、名前から色が決まらない。"""
    name = normalize_name(name)
    color = normalize_color(color)
    if find_index_by_name(entries, name) != -1:
        raise NamedColorError(f"「{name}」は既に登録されています。")
    return list(entries) + [{"name": name, "color": color}]


def update_named_color(entries, index, name, color):
    """自分自身と同じ名前のままの更新は許す。"""
    if not 0 <= index < len(entries):
        raise NamedColorError("編集対象が選択されていません。")
    name = normalize_name(name)
    color = normalize_color(color)
    existing = find_index_by_name(entries, name)
    if existing != -1 and existing != index:
        raise NamedColorError(f"「{name}」は既に登録されています。")
    updated = list(entries)
    updated[index] = {"name": name, "color": color}
    return updated


def remove_named_color(entries, index):
    if not 0 <= index < len(entries):
        raise NamedColorError("削除対象が選択されていません。")
    updated = list(entries)
    del updated[index]
    return updated


def move_named_color(entries, index, offset):
    """端を越える移動は何もしない。"""
    if not 0 <= index < len(entries):
        raise NamedColorError("移動対象が選択されていません。")
    new_index = index + offset
    if not 0 <= new_index < len(entries):
        return list(entries)
    updated = list(entries)
    updated.insert(new_index, updated.pop(index))
    return updated
