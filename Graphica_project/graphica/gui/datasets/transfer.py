"""データセットをタブの外とやり取りするメニューの入口。本体は gui/datasets/operations/transfer.py。"""
from graphica.gui.datasets.operations.runner import OperationState, run_operation
from graphica.gui.datasets.operations.transfer import TRANSFER_OPERATIONS


class TransferController:
    """データセットをタブの外(ファイル・別のタブ)とやり取りする。"""

    def __init__(self, host):
        self._host = host
        self._state = OperationState()

    @property
    def copied_style(self):
        return self._state.copied_style

    def _run(self, name):
        run_operation(TRANSFER_OPERATIONS[name], self._host, self._state)

    def export_data(self):
        self._run("export_data")

    def copy_or_move_to_tab(self, move):
        self._run("move_to_tab" if move else "copy_to_tab")

    def copy_style(self):
        self._run("copy_style")

    def paste_style(self):
        self._run("paste_style")

    def reload_from_source(self):
        self._run("reload_from_source")

    def copy_methods_text(self):
        self._run("copy_methods_text")
