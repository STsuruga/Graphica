#!/usr/bin/env python3
"""
graphica/plugins/ のプラグイン(同梱サンプルの example_plugin)を、環境設定の
「プラグインをインストール...」で入れられる zip に固める。

配布版(exe)は graphica/plugins/ を探さないので、利用者に渡すには zip が要る。
中身は1つのトップレベルフォルダ(= プラグイン名)の下に __init__.py がある形
(graphica/core/plugin_install.py の _find_plugin_root() が受け付ける形)。
プラグイン本体は別リポジトリで開発し、それぞれが同じ仕組みの scripts/build_zip.py を持つ。

    python scripts/build_plugin_zip.py example_plugin
    python scripts/build_plugin_zip.py --all --out-dir dist/plugins
"""
import argparse
import json
import os
import sys
import zipfile

# scripts/ の1つ上(Graphica_project/)をプロジェクトルートとする。
# cwd には依存しない(docs/dev/Graphica_SPEC.md §2.8 の制約)。
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGINS_DIR = os.path.join(PROJECT_ROOT, "graphica", "plugins")
DEFAULT_OUT_DIR = os.path.join(PROJECT_ROOT, "dist", "plugins")

# zipに含めない一時ファイル/キャッシュ
EXCLUDED_DIRS = {"__pycache__", ".pytest_cache", ".git"}
EXCLUDED_SUFFIXES = (".pyc", ".pyo")


def _iter_plugin_files(plugin_dir):
    """プラグインフォルダ配下の、zipに含めるファイルを列挙する。"""
    for dirpath, dirnames, filenames in os.walk(plugin_dir):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for filename in sorted(filenames):
            if filename.endswith(EXCLUDED_SUFFIXES):
                continue
            yield os.path.join(dirpath, filename)


def _read_version(plugin_dir):
    """plugin.json の version を返す(読めなければ None)。"""
    manifest_path = os.path.join(plugin_dir, "plugin.json")
    try:
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f).get("version")
    except (OSError, ValueError):
        return None


def build_plugin_zip(plugin_name, out_dir=DEFAULT_OUT_DIR):
    """
    plugins/<plugin_name>/ を zip に固めて、作成したzipのパスを返す。

    Raises:
        FileNotFoundError: プラグインフォルダ、または必須ファイルが無い場合。
    """
    plugin_dir = os.path.join(PLUGINS_DIR, plugin_name)
    if not os.path.isdir(plugin_dir):
        raise FileNotFoundError(f"プラグインフォルダがありません: {plugin_dir}")
    for required in ("__init__.py", "plugin.json"):
        if not os.path.exists(os.path.join(plugin_dir, required)):
            raise FileNotFoundError(
                f"{plugin_name} に {required} がありません"
                "(インストーラがプラグインとして認識できません)。"
            )

    version = _read_version(plugin_dir)
    basename = f"{plugin_name}-{version}.zip" if version else f"{plugin_name}.zip"
    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, basename)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in _iter_plugin_files(plugin_dir):
            # アーカイブ内のパスは「<plugin_name>/...」にする(レイアウト(a))
            arcname = os.path.join(
                plugin_name, os.path.relpath(file_path, plugin_dir)
            ).replace(os.sep, "/")
            zf.write(file_path, arcname)
    return zip_path


def discover_plugin_names():
    """plugins/ 配下の、zip化できる(必須ファイルが揃った)プラグイン名一覧。"""
    if not os.path.isdir(PLUGINS_DIR):
        return []
    names = []
    for entry in sorted(os.listdir(PLUGINS_DIR)):
        plugin_dir = os.path.join(PLUGINS_DIR, entry)
        if not os.path.isdir(plugin_dir):
            continue
        if all(os.path.exists(os.path.join(plugin_dir, f))
               for f in ("__init__.py", "plugin.json")):
            names.append(entry)
    return names


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("plugin", nargs="*", help="zip化するプラグインのフォルダ名")
    parser.add_argument("--all", action="store_true",
                        help="plugins/ 配下のプラグインをすべてzip化する")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                        help=f"出力先ディレクトリ(既定: {DEFAULT_OUT_DIR})")
    args = parser.parse_args(argv)

    if args.all:
        targets = discover_plugin_names()
    elif args.plugin:
        targets = args.plugin
    else:
        parser.error("プラグイン名か --all を指定してください。"
                     f"\n利用可能: {', '.join(discover_plugin_names()) or '(なし)'}")

    if not targets:
        print("zip化できるプラグインがありません。", file=sys.stderr)
        return 1

    for name in targets:
        try:
            zip_path = build_plugin_zip(name, args.out_dir)
        except FileNotFoundError as e:
            print(f"スキップ: {e}", file=sys.stderr)
            return 1
        size_kb = os.path.getsize(zip_path) / 1024
        print(f"{zip_path}  ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
