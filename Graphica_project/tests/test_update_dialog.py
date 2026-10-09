"""UpdateDialog: リリースノートと、配布の形に合った更新の方法。"""
import pytest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QLineEdit, QPushButton, QTextBrowser

from graphica.gui.dialogs import UpdateDialog

INFO = {'tag_name': 'v9.9.9', 'html_url': 'https://example.com/r', 'body': '## 新機能\n- **速くなった**'}


def _buttons(dialog):
    return {b.text(): b for b in dialog.findChild(QDialogButtonBox).findChildren(QPushButton)}


def _explanation(dialog):
    return dialog.findChild(QLabel, "update_explanation").text()


def test_shows_versions_and_release_notes(qapp):
    dialog = UpdateDialog(INFO, "2.1.0", 'installer', True)
    texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "v9.9.9" in texts and "2.1.0" in texts
    assert "速くなった" in dialog.findChild(QTextBrowser).toPlainText()


def test_installer_version_offers_update_now(qapp):
    dialog = UpdateDialog(INFO, "2.1.0", 'installer', True)
    buttons = _buttons(dialog)
    assert set(buttons) == {"今すぐ更新", "リリースのページを開く", "あとで"}
    assert buttons["今すぐ更新"].isDefault()
    assert "自動で起動し直します" in _explanation(dialog)

    buttons["今すぐ更新"].click()

    assert dialog.choice == 'install'
    assert dialog.result() == QDialog.DialogCode.Accepted


@pytest.mark.parametrize("kind, label, words", [
    ('windows_zip', "ZIP をダウンロード", "フォルダと置き換えて"),
    ('macos', "macOS 版をダウンロード", "Graphica.app と置き換えて"),
])
def test_zip_and_macos_versions_offer_the_download(qapp, kind, label, words):
    dialog = UpdateDialog(INFO, "2.1.0", kind, True)
    assert words in _explanation(dialog)
    _buttons(dialog)[label].click()
    assert dialog.choice == 'download'


def test_pip_version_shows_the_command_and_copies_it(qapp):
    dialog = UpdateDialog(INFO, "2.1.0", 'pip', False)
    assert dialog.findChild(QLineEdit).text() == UpdateDialog.PIP_COMMAND
    assert "今すぐ更新" not in _buttons(dialog)

    copy_button = next(b for b in dialog.findChildren(QPushButton) if b.text() == "コピー")
    copy_button.click()

    assert QApplication.clipboard().text() == UpdateDialog.PIP_COMMAND


def test_source_checkout_points_to_git(qapp):
    dialog = UpdateDialog(INFO, "2.1.0", 'source', False)
    assert "git pull" in _explanation(dialog)
    assert set(_buttons(dialog)) == {"リリースのページを開く", "あとで"}


def test_without_the_file_only_the_release_page_is_offered(qapp):
    dialog = UpdateDialog(INFO, "2.1.0", 'installer', False)
    assert set(_buttons(dialog)) == {"リリースのページを開く", "あとで"}
    assert "リリースのページ" in _explanation(dialog)


def test_release_page_and_later(qapp):
    dialog = UpdateDialog(INFO, "2.1.0", 'installer', True)
    _buttons(dialog)["リリースのページを開く"].click()
    assert dialog.choice == 'page'

    dialog = UpdateDialog(INFO, "2.1.0", 'installer', True)
    _buttons(dialog)["あとで"].click()
    assert dialog.choice is None
    assert dialog.result() == QDialog.DialogCode.Rejected


def test_missing_release_notes_are_said_so(qapp):
    dialog = UpdateDialog({'tag_name': 'v9.9.9'}, "2.1.0", 'installer', True)
    assert "リリースノートはありません" in dialog.findChild(QTextBrowser).toPlainText()
