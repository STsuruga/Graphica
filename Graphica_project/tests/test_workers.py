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
from gui.workers import DataLoadWorker, read_data_file


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


# --- BOM検出 (_detect_bom_encoding) ---

def test_read_csv_with_utf16_bom_is_detected_and_read(tmp_path):
    """UTF-16 BOM付きCSVは _detect_bom_encoding() で検出され、正しく読める。"""
    path = tmp_path / "data_utf16.csv"
    path.write_text("x,y\n1,2\n3,4\n", encoding='utf-16')  # 'utf-16'書き込みはBOM付与される

    df = read_data_file(str(path))

    assert list(df.columns) == ['x', 'y']
    assert len(df) == 2


def test_read_csv_with_utf8_sig_bom_that_fails_falls_back_and_raises(tmp_path):
    """UTF-8 BOMが付いているが実際にはデコード/パース不能なCSVは、
    BOM由来のエンコーディングでの読み込み失敗(except節)を経て、
    通常のフォールバック一覧も全て失敗し最終的にValueErrorになる。"""
    path = tmp_path / "data_broken.csv"
    # UTF-8 BOM + 引用符が閉じられていない不正なCSV(ASCIIのみなのでデコード自体は
    # utf-8-sig/cp932/latin-1いずれでも成功するが、トークナイズがどのエンコーディング
    # でも失敗するため、全フォールバックがParserErrorで失敗する)。
    path.write_bytes(b'\xef\xbb\xbfa,b\n"unterminated\n')

    with pytest.raises(ValueError, match="文字コードを判定できませんでした"):
        read_data_file(str(path))


# --- DataLoadWorker.run() ---

def test_data_load_worker_run_emits_load_succeeded(qapp, tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("x,y\n1,2\n3,4\n", encoding='utf-8')

    worker = DataLoadWorker(str(path))
    succeeded_calls = []
    failed_calls = []
    worker.load_succeeded.connect(lambda df, fp: succeeded_calls.append((df, fp)))
    worker.load_failed.connect(lambda msg, fp: failed_calls.append((msg, fp)))

    worker.run()

    assert failed_calls == []
    assert len(succeeded_calls) == 1
    df, fp = succeeded_calls[0]
    assert list(df.columns) == ['x', 'y']
    assert fp == str(path)


def test_data_load_worker_run_emits_load_failed_when_fewer_than_two_columns(qapp, tmp_path):
    """1列しかないデータは読み込み自体は成功するが、run()内のバリデーションで
    ValueErrorを送出しload_failedになる。"""
    path = tmp_path / "single_col.csv"
    path.write_text("x\n1\n2\n", encoding='utf-8')

    worker = DataLoadWorker(str(path))
    succeeded_calls = []
    failed_calls = []
    worker.load_succeeded.connect(lambda df, fp: succeeded_calls.append((df, fp)))
    worker.load_failed.connect(lambda msg, fp: failed_calls.append((msg, fp)))

    worker.run()

    assert succeeded_calls == []
    assert len(failed_calls) == 1
    msg, fp = failed_calls[0]
    assert "2列" in msg
    assert fp == str(path)


def test_data_load_worker_run_emits_load_failed_on_read_error(qapp, tmp_path):
    """未対応拡張子など、read_data_file() が例外を投げるケースもload_failedになる。"""
    path = tmp_path / "data.foo"
    path.write_text("dummy", encoding='utf-8')

    worker = DataLoadWorker(str(path))
    failed_calls = []
    worker.load_failed.connect(lambda msg, fp: failed_calls.append((msg, fp)))

    worker.run()

    assert len(failed_calls) == 1
    msg, fp = failed_calls[0]
    assert "未対応" in msg
    assert fp == str(path)
