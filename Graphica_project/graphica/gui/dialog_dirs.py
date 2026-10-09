"""ファイルダイアログを開く場所。用途ごとに前回選んだフォルダを覚え、まだ無ければ「ドキュメント」から開く。

場所を渡さないと Qt は今の作業フォルダで開き、ショートカットから起動するとそれがアプリ本体のフォルダになる。
作業中のプロジェクトの場所など、もっと適した場所があれば preferred_dir で渡す(在るときだけ使う)。
"""
import json
import os

from PySide6.QtCore import QStandardPaths

from graphica.gui import app_settings, notify

# 用途(覚えるフォルダの単位)
PROJECT = 'project'      # プロジェクトを開く・保存する
DATA = 'data'            # データを読み込む
EXPORT = 'export'        # 図・スクリプト・レポートを書き出す
TABLE = 'table'          # データ表(CSV・Excel)を書き出す
TEMPLATE = 'template'    # 書式テンプレート
OTHER = 'other'          # 設定の書き出し・診断情報・プラグインなど


def documents_dir():
    path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    return path if path and os.path.isdir(path) else os.path.expanduser('~')


def _remembered():
    raw = app_settings.LAST_DIALOG_DIRS.read(app_settings.open_settings())
    try:
        value = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def start_dir(purpose, preferred_dir=None):
    """preferred_dir が在ればそこ、無ければその用途で前回選んだフォルダ、それも無ければ「ドキュメント」。"""
    for candidate in (preferred_dir, _remembered().get(purpose)):
        if candidate and os.path.isdir(candidate):
            return os.path.normpath(candidate)
    return os.path.normpath(documents_dir())


def start_path(purpose, file_name='', preferred_dir=None):
    directory = start_dir(purpose, preferred_dir)
    return os.path.normpath(os.path.join(directory, file_name) if file_name else directory)


def remember(purpose, path):
    """選んだファイルのフォルダ(フォルダならそのもの)を、その用途の次の開き先にする。"""
    if not path:
        return
    directory = path if os.path.isdir(path) else os.path.dirname(path)
    if not directory:
        return
    remembered = _remembered()
    if remembered.get(purpose) == directory:
        return
    remembered[purpose] = directory
    app_settings.LAST_DIALOG_DIRS.write(app_settings.open_settings(), json.dumps(remembered, ensure_ascii=False))


def get_save_file_name(parent, purpose, title, file_name, file_filter, preferred_dir=None):
    path, selected_filter = notify.get_save_file_name(
        parent, title, start_path(purpose, file_name, preferred_dir), file_filter)
    remember(purpose, path)
    return path, selected_filter


def get_open_file_name(parent, purpose, title, file_filter, preferred_dir=None):
    path, selected_filter = notify.get_open_file_name(parent, title, start_dir(purpose, preferred_dir), file_filter)
    remember(purpose, path)
    return path, selected_filter


def get_open_file_names(parent, purpose, title, file_filter, preferred_dir=None):
    paths, selected_filter = notify.get_open_file_names(parent, title, start_dir(purpose, preferred_dir), file_filter)
    if paths:
        remember(purpose, paths[0])
    return paths, selected_filter


def get_existing_directory(parent, purpose, title, preferred_dir=None):
    path = notify.get_existing_directory(parent, title, start_dir(purpose, preferred_dir))
    remember(purpose, path)
    return path


# --- 作業中のものに合わせた場所 ---

def project_dir(app):
    """保存したプロジェクトのフォルダ。まだ保存していなければ None。"""
    path = getattr(app, '_current_project_path', None)
    return os.path.dirname(path) if path else None


def project_stem(app):
    path = getattr(app, '_current_project_path', None)
    return os.path.splitext(os.path.basename(path))[0] if path else ''


def data_source_dir(app):
    """読み込んだデータファイルのうち、最初に見つかったもののフォルダ(データの隣にプロジェクトを置けるように)。"""
    for dataset in getattr(app.project, 'datasets', []):
        source = getattr(dataset, 'source_file', None)
        if source and os.path.isdir(os.path.dirname(source)):
            return os.path.dirname(source)
    return None


def output_dir(app):
    """書き出しの場所: 保存したプロジェクトのフォルダ、無ければ読み込んだデータのフォルダ。"""
    return project_dir(app) or data_source_dir(app)
