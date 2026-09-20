"""
名前付きの色の登録簿(名前1つに色1つ)。同じ物質をどのプロジェクトでも同じ色で描くためのもの。
配色パレット(core/color_palettes.py、順序付きの色のリスト)と混ぜると、パレット管理の
「アクティブなパレット」の意味が壊れるので、QSettings のキーから別にしている。
"""
import json
import re
from typing import Any

# 並び順がポップアップの表示順なので、辞書ではなく JSON の配列で保存する。
NAMED_COLORS_SETTINGS_KEY = "named_colors_json"

MAX_NAME_LENGTH = 60
POPUP_LIMIT = 5  # これを超えた分は「すべての登録色...」から選ぶ

_HEX_RE = re.compile(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$')


class NamedColorError(ValueError):
    """メッセージはそのまま利用者に表示する。"""


def normalize_color(value: Any) -> str:
    """`#rgb` / `#rrggbb` を小文字の `#rrggbb` にする。QColor を使わないのは Qt 非依存にするため。"""
    text = (value or "").strip()
    if not _HEX_RE.match(text):
        raise NamedColorError(f"色コードが不正です: {value!r}(例: #1f77b4)")
    text = text.lower()
    if len(text) == 4:
        text = "#" + "".join(ch * 2 for ch in text[1:])
    return text


def normalize_name(value: Any) -> str:
    name = (value or "").strip()
    if not name:
        raise NamedColorError("登録名を入力してください。")
    if len(name) > MAX_NAME_LENGTH:
        raise NamedColorError(f"登録名が長すぎます({MAX_NAME_LENGTH}文字まで)。")
    return name


def load_named_colors(settings: Any) -> list[dict[str, str]]:
    """壊れたエントリは1件ずつ捨てる。設定が壊れても起動できなくなるよりは、登録が一部消える方がよい。"""
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


def save_named_colors(settings: Any, entries: list[dict[str, str]]) -> None:
    payload = [{"name": e["name"], "color": e["color"]} for e in entries]
    settings.setValue(NAMED_COLORS_SETTINGS_KEY, json.dumps(payload, ensure_ascii=False))


def find_index_by_name(entries: list[dict[str, str]], name: str) -> int:
    target = (name or "").strip()
    for index, entry in enumerate(entries):
        if entry["name"] == target:
            return index
    return -1


# 編集関数はどれも、引数のリストを変えずに新しいリストを返す。


def add_named_color(entries: list[dict[str, str]], name: object, color: object) -> list[dict[str, str]]:
    # 名前と色が1対1でないと、名前から色が決まらないので重複は禁止。
    name = normalize_name(name)
    color = normalize_color(color)
    if find_index_by_name(entries, name) != -1:
        raise NamedColorError(f"「{name}」は既に登録されています。")
    return list(entries) + [{"name": name, "color": color}]


def update_named_color(entries: list[dict[str, str]], index: int, name: object, color: object) -> list[dict[str, str]]:
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


def remove_named_color(entries: list[dict[str, str]], index: int) -> list[dict[str, str]]:
    if not 0 <= index < len(entries):
        raise NamedColorError("削除対象が選択されていません。")
    updated = list(entries)
    del updated[index]
    return updated


def move_named_color(entries: list[dict[str, str]], index: int, offset: int) -> list[dict[str, str]]:
    if not 0 <= index < len(entries):
        raise NamedColorError("移動対象が選択されていません。")
    new_index = index + offset
    if not 0 <= new_index < len(entries):
        return list(entries)
    updated = list(entries)
    updated.insert(new_index, updated.pop(index))
    return updated
