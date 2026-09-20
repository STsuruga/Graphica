"""選んだデータセットの処理の履歴をツリーで見せるドック。

操作の下にその元のデータセットを置き、元にも履歴があれば祖先まで辿る。元が消されていれば「(削除済み)」で止める
(履歴が親の ID だけでなく名前も持つのはこのため)。
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem

from graphica.core.methods_text import describe_operation


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
        """dataset は None でもよい。project は祖先を辿るのに使う。"""
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
        """dataset を作った操作と元のデータセットを parent_item の下に足し、元も辿る。visited で循環を止める。"""
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
