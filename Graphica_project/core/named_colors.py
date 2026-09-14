# core/named_colors.py
"""
「名前付きの色」の登録簿。

用途は「複数の種類のデータで、同じ物質には同じ色を使いたい」。試料名や条件名に
色を1つ結び付けて登録しておき、データセットの色を選ぶときにその名前から選べる
ようにする。

**既存の「配色パレット」(gui/mixins/dataset_mixin.py の COLOR_PALETTES_SETTINGS_KEY、
core/color_palettes.py の BUILTIN_PALETTES)とは別物**なので、QSettings のキーも
分けてある:

- 配色パレット = 「系列に順番に割り当てるための、**順序付きの色のリスト**」。
  1つのパレットが N 色を持ち、名前はパレット全体に付く。
- こちら       = 「**1つの名前に1つの色**」。N 個の独立した登録が並ぶ。

同じ入れ物に押し込むと、パレット管理側(色の追加/削除、アクティブなパレットの
切り替え)の意味が壊れるため、統合しない。

このモジュールは GUI にも Qt にも依存しない純粋なロジックだけを持つ
(QSettings オブジェクトは `value()`/`setValue()` を持つ何かとしてしか扱わない)。
保存形式は、このリポジトリの慣習どおり **JSON文字列** (CLAUDE.md「Settings and
autosave」参照)。
"""
import json
import re

# QSettings のキー。ユーザー単位・全プロジェクト共通で保持する(ユーザー判断:
# 「同じ物質はいつも同じ色」が目的なので、プロジェクトをまたいで効いてほしい)。
NAMED_COLORS_SETTINGS_KEY = "named_colors_json"

# 登録名の最大長。長すぎる名前はポップアップメニューの幅を壊すだけなので上限を切る。
MAX_NAME_LENGTH = 60

_HEX_RE = re.compile(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$')


class NamedColorError(ValueError):
    """登録名・色コードが不正な場合に送出する(呼び出し側がメッセージを表示する)。"""


def normalize_color(value):
    """
    色コードを `#rrggbb`(小文字)へ正規化する。`#rgb` の短縮形も受け付ける。

    QColor を使わずに自前で判定しているのは、このモジュールを QApplication の
    無い環境でも単体テストできるようにするため。
    """
    text = (value or "").strip()
    if not _HEX_RE.match(text):
        raise NamedColorError(f"色コードが不正です: {value!r}(例: #1f77b4)")
    text = text.lower()
    if len(text) == 4:  # #rgb -> #rrggbb
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
    QSettings から登録済みの色を読み出す。

    戻り値は `{'name': str, 'color': '#rrggbb'}` の **リスト**(辞書ではない)。
    ユーザーが並べ替えた順序そのものに意味があるため、順序を保てる形にしている。

    壊れた JSON・想定外の形・不正な色は**黙って捨てて**、読めたものだけを返す
    (設定ファイルが壊れていてもアプリが起動しなくなるより、登録が消えている方が
    まだ復帰しやすいため。プラグインマニフェストのように「入口で厳しく弾く」
    必要がある場所とは方針が異なる)。
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
    """登録リストを QSettings へ書き戻す(JSON文字列として)。"""
    payload = [{"name": e["name"], "color": e["color"]} for e in entries]
    settings.setValue(NAMED_COLORS_SETTINGS_KEY, json.dumps(payload, ensure_ascii=False))


def find_index_by_name(entries, name):
    """登録名から位置を探す。見つからなければ -1。比較は前後の空白を除いた完全一致。"""
    target = (name or "").strip()
    for index, entry in enumerate(entries):
        if entry["name"] == target:
            return index
    return -1


def add_named_color(entries, name, color):
    """
    1件追加した**新しいリスト**を返す(引数のリストは変更しない)。

    ユーザー判断により**登録名の重複は禁止**。名前→色が1対1でないと、
    一括適用や将来の自動割り当てで「どちらの色か」が決まらないため。
    """
    name = normalize_name(name)
    color = normalize_color(color)
    if find_index_by_name(entries, name) != -1:
        raise NamedColorError(f"「{name}」は既に登録されています。")
    return list(entries) + [{"name": name, "color": color}]


def update_named_color(entries, index, name, color):
    """index の登録を書き換えた新しいリストを返す。自分自身との名前衝突は許す。"""
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
    """index の登録を除いた新しいリストを返す。"""
    if not 0 <= index < len(entries):
        raise NamedColorError("削除対象が選択されていません。")
    updated = list(entries)
    del updated[index]
    return updated


def move_named_color(entries, index, offset):
    """
    index の登録を offset だけ動かした新しいリストを返す。並び順はポップアップの
    表示順にそのまま使われるため、よく使う色を上へ持って行けるようにする。
    端を越える移動は何もしない(ボタンを押しても無反応、という素直な挙動)。
    """
    if not 0 <= index < len(entries):
        raise NamedColorError("移動対象が選択されていません。")
    new_index = index + offset
    if not 0 <= new_index < len(entries):
        return list(entries)
    updated = list(entries)
    updated.insert(new_index, updated.pop(index))
    return updated
