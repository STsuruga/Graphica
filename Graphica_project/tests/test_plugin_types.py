# tests/test_plugin_types.py
"""core/plugin_types.py (トラック1 フェーズA-1、C-1/C-2) に対する軽量なテスト。"""
from core.plugin_types import (
    AnalysisResult, PluginAnalyzer, PluginHookKind, PluginProcessor, PluginRegistrationError,
)


def test_plugin_hook_kind_values():
    assert PluginHookKind.FIT_FUNCTION.value == "fit_function"
    assert PluginHookKind.MENU_ACTION.value == "menu_action"


def test_plugin_registration_error_defaults():
    err = PluginRegistrationError(
        plugin_name="my_plugin", hook_kind=PluginHookKind.FIT_FUNCTION, message="失敗しました"
    )
    assert err.plugin_name == "my_plugin"
    assert err.hook_kind is PluginHookKind.FIT_FUNCTION
    assert err.message == "失敗しました"
    assert err.exception is None


def test_plugin_registration_error_carries_original_exception():
    original = ValueError("bad name")
    err = PluginRegistrationError(
        plugin_name="my_plugin", hook_kind=PluginHookKind.MENU_ACTION,
        message=str(original), exception=original,
    )
    assert err.exception is original


def test_plugin_hook_kind_includes_processor_and_analyzer():
    assert PluginHookKind.PROCESSOR.value == "processor"
    assert PluginHookKind.ANALYZER.value == "analyzer"


def test_plugin_processor_fields():
    proc = PluginProcessor(name="Smooth", fn=lambda ds, params: ds, category="denoise",
                            param_schema=[{"name": "window", "type": "int"}], plugin_name="X")
    assert proc.name == "Smooth"
    assert proc.category == "denoise"
    assert proc.param_schema[0]["name"] == "window"
    assert proc.plugin_name == "X"


def test_plugin_analyzer_fields():
    analyzer = PluginAnalyzer(name="Peaks", fn=lambda ds, params: None, output_kind="table",
                               param_schema=[], plugin_name="X")
    assert analyzer.name == "Peaks"
    assert analyzer.output_kind == "table"


def test_analysis_result_defaults_to_all_none():
    result = AnalysisResult()
    assert result.table is None
    assert result.annotations is None
    assert result.new_datasets is None


def test_analysis_result_can_carry_all_three_kinds_of_output():
    table = object()
    annotations = [{"type": "text", "text": "peak"}]
    new_datasets = [object()]
    result = AnalysisResult(table=table, annotations=annotations, new_datasets=new_datasets)
    assert result.table is table
    assert result.annotations is annotations
    assert result.new_datasets is new_datasets
