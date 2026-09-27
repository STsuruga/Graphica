"""特性テストの共通 fixture。どのシナリオも ID と時刻を固定し、出たモーダルを記録する。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import recorder  # noqa: E402
import scenario  # noqa: E402


@pytest.fixture(autouse=True)
def _characterization_determinism(deterministic_ids_and_time):
    yield


def pytest_configure(config):
    config.addinivalue_line("markers", "pinned_os: 基準を取った OS(ENVIRONMENT.md)でだけ比べる")
    config.addinivalue_line(
        "markers", "any_os: 記録器そのもののテストなど、どの OS でも同じ結果になるもの")


def pytest_collection_modifyitems(config, items):
    # 数値は libm と SIMD の違いで最後の桁が変わり、条件の悪いフィットはそれを大きくする。画面の大きさはフォントで
    # 変わる。どれも OS ごとの基準を持つ意味が無いので、基準を取った OS でだけ比べる
    for item in items:
        if "characterization" in str(item.path) and not item.get_closest_marker("any_os"):
            item.add_marker(pytest.mark.pinned_os)


@pytest.fixture(autouse=True)
def _skip_on_other_os(request):
    if request.node.get_closest_marker("pinned_os") and not recorder.pinned_os_matches():
        pytest.skip(f"基準は {recorder.PIXEL_ENVIRONMENT['os']} で取った(ENVIRONMENT.md)")


@pytest.fixture
def normalizer(tmp_path):
    norm = recorder.Normalizer()
    norm.add_path(tmp_path, "<CASE>")
    return norm


@pytest.fixture
def modal_log(monkeypatch) -> scenario.ModalLog:
    return scenario.install_modal_log(monkeypatch)


@pytest.fixture
def app_env(tmp_path, monkeypatch, modal_log):
    from PySide6.QtWidgets import QApplication

    from graphica.core import i18n
    from graphica.gui import theme

    env = scenario.AppEnvironment(tmp_path, monkeypatch, modal_log)
    yield env
    # 言語とテーマはプロセス全体の状態なので、次のシナリオに持ち越さない
    i18n.set_language(i18n.DEFAULT_LANGUAGE)
    theme.apply_theme(QApplication.instance(), False)
