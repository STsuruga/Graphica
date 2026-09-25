"""特性テストの記録器: 今の挙動を JSON に落とし、golden/ の基準と比べる。

基準を作り直すのは scripts/update_characterization.py(環境変数 GRAPHICA_UPDATE_GOLDEN=1)だけ。
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import platform
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
UPDATE_ENV = "GRAPHICA_UPDATE_GOLDEN"
# 画素の比較に失敗したときの PNG と差分画像。リポジトリを重くしないよう一時フォルダに置く。
ARTIFACT_DIR = Path(tempfile.gettempdir()) / "graphica-characterization"
# 差分画像を作るための手元の画像。基準にはハッシュしか持たない。
IMAGE_CACHE_DIR = Path(__file__).resolve().parents[2] / ".characterization_images"

# 画素はこの版の組み合わせでしか一致しない(ENVIRONMENT.md)。
PIXEL_ENVIRONMENT = {
    "os": "Windows",
    "PySide6": "6.9.1",
    "matplotlib": "3.10.7",
    "numpy": "2.3.1",
}

# OS 間で最後の桁が揺れる計算結果を同じ値として扱うための有効桁数。
FLOAT_DIGITS = 10
MAX_DIFF_LINES = 40


def updating() -> bool:
    return os.environ.get(UPDATE_ENV) == "1"


def pixel_environment_matches() -> bool:
    import matplotlib
    import PySide6

    actual = {
        "os": platform.system(),
        "PySide6": PySide6.__version__,
        "matplotlib": matplotlib.__version__,
        "numpy": np.__version__,
    }
    return actual == PIXEL_ENVIRONMENT


# --- 正規化 ---

class Normalizer:
    """一時パスや版の文字列など、実行ごと・環境ごとに変わる部分を置き換える。"""

    def __init__(self, replacements: dict[str, str] | None = None):
        from graphica.core.version import __version__

        self.replacements: dict[str, str] = {}
        for path in (tempfile.gettempdir(),):
            self.add_path(path, "<TMP>")
        self.replacements[__version__] = "<VERSION>"
        for text, token in (replacements or {}).items():
            self.replacements[text] = token

    def add_path(self, path: str | os.PathLike, token: str) -> None:
        text = str(path)
        variants = {text, text.replace("\\", "/"), os.path.realpath(text), os.path.realpath(text).replace("\\", "/")}
        for variant in variants:
            if variant:
                self.replacements[variant] = token

    def text(self, value: str) -> str:
        # 長いものから置き換えないと、一時パスの中の短いパスが先に当たる
        for old in sorted(self.replacements, key=len, reverse=True):
            if old and old in value:
                value = value.replace(old, self.replacements[old])
        return value

    def __call__(self, value: Any) -> Any:
        return to_jsonable(value, self)


def _float(value: float) -> Any:
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Infinity" if value > 0 else "-Infinity"
    rounded = float(f"{value:.{FLOAT_DIGITS}g}")
    return 0.0 if rounded == 0 else rounded


def to_jsonable(value: Any, normalizer: Normalizer | None = None) -> Any:
    """比べられる形(JSON に書けて、実行ごとに変わらない形)にする。"""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return _float(float(value))
    if isinstance(value, str):
        return normalizer.text(value) if normalizer else value
    if isinstance(value, bytes):
        return {"bytes_sha256": hashlib.sha256(value).hexdigest(), "len": len(value)}
    if isinstance(value, Path):
        return to_jsonable(str(value), normalizer)
    if isinstance(value, dict):
        return {str(to_jsonable(k, normalizer)): to_jsonable(v, normalizer) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v, normalizer) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted((to_jsonable(v, normalizer) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(value, np.ndarray):
        return array_summary(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name), normalizer) for f in dataclasses.fields(value)}
    if hasattr(value, "name") and hasattr(value, "value") and type(value).__module__.startswith(("PySide6", "enum")):
        return f"{type(value).__name__}.{value.name}"
    return f"<{type(value).__name__}>"


def array_summary(values: Any) -> dict[str, Any]:
    """配列を「形・型・値のハッシュ」にする。値は有効桁で丸めてから数える。"""
    array = np.asarray(values)
    summary: dict[str, Any] = {"shape": list(array.shape), "dtype": str(array.dtype)}
    if array.dtype.kind in "fc":
        flat = array.astype(complex if array.dtype.kind == "c" else float).ravel()
        tokens = [json.dumps(_float(v)) if array.dtype.kind == "f" else json.dumps([_float(v.real), _float(v.imag)])
                  for v in flat]
        payload = "|".join(tokens)
    elif array.dtype.kind == "M":
        payload = "|".join(str(v) for v in array.ravel())
    elif array.dtype.kind == "O":
        payload = "|".join(json.dumps(to_jsonable(v)) for v in array.ravel())
    else:
        payload = "|".join(str(v) for v in array.ravel().tolist())
    summary["sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return summary


# --- 基準との比較 ---

def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        if not value:
            return {prefix or "/": {}}
        out: dict[str, Any] = {}
        for key, item in value.items():
            out.update(_flatten(item, f"{prefix}/{key}"))
        return out
    if isinstance(value, list):
        if not value:
            return {prefix or "/": []}
        out = {}
        for index, item in enumerate(value):
            out.update(_flatten(item, f"{prefix}[{index}]"))
        return out
    return {prefix or "/": value}


def diff_summary(expected: Any, actual: Any, limit: int = MAX_DIFF_LINES) -> str:
    """どこがどう違うかを、パスごとに 1 行で並べる。"""
    left, right = _flatten(expected), _flatten(actual)
    lines = []
    for key in sorted(set(left) | set(right)):
        if key not in right:
            lines.append(f"- {key}: {left[key]!r}")
        elif key not in left:
            lines.append(f"+ {key}: {right[key]!r}")
        elif left[key] != right[key]:
            lines.append(f"~ {key}: {left[key]!r} -> {right[key]!r}")
    if len(lines) > limit:
        lines = lines[:limit] + [f"... ほか {len(lines) - limit} 件"]
    return "\n".join(lines)


def golden_path(name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_\-/.]+", name) or ".." in name:
        raise ValueError(f"基準の名前に使えない文字がある: {name!r}")
    return GOLDEN_DIR / f"{name}.json"


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def check(name: str, value: Any, normalizer: Normalizer | None = None) -> None:
    """value(正規化済みでなくてよい)を基準 golden/<name>.json と比べる。"""
    actual = to_jsonable(value, normalizer or Normalizer())
    # 一度 JSON を往復させ、キーの型などを基準と同じ形にそろえる
    actual = json.loads(_dump(actual))
    path = golden_path(name)
    if updating():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_dump(actual), encoding="utf-8", newline="\n")
        return
    if not path.exists():
        raise AssertionError(f"基準 {path.name} が無い。scripts/update_characterization.py で作る")
    expected = json.loads(path.read_text(encoding="utf-8"))
    if expected != actual:
        raise AssertionError(f"特性テスト {name} が基準と違う:\n{diff_summary(expected, actual)}")


# --- 画素 ---

def rgba_of_figure(figure) -> np.ndarray:
    if not hasattr(figure.canvas, "buffer_rgba"):
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        FigureCanvasAgg(figure)
    figure.canvas.draw()
    return np.asarray(figure.canvas.buffer_rgba()).copy()


def pixel_hash(rgba: np.ndarray) -> str:
    rgba = np.ascontiguousarray(rgba)
    header = f"{rgba.shape}|{rgba.dtype}|".encode()
    return hashlib.sha256(header + rgba.tobytes()).hexdigest()


def _write_png(path: Path, rgba: np.ndarray) -> None:
    import matplotlib.image as mpimg

    path.parent.mkdir(parents=True, exist_ok=True)
    mpimg.imsave(path, rgba)


def _write_diff(path: Path, expected: np.ndarray, actual: np.ndarray) -> None:
    if expected.shape != actual.shape:
        return
    changed = np.any(expected != actual, axis=-1)
    diff = np.zeros_like(actual)
    diff[..., 3] = 255
    diff[..., :3] = (actual[..., :3] // 4)
    diff[changed] = (255, 0, 255, 255)
    _write_png(path, diff)


def check_pixels(name: str, images: dict[str, np.ndarray]) -> None:
    """画素のハッシュを golden/<name>.pixels.json と比べる。ピンした環境でないときは何もしない。"""
    if not pixel_environment_matches():
        return
    hashes = {key: pixel_hash(rgba) for key, rgba in images.items()}
    path = golden_path(f"{name}.pixels")
    cache_dir = IMAGE_CACHE_DIR / name
    if updating():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_dump(hashes), encoding="utf-8", newline="\n")
        for key, rgba in images.items():
            _write_png(cache_dir / f"{key}.png", rgba)
        return
    if not path.exists():
        raise AssertionError(f"画素の基準 {path.name} が無い。scripts/update_characterization.py で作る")
    expected = json.loads(path.read_text(encoding="utf-8"))
    mismatched = sorted(k for k in set(expected) | set(hashes) if expected.get(k) != hashes.get(k))
    if not mismatched:
        return
    out_dir = ARTIFACT_DIR / name
    notes = []
    for key in mismatched:
        if key not in images:
            notes.append(f"- {key}: 描かれなくなった")
            continue
        _write_png(out_dir / f"{key}.actual.png", images[key])
        cached = cache_dir / f"{key}.png"
        if cached.exists():
            import matplotlib.image as mpimg

            before = (mpimg.imread(cached) * 255).round().astype(np.uint8)
            _write_diff(out_dir / f"{key}.diff.png", before, images[key])
        notes.append(f"~ {key}" if key in expected else f"+ {key}: 基準に無い")
    raise AssertionError(f"特性テスト {name} の画素が基準と違う(画像は {out_dir}):\n" + "\n".join(notes))


# --- 記録する対象ごとの要約 ---

def color_hex(color: Any) -> Any:
    from matplotlib.colors import to_hex

    try:
        return to_hex(color, keep_alpha=True)
    except (ValueError, TypeError):
        return to_jsonable(color)


def signal_receivers(obj) -> dict[str, int]:
    """接続先が 1 つ以上ある信号ごとの接続数(組み立ての配線が変わっていないことを見る)。"""
    from PySide6.QtCore import SIGNAL, QMetaMethod

    counts: dict[str, int] = {}
    meta = obj.metaObject()
    for index in range(meta.methodCount()):
        method = meta.method(index)
        if method.methodType() != QMetaMethod.MethodType.Signal:
            continue
        signature = bytes(method.methodSignature()).decode()
        # PySide は Python の包みを持つオブジェクトの destroyed に自分で接続するので、数えると参照の有無で揺れる
        if signature.startswith("destroyed("):
            continue
        count = obj.receivers(SIGNAL(signature))
        if count:
            counts[signature] = count
    return counts


def widget_tree(widget, root=None, signals: bool = False) -> dict[str, Any]:
    """ウィジェットの木。子は Qt の子の順(= 作られた順)に並べる。"""
    from PySide6.QtWidgets import (
        QAbstractButton,
        QAbstractSpinBox,
        QComboBox,
        QGroupBox,
        QLabel,
        QLineEdit,
        QWidget,
    )

    root = root or widget
    node: dict[str, Any] = {"class": type(widget).__name__}
    if widget.objectName():
        node["name"] = widget.objectName()
    if isinstance(widget, (QAbstractButton, QLabel, QLineEdit)):
        node["text"] = widget.text()
    if isinstance(widget, QAbstractButton) and widget.isCheckable():
        node["checked"] = widget.isChecked()
    if isinstance(widget, QGroupBox):
        node["title"] = widget.title()
        if widget.isCheckable():
            node["checked"] = widget.isChecked()
    if isinstance(widget, QComboBox):
        node["items"] = [widget.itemText(i) for i in range(widget.count())]
        node["current"] = widget.currentIndex()
    if isinstance(widget, QAbstractSpinBox):
        node["value"] = widget.text()
    if widget.windowTitle() and widget.isWindow():
        node["window_title"] = widget.windowTitle()
    node["visible"] = widget.isVisibleTo(root) if widget is not root else not widget.isHidden()
    node["enabled"] = widget.isEnabled()
    if widget.toolTip():
        node["tooltip"] = widget.toolTip()
    if signals:
        receivers = signal_receivers(widget)
        if receivers:
            node["receivers"] = receivers
    children = [widget_tree(child, root, signals) for child in widget.children() if isinstance(child, QWidget)]
    if children:
        node["children"] = children
    return node


def menu_tree(menu, signals: bool = False) -> list[dict[str, Any]]:
    items = []
    for action in menu.actions():
        if action.isSeparator():
            items.append({"separator": True})
            continue
        item: dict[str, Any] = {"text": action.text()}
        if action.shortcut().toString():
            item["shortcut"] = action.shortcut().toString()
        if action.isCheckable():
            item["checked"] = action.isChecked()
        if not action.isEnabled():
            item["enabled"] = False
        if not action.isVisible():
            item["visible"] = False
        if action.toolTip() and action.toolTip() != action.text().replace("&", ""):
            item["tooltip"] = action.toolTip()
        if signals:
            receivers = signal_receivers(action)
            if receivers:
                item["receivers"] = receivers
        if action.menu() is not None:
            item["submenu"] = menu_tree(action.menu(), signals)
        items.append(item)
    return items


def artist_style(artist) -> dict[str, Any]:
    state: dict[str, Any] = {"class": type(artist).__name__}
    for getter in ("get_label", "get_color", "get_linestyle", "get_linewidth", "get_marker", "get_markersize",
                   "get_alpha", "get_zorder", "get_visible"):
        if hasattr(artist, getter):
            try:
                value = getattr(artist, getter)()
            except (TypeError, ValueError, AttributeError):
                continue
            state[getter[4:]] = color_hex(value) if getter == "get_color" else to_jsonable(value)
    return state


def axes_state(ax) -> dict[str, Any]:
    """描画後の軸の状態。figure.canvas.draw() のあとに呼ぶ(目盛りの文字はその時に決まる)。"""
    state: dict[str, Any] = {
        "position": to_jsonable(list(ax.get_position().bounds)),
        "title": [ax.get_title(loc) for loc in ("left", "center", "right")],
        "xlabel": ax.get_xlabel(),
        "ylabel": ax.get_ylabel(),
        "xlim": to_jsonable(list(ax.get_xlim())),
        "ylim": to_jsonable(list(ax.get_ylim())),
        "xscale": ax.get_xscale(),
        "yscale": ax.get_yscale(),
        "xticks": [t.get_text() for t in ax.get_xticklabels()],
        "yticks": [t.get_text() for t in ax.get_yticklabels()],
        "facecolor": color_hex(ax.get_facecolor()),
        "visible": ax.get_visible(),
        "spines": {k: s.get_visible() for k, s in ax.spines.items()},
    }
    lines = []
    for line in ax.get_lines():
        entry = artist_style(line)
        entry["x"] = array_summary(line.get_xdata())
        entry["y"] = array_summary(line.get_ydata())
        lines.append(entry)
    state["lines"] = lines
    collections = []
    for collection in ax.collections:
        entry = {
            "class": type(collection).__name__,
            "label": collection.get_label(),
            "visible": collection.get_visible(),
            "zorder": to_jsonable(collection.get_zorder()),
            "alpha": to_jsonable(collection.get_alpha()),
            "facecolors": [color_hex(c) for c in collection.get_facecolors()[:8]],
            "edgecolors": [color_hex(c) for c in collection.get_edgecolors()[:8]],
            "paths": len(collection.get_paths()),
            "offsets": array_summary(np.asarray(collection.get_offsets())),
        }
        array = collection.get_array()
        if array is not None:
            entry["array"] = array_summary(np.ma.filled(np.asarray(array, dtype=float), np.nan))
        collections.append(entry)
    state["collections"] = collections
    state["patches"] = [artist_style(p) for p in ax.patches]
    state["images"] = [
        {"class": type(im).__name__, "array": array_summary(np.ma.filled(im.get_array(), np.nan)),
         "cmap": im.get_cmap().name, "clim": to_jsonable(list(im.get_clim()))}
        for im in ax.images
    ]
    state["texts"] = [{"text": t.get_text(), "position": to_jsonable(list(t.get_position()))} for t in ax.texts]
    legend = ax.get_legend()
    state["legend"] = None if legend is None else {
        "texts": [t.get_text() for t in legend.get_texts()],
        "visible": legend.get_visible(),
        "loc": to_jsonable(getattr(legend, "_loc", None)),
    }
    return state


def dataset_summary(dataset) -> dict[str, Any]:
    """データセットの要約: 列・値のハッシュ・スタイル(df 以外のフィールドすべて)。"""
    df = dataset.df
    summary: dict[str, Any] = {
        "columns": [str(c) for c in df.columns],
        "dtypes": [str(t) for t in df.dtypes],
        "shape": list(df.shape),
        "index": array_summary(np.asarray(df.index)),
        "values": {str(c): array_summary(df[c].to_numpy()) for c in df.columns},
    }
    for field in dataclasses.fields(dataset):
        if field.name == "df":
            continue
        summary[field.name] = to_jsonable(getattr(dataset, field.name))
    return summary


def environment_line() -> str:
    import matplotlib
    import PySide6

    return (f"{platform.platform()} / Python {sys.version.split()[0]} / PySide6 {PySide6.__version__} / "
            f"matplotlib {matplotlib.__version__} / numpy {np.__version__}")
