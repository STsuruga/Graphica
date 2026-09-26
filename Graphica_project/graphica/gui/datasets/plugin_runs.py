"""プラグインが登録したデータ処理と解析の実行。結果の追加は Undo できる。"""
import logging
from PySide6.QtWidgets import QDialog

from graphica.gui import notify
from graphica.core.dataset import Dataset
from graphica.core.plugin_types import AnalysisResult, PluginExecutionError
from graphica.gui.dialogs import PluginParamDialog, ResultDialog

logger = logging.getLogger(__name__)


class PluginRunController:
    """プラグインのデータ処理(processor)と解析(analyzer)を今のデータセットに対して実行する。"""

    def __init__(self, host):
        self._host = host
        self.analysis_result_dialog = None

    def run_processor(self, processor):
        """processor が返したデータセットを Undo できる形で足す(プラグイン側は Undo を意識しない)。"""
        dataset = self._host.current_dataset()
        if dataset is None:
            notify.information(self._host.parent_widget, processor.name, "データセットを選択してください。")
            return

        params = {}
        if processor.param_schema:
            dialog = PluginParamDialog(processor.name, processor.param_schema, self._host.parent_widget)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            params = dialog.get_values()

        try:
            new_dataset = processor.fn(dataset, params)
            if not isinstance(new_dataset, Dataset):
                raise TypeError(f"Datasetを返しませんでした(型: {type(new_dataset).__name__})。")
        except Exception as e:
            logger.exception("[plugin:%s] processor の実行に失敗しました", processor.plugin_name)
            notify.critical(
                self._host.parent_widget, "データ処理エラー",
                str(PluginExecutionError(processor.plugin_name, f"「{processor.name}」の実行に失敗しました: {e}"))
            )
            return

        # どのプラグインが作ったかを残す
        new_dataset.source_plugin = processor.plugin_name
        self._host.add_dataset_with_undo(
            new_dataset, self._host.target_folder_for_new_dataset(),
            description=f"データ処理: {processor.name}"
        )
        self._host.show_status(f"「{new_dataset.name}」を追加しました")

    def run_analyzer(self, analyzer):
        """analyzer の結果(派生データセット・注釈・表)を、それぞれ Undo できる形や結果の窓で反映する。"""
        dataset = self._host.current_dataset()
        if dataset is None:
            notify.information(self._host.parent_widget, analyzer.name, "データセットを選択してください。")
            return

        params = {}
        if analyzer.param_schema:
            dialog = PluginParamDialog(analyzer.name, analyzer.param_schema, self._host.parent_widget)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            params = dialog.get_values()

        try:
            result = analyzer.fn(dataset, params)
            if not isinstance(result, AnalysisResult):
                raise TypeError(f"AnalysisResultを返しませんでした(型: {type(result).__name__})。")
        except Exception as e:
            logger.exception("[plugin:%s] analyzer の実行に失敗しました", analyzer.plugin_name)
            notify.critical(
                self._host.parent_widget, "解析エラー",
                str(PluginExecutionError(analyzer.plugin_name, f"「{analyzer.name}」の実行に失敗しました: {e}"))
            )
            return

        if result.new_datasets:
            target_folder = self._host.target_folder_for_new_dataset()
            for new_dataset in result.new_datasets:
                new_dataset.source_plugin = analyzer.plugin_name
                self._host.add_dataset_with_undo(
                    new_dataset, target_folder, description=f"解析による追加: {analyzer.name}"
                )

        if result.annotations:
            self._host.add_annotations_to_active_axis(result.annotations, f"解析による注釈追加: {analyzer.name}")

        if result.table is not None:
            if self.analysis_result_dialog is not None:
                self.analysis_result_dialog.close()
            self.analysis_result_dialog = ResultDialog(
                analyzer.name, f"[{analyzer.name}] の解析結果", self._host.parent_widget, csv_data=result.table
            )
            self.analysis_result_dialog.show()

        self._host.show_status(f"「{analyzer.name}」を実行しました")
