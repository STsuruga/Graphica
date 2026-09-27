"""Windows で .gra と .graphica を Graphica に結び付ける(利用者の範囲 HKCU\\Software\\Classes だけを触る)。

インストーラーを使わず exe だけを置いた人のため、環境設定のボタンから登録・解除する。インストーラーは同じ名前で自分で登録する。
ソースや pip から動かしているときは、ダブルクリックで起動する exe が無いので登録しない。
"""
import os
import sys

PROG_ID = "Graphica.Project"
PROG_ID_DESCRIPTION = "Graphica プロジェクト"
ASSOCIATED_EXTENSIONS = (".gra", ".graphica")
_CLASSES_ROOT = r"Software\Classes"


def _winreg():
    import winreg
    return winreg


def is_supported():
    """登録できるのは、Windows の exe(PyInstaller で固めたもの)から動かしているときだけ。"""
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def open_command(executable=None):
    return f'"{executable or sys.executable}" "%1"'


def _set_default(winreg, path, value):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_WRITE) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, value)


def _read_default(winreg, path):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return winreg.QueryValueEx(key, "")[0]
    except OSError:
        return None


def _delete_tree(winreg, path):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_tree(winreg, path + "\\" + child)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except FileNotFoundError:
        pass


def _notify_shell():
    """エクスプローラーにアイコンと関連付けを読み直させる。失敗しても登録自体は済んでいる。"""
    try:
        import ctypes
        shcne_assocchanged, shcnf_idlist = 0x08000000, 0x0000
        ctypes.windll.shell32.SHChangeNotify(shcne_assocchanged, shcnf_idlist, None, None)
    except (AttributeError, OSError):
        pass


def register(executable=None, winreg=None, notify_shell=True):
    winreg = winreg or _winreg()
    executable = executable or sys.executable
    prog_id_path = _CLASSES_ROOT + "\\" + PROG_ID
    _set_default(winreg, prog_id_path, PROG_ID_DESCRIPTION)
    _set_default(winreg, prog_id_path + r"\DefaultIcon", f'"{executable}",0')
    _set_default(winreg, prog_id_path + r"\shell\open\command", open_command(executable))
    for ext in ASSOCIATED_EXTENSIONS:
        _set_default(winreg, _CLASSES_ROOT + "\\" + ext, PROG_ID)
    if notify_shell:
        _notify_shell()


def unregister(winreg=None, notify_shell=True):
    """自分が結び付けた拡張子だけを外す(ほかのソフトに変えられていれば触らない)。"""
    winreg = winreg or _winreg()
    for ext in ASSOCIATED_EXTENSIONS:
        path = _CLASSES_ROOT + "\\" + ext
        if _read_default(winreg, path) == PROG_ID:
            _delete_tree(winreg, path)
    _delete_tree(winreg, _CLASSES_ROOT + "\\" + PROG_ID)
    if notify_shell:
        _notify_shell()


def is_registered(executable=None, winreg=None):
    """このアプリの exe で開くよう登録されているか。"""
    winreg = winreg or _winreg()
    command = _read_default(winreg, _CLASSES_ROOT + "\\" + PROG_ID + r"\shell\open\command")
    if command is None or os.path.normcase(command) != os.path.normcase(open_command(executable)):
        return False
    return all(_read_default(winreg, _CLASSES_ROOT + "\\" + ext) == PROG_ID for ext in ASSOCIATED_EXTENSIONS)
