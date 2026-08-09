# tests/test_workers.py
"""gui/workers.py の read_data_file() に対するテスト。

ビルトインのCSV/Excel読み込みに加えて、register_importer()(項目B-1)による
プラグイン読み込み経路(read_data_file()の入口での割り込み)を検証する。
"""
import pandas as pd
import pytest

import core.plugin_api as plugin_api_module
from core.plugin_api import GraphicaPluginAPI
from core.plugin_types import PluginExecutionError
from gui.workers import read_data_file


@pytest.fixture(autouse=True)
def _isolate_plugin_api_singleton():
    """各テストの前後で core.plugin_api._singleton_api をリセットし、
    テスト間でプラグイン登録状態が伝播しないようにする。"""
    yield
    plugin_api_module._singleton_api = None
    plugin_api_module._singleton_manager = None


# --- ビルトインのCSV/Excel読み込み(プラグイン無し、既存動作の回帰確認) ---

def test_read_csv_file(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("x,y\n1,2\n3,4\n", encoding='utf-8')
    df = read_data_file(str(path))
    assert list(df.columns) == ['x', 'y']
    assert len(df) == 2


def test_read_excel_file(tmp_path):
    path = tmp_path / "data.xlsx"
    pd.DataFrame({'x': [1, 2], 'y': [3, 4]}).to_excel(str(path), index=False)
    df = read_data_file(str(path))
    assert list(df.columns) == ['x', 'y']


def test_read_unsupported_extension_raises_value_error(tmp_path):
    path = tmp_path / "data.foo"
    path.write_text("dummy", encoding='utf-8')
    with pytest.raises(ValueError, match="未対応"):
        read_data_file(str(path))


# --- プラグインインポーター経由の読み込み(項目B-1) ---

def test_plugin_importer_is_used_for_registered_extension(tmp_path):
    path = tmp_path / "data.testfmt"
    path.write_text("dummy", encoding='utf-8')

    api = GraphicaPluginAPI()
    calls = []

    def fake_loader(file_path):
        calls.append(file_path)
        return pd.DataFrame({'a': [1.0, 2.0], 'b': [3.0, 4.0]})

    api.register_importer([".testfmt"], fake_loader, name="TestPlugin")
    plugin_api_module._singleton_api = api

    df = read_data_file(str(path))

    assert calls == [str(path)]
    assert list(df.columns) == ['a', 'b']


def test_plugin_importer_extension_without_dot_and_uppercase(tmp_path):
    """register_importer側のextensionsは大文字・ピリオド無しでも正しく正規化される"""
    path = tmp_path / "data.TESTFMT"
    path.write_text("dummy", encoding='utf-8')

    api = GraphicaPluginAPI()
    api.register_importer(["TESTFMT"], lambda fp: pd.DataFrame({'a': [1]}), name="TestPlugin")
    plugin_api_module._singleton_api = api

    df = read_data_file(str(path))
    assert list(df.columns) == ['a']


def test_plugin_importer_not_registered_falls_back_to_builtin(tmp_path):
    """他の拡張子用のプラグインが登録されていても、CSVはビルトイン処理のまま動く"""
    path = tmp_path / "data.csv"
    path.write_text("x,y\n1,2\n", encoding='utf-8')

    api = GraphicaPluginAPI()
    api.register_importer([".testfmt"], lambda fp: pd.DataFrame({'a': [1]}), name="TestPlugin")
    plugin_api_module._singleton_api = api

    df = read_data_file(str(path))
    assert list(df.columns) == ['x', 'y']


def test_plugin_importer_higher_priority_wins(tmp_path):
    path = tmp_path / "data.testfmt"
    path.write_text("dummy", encoding='utf-8')

    api = GraphicaPluginAPI()
    api.register_importer([".testfmt"], lambda fp: pd.DataFrame({'from': ['low']}), name="Low", priority=0)
    api.register_importer([".testfmt"], lambda fp: pd.DataFrame({'from': ['high']}), name="High", priority=10)
    plugin_api_module._singleton_api = api

    df = read_data_file(str(path))
    assert df['from'].iloc[0] == 'high'


def test_plugin_importer_raises_plugin_execution_error_with_plugin_name(tmp_path):
    path = tmp_path / "data.testfmt"
    path.write_text("dummy", encoding='utf-8')

    api = GraphicaPluginAPI()

    def broken_loader(file_path):
        raise RuntimeError("corrupt file")

    api.register_importer([".testfmt"], broken_loader, name="BrokenPlugin")
    plugin_api_module._singleton_api = api

    with pytest.raises(PluginExecutionError, match="BrokenPlugin") as exc_info:
        read_data_file(str(path))
    assert "corrupt file" in str(exc_info.value)


def test_plugin_importer_returning_non_dataframe_raises_clear_error(tmp_path):
    path = tmp_path / "data.testfmt"
    path.write_text("dummy", encoding='utf-8')

    api = GraphicaPluginAPI()
    api.register_importer([".testfmt"], lambda fp: {"sheet1": pd.DataFrame({'a': [1]})}, name="MultiSheetPlugin")
    plugin_api_module._singleton_api = api

    with pytest.raises(PluginExecutionError, match="MultiSheetPlugin"):
        read_data_file(str(path))
