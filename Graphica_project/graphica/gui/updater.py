"""アプリの中からの更新。配布の形を見分け、Windows のインストーラー版はインストーラーを落として確かめ、実行する。

ほかの形(zip・macOS・pip・ソース)は、それぞれに合った案内だけにする(署名していない .app を自分で差し替えると壊れやすい)。
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

# アプリの中からの更新でインストーラーに渡す引数。/RELAUNCH=1 のときだけ、入れ終わったら起動し直す(installer/graphica.iss)。
# 閉じるのは Graphica 自身が先に済ませる(未保存の確認のため)。/CLOSEAPPLICATIONS は終わりきる前に始まったときの保険
INSTALLER_UPDATE_ARGS = ('/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CLOSEAPPLICATIONS', '/RELAUNCH=1')
_CHUNK_BYTES = 1 << 16
_DOWNLOAD_TIMEOUT_SEC = 30


class DownloadCancelled(Exception):
    pass


def install_kind():
    """'installer'(Windows のインストーラー版)/ 'windows_zip' / 'macos' / 'pip' / 'source'。"""
    if getattr(sys, 'frozen', False):
        if sys.platform == 'darwin':
            return 'macos'
        # インストーラーで入れたフォルダには、Inno Setup のアンインストーラーがある
        app_dir = os.path.dirname(sys.executable)
        return 'installer' if os.path.exists(os.path.join(app_dir, 'unins000.exe')) else 'windows_zip'
    return 'source' if _is_editable_install() else 'pip'


def _is_editable_install():
    """入れていない(ソースのまま)か、pip install -e で入れたなら True。PyPI から入れたものには direct_url.json が無い。"""
    from importlib.metadata import PackageNotFoundError, distribution
    try:
        direct_url = distribution('graphica-plot').read_text('direct_url.json') or ''
    except PackageNotFoundError:
        return True
    try:
        info = json.loads(direct_url) if direct_url else {}
    except ValueError:
        return False
    return bool((info.get('dir_info') or {}).get('editable'))


def update_download_dir():
    path = os.path.join(tempfile.gettempdir(), 'Graphica-update')
    os.makedirs(path, exist_ok=True)
    return path


def download_file(url, dest_path, expected_size=0, expected_sha256='', report_progress=None, is_cancelled=None):
    """url を dest_path に落とす。大きさと SHA-256 が分かっていれば確かめ、合わなければ消して例外。TaskRunner 用。

    途中の内容は .part に書き、確かめ終えてから名前を変える(壊れたインストーラーを実行しないように)。
    キャンセルされたら None。進み具合は KB 単位(Qt の int に収める)。
    """
    partial_path = dest_path + '.part'
    digest = hashlib.sha256()
    received = 0
    request = urllib.request.Request(url, headers={'User-Agent': 'Graphica-updater'})
    try:
        with urllib.request.urlopen(request, timeout=_DOWNLOAD_TIMEOUT_SEC) as response, \
                open(partial_path, 'wb') as out:
            total = int(response.headers.get('Content-Length') or expected_size or 0)
            while True:
                if is_cancelled is not None and is_cancelled():
                    raise DownloadCancelled()
                block = response.read(_CHUNK_BYTES)
                if not block:
                    break
                out.write(block)
                digest.update(block)
                received += len(block)
                if report_progress is not None:
                    report_progress(received // 1024, total // 1024)
        if expected_size and received != expected_size:
            raise ValueError(f"ダウンロードした大きさ({received:,} バイト)が、公開されている大きさ({expected_size:,} バイト)と違います。")
        if expected_sha256 and digest.hexdigest() != expected_sha256.lower():
            raise ValueError("ダウンロードしたファイルの SHA-256 が、公開されている値と一致しません。")
        os.replace(partial_path, dest_path)
        return dest_path
    except DownloadCancelled:
        return None
    finally:
        # 名前を変えたあとは .part は無い。失敗・キャンセルで残った途中のファイルだけ消える
        _remove_quietly(partial_path)


def _remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass


def launch_installer(installer_path):
    """インストーラーを Graphica と切り離して起動する。ログは同じフォルダに残す(更新に失敗したときの調べ用)。"""
    log_path = os.path.join(os.path.dirname(installer_path), 'Graphica-update.log')
    args = [installer_path, *INSTALLER_UPDATE_ARGS, f'/LOG={log_path}']
    flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    subprocess.Popen(args, creationflags=flags, close_fds=True)
    return args
