"""データセットの並び。描画の順(project.datasets)・一覧のツリー・保存用のフォルダ構造(dataset_group_tree)の 3 つと、
それらを合わせる規則をここに集める。

今の規則(変えるときはここだけ):
- 追加はツリーでは指定したフォルダの末尾。描画順は、最上位なら末尾、フォルダの中ならツリーで直前にあるデータセットの
  すぐ後(一覧と描画の重なりをそろえる。K-18)。保存済みの並びは変えないので、開いたプロジェクトの見た目は変わらない。
- ドラッグの並べ替えのあとでだけ、描画順をツリーの順(深さ優先)に合わせる。同じフォルダの中の並べ替えだけ Undo できる。
- 保存用のフォルダ構造は保存・比較の直前にツリーから作り、読み込みではそこからツリーを作り直す。
- 削除の Undo は、描画順の全体と各項目の親・位置を控えて戻す。
"""
from PySide6.QtCore import Qt

_DATASET_ROLE = Qt.ItemDataRole.UserRole


def item_dataset(item):
    """ツリーの項目のデータセット。フォルダなら None。"""
    return item.data(0, _DATASET_ROLE)


class DatasetOrder:

    def __init__(self, project, tree, make_dataset_item):
        # ツリーは組み立ての途中で差し替わるので、使うたびに取り出す
        self._project = project
        self._tree = tree
        self._make_dataset_item = make_dataset_item

    @property
    def tree(self):
        return self._tree()

    @property
    def datasets(self):
        return self._project.datasets

    # --- 探す ---

    def find_row(self, dataset):
        """描画順の位置。Dataset の == は DataFrame を比べて例外になるので、同一性(is)で探す。"""
        for i, ds in enumerate(self._project.datasets):
            if ds is dataset:
                return i
        return -1

    def dataset_items(self, parent_item=None):
        """データセットの葉を表示順(深さ優先)に返す。"""
        items = []
        source = self.tree.invisibleRootItem() if parent_item is None else parent_item
        for i in range(source.childCount()):
            child = source.child(i)
            if item_dataset(child) is not None:
                items.append(child)
            else:
                items.extend(self.dataset_items(child))
        return items

    def item_for(self, dataset):
        for item in self.dataset_items():
            if item_dataset(item) is dataset:
                return item
        return None

    def current_dataset(self):
        item = self.tree.currentItem()
        if item is None:
            return None
        return item_dataset(item)

    def selected_datasets(self):
        return [ds for item in self.tree.selectedItems() if (ds := item_dataset(item)) is not None]

    def target_folder(self):
        """選択中の項目がフォルダならそれ(新しいデータセットをその中に入れる)。"""
        current_item = self.tree.currentItem()
        if current_item is not None and item_dataset(current_item) is None:
            return current_item
        return None

    @staticmethod
    def top_level_items(items):
        """ほかの選択項目の子孫でないものだけ(フォルダと中身が両方選ばれていても二重に扱わないため)。"""
        item_ids = {id(it) for it in items}
        result = []
        for item in items:
            ancestor = item.parent()
            while ancestor is not None and id(ancestor) not in item_ids:
                ancestor = ancestor.parent()
            if ancestor is None:
                result.append(item)
        return result

    # --- 足す ---

    def append(self, dataset, parent_folder=None):
        """ツリーのフォルダの末尾と、それに合う描画順の位置に足す。"""
        item = self._make_dataset_item(dataset, parent_folder)
        position = len(self._project.datasets) if parent_folder is None else self._draw_position_for(item)
        self._project.datasets.insert(position, dataset)
        return item

    def _draw_position_for(self, item):
        """ツリーで直前にあるデータセットの描画順のすぐ後。前に無ければ直後のものの前、どちらも無ければ末尾。"""
        leaves = self.dataset_items()
        index = next(i for i, leaf in enumerate(leaves) if leaf is item)
        for leaf in reversed(leaves[:index]):
            row = self.find_row(item_dataset(leaf))
            if row != -1:
                return row + 1
        for leaf in leaves[index + 1:]:
            row = self.find_row(item_dataset(leaf))
            if row != -1:
                return row
        return len(self._project.datasets)

    def add_folder(self, name, parent_item=None):
        from PySide6.QtWidgets import QTreeWidgetItem

        item = QTreeWidgetItem([name])
        item.setData(0, _DATASET_ROLE, None)
        if parent_item is not None:
            parent_item.addChild(item)
        else:
            self.tree.addTopLevelItem(item)
        item.setExpanded(True)
        return item

    def detach_item(self, item):
        """ツリーから外す(親の子か最上位かで外し方が違う)。"""
        parent = item.parent()
        if parent is not None:
            parent.removeChild(item)
        else:
            index = self.tree.indexOfTopLevelItem(item)
            if index != -1:
                self.tree.takeTopLevelItem(index)

    def remove_added(self, dataset):
        """append() の取り消し。"""
        row = self.find_row(dataset)
        if row != -1:
            del self._project.datasets[row]
        item = self.item_for(dataset)
        if item is not None:
            self.detach_item(item)

    # --- 消す ---

    def removal(self, top_level_items):
        """項目(データセットかフォルダ)を消す手順と戻す手順。消すものが無ければ None。

        戻すために、描画順の全体と各項目の親・位置を控える。外した項目はこの手順が持つので、同じものを差し戻せる。
        戻り値は (消す手順, 戻す手順, 消えるデータセット)。
        """
        tree = self.tree
        snapshots = []  # [(item, parent_item_or_None, index_in_parent), ...]
        for item in top_level_items:
            parent = item.parent()
            index = parent.indexOfChild(item) if parent is not None else tree.indexOfTopLevelItem(item)
            if index == -1:
                continue
            snapshots.append((item, parent, index))
        if not snapshots:
            return None

        removed_datasets = []
        for item, _parent, _index in snapshots:
            dataset = item_dataset(item)
            if dataset is not None:
                removed_datasets.append(dataset)
            else:
                removed_datasets.extend(item_dataset(leaf) for leaf in self.dataset_items(item))

        datasets_before = list(self._project.datasets)

        def remove():
            # 操作中に currentItemChanged が出ないように
            tree.blockSignals(True)
            try:
                rows = sorted({row for ds in removed_datasets if (row := self.find_row(ds)) != -1}, reverse=True)
                for row in rows:
                    del self._project.datasets[row]
                # 同じ親の中でずれないよう、後ろから外す
                for item, parent, _index in sorted(snapshots, key=lambda s: s[2], reverse=True):
                    if parent is not None:
                        parent.removeChild(item)
                    else:
                        index = tree.indexOfTopLevelItem(item)
                        if index != -1:
                            tree.takeTopLevelItem(index)
            finally:
                tree.blockSignals(False)

        def restore():
            tree.blockSignals(True)
            try:
                for item, parent, index in sorted(snapshots, key=lambda s: s[2]):
                    if parent is not None:
                        parent.insertChild(min(index, parent.childCount()), item)
                    else:
                        tree.insertTopLevelItem(min(index, tree.topLevelItemCount()), item)
                # リストの中身だけ差し替える(描画順も戻る)
                self._project.datasets[:] = datasets_before
            finally:
                tree.blockSignals(False)

        return remove, restore, removed_datasets

    # --- 描画順とツリーの順 ---

    def tree_order(self):
        """ツリーの表示順(深さ優先)に並べたデータセット。"""
        return [item_dataset(item) for item in self.dataset_items()]

    def sort_tree_to_draw_order(self):
        """フォルダの中の並びを描画順に合わせる(並べ替えの Undo/Redo 用)。フォルダ自体は動かさない。"""
        tree = self.tree
        order_index = {id(ds): i for i, ds in enumerate(self._project.datasets)}
        selected_ids = {id(item_dataset(item)) for item in tree.selectedItems()}
        current_item = tree.currentItem()
        current_dataset = item_dataset(current_item) if current_item else None

        tree.blockSignals(True)

        def sort_children(parent_item):
            source = tree.invisibleRootItem() if parent_item is None else parent_item
            children = [source.child(i) for i in range(source.childCount())]

            dataset_positions = [i for i, c in enumerate(children) if item_dataset(c) is not None]
            dataset_items_sorted = sorted(
                (children[i] for i in dataset_positions),
                key=lambda it: order_index.get(id(item_dataset(it)), 0)
            )
            new_children = list(children)
            for pos, item in zip(dataset_positions, dataset_items_sorted):
                new_children[pos] = item

            for _ in range(source.childCount()):
                source.takeChild(0)
            for item in new_children:
                source.addChild(item)

            for item in new_children:
                if item_dataset(item) is None:
                    sort_children(item)

        sort_children(None)

        for item in self.dataset_items():
            ds = item_dataset(item)
            if id(ds) in selected_ids:
                item.setSelected(True)
            if ds is current_dataset:
                tree.setCurrentItem(item)
        tree.blockSignals(False)

    # --- 保存用のフォルダ構造 ---

    def group_tree(self):
        """ツリーから保存用のフォルダ構造を作る。"""
        def walk(parent_item):
            children = []
            source = self.tree.invisibleRootItem() if parent_item is None else parent_item
            for i in range(source.childCount()):
                child = source.child(i)
                dataset = item_dataset(child)
                if dataset is not None:
                    children.append({'dataset': dataset})
                else:
                    children.append({'name': child.text(0), 'children': walk(child)})
            return children
        return {'name': '', 'children': walk(None)}

    def rebuild_tree(self):
        """保存用のフォルダ構造からツリーを作り直す(読み込みのあと)。"""
        tree = self.tree
        tree.clear()

        def build(node, parent_item):
            for child_node in node.get('children', []):
                if 'dataset' in child_node:
                    self._make_dataset_item(child_node['dataset'], parent_item)
                else:
                    folder_item = self.add_folder(child_node.get('name', 'フォルダ'), parent_item)
                    build(child_node, folder_item)

        build(self._project.dataset_group_tree, None)

    # --- 検索 ---

    def filter_by_name(self, text):
        """名前に検索文字列を含むデータセットだけを出す。フォルダは中に1つでも当たりがあれば出す。"""
        query = text.strip().lower()

        def apply_filter(item):
            dataset = item_dataset(item)
            if dataset is not None:
                visible = (not query) or (query in dataset.name.lower())
                item.setHidden(not visible)
                return visible
            any_child_visible = False
            for i in range(item.childCount()):
                if apply_filter(item.child(i)):
                    any_child_visible = True
            item.setHidden(bool(query) and not any_child_visible)
            return any_child_visible or not query

        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            apply_filter(root.child(i))
