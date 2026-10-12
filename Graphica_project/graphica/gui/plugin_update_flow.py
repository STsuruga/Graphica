"""プラグインの更新: 起動時(1日1回)とヘルプメニュー・環境設定から新しい版を調べ、一覧で知らせて、選んだものを入れ替える。

調べる・落とす・入れ替えるのは別スレッド(TaskRunner)。入れ替えたプラグインは次の起動から使われる
(読み込んだプラグインをその場で入れ替える仕組みは無い)。
"""
import datetime
import logging
import os

from graphica.core.app_paths import get_user_plugins_dir
from graphica.core.i18n import tr
from graphica.core.plugin_install import install_plugin_zip
from graphica.core.plugin_updates import check_plugin_updates, check_update_zip
from graphica.gui import app_settings, notify
from graphica.gui.task_runner import TaskRunner
from graphica.gui.updater import download_file, update_download_dir

logger = logging.getLogger(__name__)


def _today():
    return datetime.date.today().isoformat()


def _start_check(app, on_succeeded, on_failed):
    if getattr(app, '_plugin_update_runner', None) is not None:
        return False
    runner = TaskRunner(check_plugin_updates, get_user_plugins_dir(), parent=app)
    runner.succeeded.connect(on_succeeded)
    runner.failed.connect(on_failed)
    app._plugin_update_runner = runner
    runner.start()
    return True


def _finish(app):
    app._plugin_update_runner = None


def start_startup_check(app):
    """1日1回だけ調べ、新しい版があるときだけ知らせる(失敗・無しなら何も出さない)。"""
    if app_settings.PLUGIN_UPDATE_LAST_CHECK.read(app.settings) == _today():
        return

    def succeeded(updates):
        _finish(app)
        app_settings.PLUGIN_UPDATE_LAST_CHECK.write(app.settings, _today())
        if updates:
            offer_updates(app, updates)

    def failed(message):
        _finish(app)
        logger.info("起動時のプラグインの更新の確認に失敗しました(オフライン等の可能性): %s", message)

    _start_check(app, succeeded, failed)


def check_now(app):
    """メニュー・環境設定の「プラグインの更新を確認」。最新でも失敗でも結果を知らせる。"""
    def succeeded(updates):
        _finish(app)
        app_settings.PLUGIN_UPDATE_LAST_CHECK.write(app.settings, _today())
        if updates:
            offer_updates(app, updates)
        else:
            notify.information(app, tr("プラグインの更新"), tr("入れているプラグインはすべて最新です。"))

    def failed(message):
        _finish(app)
        logger.warning("プラグインの更新の確認に失敗しました: %s", message)
        notify.warning(app, tr("プラグインの更新"),
                       tr("更新を確認できませんでした。インターネットに接続しているか確かめてください。") + f"\n\n{message}")

    if not _start_check(app, succeeded, failed):
        notify.information(app, tr("プラグインの更新"), tr("確認中です。完了までお待ちください。"))


def offer_updates(app, updates):
    """新しい版の一覧を出し、選んだものを入れ替える。"""
    from graphica.gui.dialogs import PluginUpdatesDialog
    dialog = PluginUpdatesDialog(updates, app)
    if dialog.exec() != dialog.DialogCode.Accepted:
        return
    selected = dialog.selected_updates()
    if selected:
        apply_updates(app, selected)


def download_and_install(updates, plugins_dir, download_dir, report_progress=None, is_cancelled=None):
    """1件ずつ落として確かめ、入れ替える。結果は [(更新の情報, エラーの文 or None)]。TaskRunner 用。"""
    results = []
    for number, update in enumerate(updates, start=1):
        if is_cancelled is not None and is_cancelled():
            break
        if report_progress is not None:
            report_progress(number - 1, len(updates), update['name'])
        asset = update['zip']
        path = os.path.join(download_dir, f"{update['folder']}-{update['latest']}.zip")
        try:
            if download_file(asset['url'], path, asset.get('size', 0), asset.get('sha256', ''),
                             is_cancelled=is_cancelled) is None:
                break
            check_update_zip(path, update['folder'])
            install_plugin_zip(path, plugins_dir)
            results.append((update, None))
        except Exception as e:  # 1件の失敗でほかを止めない(理由は結果に出す)
            logger.warning("プラグイン %s の更新に失敗しました", update['name'], exc_info=True)
            results.append((update, str(e)))
        finally:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
    return results


def apply_updates(app, updates):
    runner = TaskRunner(download_and_install, updates, get_user_plugins_dir(), update_download_dir(), parent=app)
    runner.succeeded.connect(lambda results: _on_installed(app, results))
    runner.failed.connect(lambda message: _on_install_failed(app, message))
    app._plugin_update_runner = runner
    app.statusBar().showMessage(tr("プラグインを更新しています..."))
    runner.start()


def _on_installed(app, results):
    _finish(app)
    app.statusBar().clearMessage()
    done = [update for update, error in results if error is None]
    failed = [(update, error) for update, error in results if error is not None]
    lines = []
    if done:
        lines.append(tr("次のプラグインを更新しました。Graphica を起動し直すと新しい版が使われます。"))
        lines += [f"  • {u['name']} {u['current']} → {u['latest']}" for u in done]
    if failed:
        if lines:
            lines.append("")
        lines.append(tr("次のプラグインは更新できませんでした。"))
        lines += [f"  • {u['name']}: {error}" for u, error in failed]
    if not lines:
        return
    (notify.warning if failed else notify.information)(app, tr("プラグインの更新"), "\n".join(lines))


def _on_install_failed(app, message):
    _finish(app)
    app.statusBar().clearMessage()
    notify.warning(app, tr("プラグインの更新"), tr("プラグインを更新できませんでした。") + f"\n\n{message}")


def stop(app):
    """タブを閉じるとき: 動いている確認・更新を止めて待つ(閉じたタブに結果を返さない)。"""
    runner = getattr(app, '_plugin_update_runner', None)
    if runner is None:
        return
    try:
        runner.succeeded.disconnect()
        runner.failed.disconnect()
    except (RuntimeError, TypeError):
        pass
    runner.requestInterruption()
    runner.wait()
    runner.deleteLater()
    app._plugin_update_runner = None
