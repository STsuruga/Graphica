"""
プラグインが本体を操作するための窓口(プラグイン API 2.0)。

メニューの callback とパネルの widget_factory が受け取る。1つのタブと1つのプラグインの
組ごとに1つ作られるので、どのメソッドも「そのタブ」を相手にする(複数タブでも取り違えない)。
本体の内部(PlotterApp やその private メソッド)には、この窓口の外から触らないこと。
本体の実装は gui/plugin_context.py、テスト用は core.plugin_testing.FakePluginContext。
"""
from typing import TYPE_CHECKING, Any, Callable
if TYPE_CHECKING:
    from graphica.core.dataset import Dataset


class PluginContext:
    """プラグイン向けの窓口の仕様。メソッドの中身は実装側が持つ。"""

    # --- データセット ---

    def datasets(self) -> "list[Dataset]":
        """
        タブの全データセットを返す。

        Returns:
            list[Dataset]: 表示順。リスト自体はコピーなので、並べ替えても本体は変わらない。
                要素の Dataset は本体と同じオブジェクト。変更は set_dataset_properties() で行う。
        """
        raise NotImplementedError

    def current_dataset(self) -> "Dataset | None":
        """
        Returns:
            Dataset | None: データセット一覧で現在選ばれているもの。なければ None。
        """
        raise NotImplementedError

    def selected_datasets(self) -> "list[Dataset]":
        """
        Returns:
            list[Dataset]: データセット一覧で選択されているもの(複数選択を含む)。
        """
        raise NotImplementedError

    def add_dataset(self, dataset: "Dataset", description: str | None = None) -> None:
        """
        データセットを追加する。Undo で取り消せる。

        Args:
            dataset (Dataset): 追加するデータセット。
            description (str | None): 「元に戻す」メニューに出す説明。省略時は既定の文言。
        """
        raise NotImplementedError

    def set_dataset_properties(self, dataset: "Dataset", values: dict[str, Any], description: str | None = None) -> None:
        """
        データセットの属性をまとめて変更し、再描画する。Undo で取り消せる。

        Args:
            dataset (Dataset): 対象。datasets() などで得たもの。
            values (dict): {属性名: 新しい値}。例: {"color": "#1f77b4", "linewidth": 2.0}
            description (str | None): 「元に戻す」メニューに出す説明。
        Raises:
            AttributeError: Dataset に無い属性名が含まれる。
        """
        raise NotImplementedError

    def redraw(self) -> None:
        """グラフを描き直す。データセットの中身を直接変えたあとに呼ぶ。"""
        raise NotImplementedError

    # --- 変化の通知 ---

    def on_datasets_changed(self, callback: Callable[[], Any]) -> None:
        """
        データセットの追加・削除・変更・プロジェクトの読み込みのあとに callback() を呼ぶ。
        パネルの表示を最新に保つのに使う。描き直しのたびに呼ばれるので、callback は軽くする。

        Args:
            callback (callable): 引数なし。
        """
        raise NotImplementedError

    def on_selection_changed(self, callback: Callable[["Dataset | None"], Any]) -> None:
        """
        データセット一覧の選択が変わったら callback(current_dataset) を呼ぶ。

        Args:
            callback (callable): Dataset | None を1つ受け取る。
        """
        raise NotImplementedError

    # --- 画面 ---

    @property
    def parent_widget(self) -> Any:
        """
        Returns:
            QWidget | None: ダイアログの親にするウィンドウ。
        """
        raise NotImplementedError

    def show_message(self, text: str, title: str | None = None) -> None:
        """情報メッセージを表示する。title の省略時はプラグイン名。"""
        raise NotImplementedError

    def show_error(self, text: str, title: str | None = None) -> None:
        """エラーメッセージを表示する。title の省略時はプラグイン名。"""
        raise NotImplementedError

    # --- 保存場所 ---

    @property
    def data_dir(self) -> str:
        """
        Returns:
            str: このプラグイン専用の書き込み可能なフォルダ(無ければ作る)。設定やライブラリの保存先。
                本体のインストール先は読み取り専用のことがあるので、ここ以外には書かない。
        """
        raise NotImplementedError

    # --- 色 ---

    def named_colors(self) -> list[dict[str, str]]:
        """
        本体に登録された名前付きの色。

        Returns:
            list[dict]: [{"name": str, "color": "#rrggbb"}, ...]。並び順は利用者が決めた表示順。
        """
        raise NotImplementedError

    def set_named_colors(self, entries: list[dict[str, str]]) -> None:
        """
        名前付きの色を丸ごと置き換える。

        Args:
            entries (list[dict]): named_colors() と同じ形。
        Raises:
            core.named_colors.NamedColorError: 名前か色コードが不正、または名前が重複している。
        """
        raise NotImplementedError

    def color_palettes(self) -> dict[str, list[str]]:
        """
        利用者が作った配色パレット(組み込みのパレットは含まない)。

        Returns:
            dict[str, list[str]]: {パレット名: ["#rrggbb", ...]}
        """
        raise NotImplementedError

    def set_color_palettes(self, palettes: dict[str, list[str]]) -> None:
        """
        利用者の配色パレットを丸ごと置き換える。

        Args:
            palettes (dict[str, list[str]]): color_palettes() と同じ形。
        Raises:
            ValueError: 形が不正、または色コードが不正。
        """
        raise NotImplementedError

    def active_color_cycle(self) -> list[str]:
        """
        Returns:
            list[str]: いま選ばれているパレットの色(系列に順に割り当てる色)。
        """
        raise NotImplementedError
