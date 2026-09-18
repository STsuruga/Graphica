# gui/provenance_panel.py
"""
処理履歴(provenance、項目C-1101)をツリー表示する専用ドックパネル。
gui/residual_panel.py(項目C-406)と同じ「メインキャンバスとは別の、選択状態に
連動する小さな独立パネル」という確立されたパターンを踏襲する。選択中の
データセットが切り替わるたびに refresh(dataset, project) が呼ばれる
(gui/mixins/dataset_mixin.py の _update_ui_state 内)。

ツリー構造: ルート=選択中のデータセット名。その下に「操作内容」ノード
(describe_operationで日本語化)、さらにその下に「その操作の元になった
データセット」ノードを配置し、元データセット自身もprovenanceを持っていれば
同じパターンで再帰的に祖先までたどる。元データセットが既に削除されている
場合は「(削除済み)」と表示して再帰を打ち切る(provenanceが親のIDだけでなく
名前も保持しているのはこのため)。
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem

from core.methods_text import describe_operation


class ProvenancePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.placeholder_label = QLabel(
            "処理履歴(フィット・ベースライン補正・平滑化等で生成された\n"
            "データセット)を選択すると、ここに処理の流れが表示されます。"
        )
        self.placeholder_label.setWordWrap(True)
        self.placeholder_label.setStyleSheet("color: gray; padding: 12px;")
        layout.addWidget(self.placeholder_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        layout.addWidget(self.tree)
        self.tree.setVisible(False)

    def refresh(self, dataset, project):
        """
        選択中のデータセット(非選択時、またはprovenanceを持たない元データの
        場合はNoneでも安全)と、祖先を辿るためのprojectを受けてツリーを描き直す。
        """
        self.tree.clear()
        if dataset is None:
            self.tree.setVisible(False)
            self.placeholder_label.setVisible(True)
            return

        self.placeholder_label.setVisible(False)
        self.tree.setVisible(True)

        root_item = QTreeWidgetItem([dataset.name])
        self.tree.addTopLevelItem(root_item)
        self._add_provenance_children(root_item, dataset, project, frozenset())
        self.tree.expandAll()

    def _add_provenance_children(self, parent_item, dataset, project, visited):
        """
        dataset自身を生成した操作+その元データセットを、parent_itemの子として
        追加し、元データセット側も再帰的に辿る。visitedは循環参照(理論上
        発生しないはずだが、壊れた/手編集されたプロジェクトファイルへの
        安全策)を検知するためのdataset_idの集合。
        """
        if dataset is None or not dataset.provenance or dataset.dataset_id in visited:
            return
        visited = visited | {dataset.dataset_id}

        operation_item = QTreeWidgetItem([describe_operation(dataset.provenance)])
        parent_item.addChild(operation_item)

        source_ids = dataset.provenance.get('source_dataset_ids') or []
        source_names = dataset.provenance.get('source_dataset_names') or []
        for i, source_id in enumerate(source_ids):
            source_dataset = next((ds for ds in project.datasets if ds.dataset_id == source_id), None)
            fallback_name = source_names[i] if i < len(source_names) else "不明"
            if source_dataset is None:
                operation_item.addChild(QTreeWidgetItem([f"{fallback_name}(削除済み)"]))
                continue
            source_item = QTreeWidgetItem([source_dataset.name])
            operation_item.addChild(source_item)
            self._add_provenance_children(source_item, source_dataset, project, visited)
