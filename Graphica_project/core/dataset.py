import uuid
import numpy as np
import pandas as pd
from dataclasses import dataclass, field, fields, MISSING

@dataclass
class Dataset:
    """
    1つのプロット（線、散布図など）に関するすべての情報を保持するための
    データクラス (data class) です。
    
    @dataclass デコレータを使うことで、__init__ メソッドなどを自動的に生成してくれます。
    """
    
    # --- データそのものに関する情報 ---
    name: str             # 凡例 (Legend) に表示される名前 (例: "data1.csv")
    df: pd.DataFrame      # ★ プロットの元となるデータ全体 (DataFrame)
    x_col_name: str       # ★ 現在 X軸として選択されている「列名」
    y_col_name: str       # ★ 現在 Y軸として選択されている「列名」
    
    # --- @property (プロパティ) ---
    # これらはメソッドですが、アクセスする時 (例: ds.x_data) は
    # () が不要で、変数（属性）のように振る舞います。
    # df と col_name が変更されると、ここから取得されるデータも自動的に更新されます。
    
    @property
    def x_data(self) -> np.ndarray:
        """
        現在の X軸列名 (x_col_name) に基づいて、
        DataFrame (df) から X軸のデータを NumPy 配列として返します。
        """
        # .values は pandas Series を NumPy 配列に変換します
        return self.df[self.x_col_name].values
    
    @property
    def y_data(self) -> np.ndarray:
        """
        現在の Y軸列名 (y_col_name) に基づいて、
        DataFrame (df) から Y軸のデータを NumPy 配列として返します。
        """
        return self.df[self.y_col_name].values

    @property
    def x_err_data(self):
        """
        X軸の誤差列 (x_err_col_name) が設定されていれば、そのデータを
        NumPy 配列として返す。未設定 (None) ならエラーバーなしを表す None を返す。
        """
        if self.x_err_col_name and self.x_err_col_name in self.df.columns:
            return self.df[self.x_err_col_name].values
        return None

    @property
    def y_err_data(self):
        """Y軸の誤差列 (y_err_col_name) について x_err_data と同様。"""
        if self.y_err_col_name and self.y_err_col_name in self.df.columns:
            return self.df[self.y_err_col_name].values
        return None

    # --- スタイルと状態に関する情報 (デフォルト値付き) ---
    plot_type: str = 'Line'       # 'Line', 'Scatter', 'Line+Scatter'
    color: str = '#1f77b4'        # 16進数カラーコード (Matplotlib のデフォルト色)
    linestyle: str = '-'          # 実線 (Solid)
    linewidth: float = 1.5
    marker: str = 'o'             # マーカーの種類 (円)
    markersize: float = 6.0
    smoothing: bool = False       # CubicSpline で平滑化するかどうか
    alpha: float = 1.0            # 透明度 (0.0=完全に透明 ～ 1.0=不透明)

    # エラーバー表示用の誤差列名。None ならその軸のエラーバーは表示しない。
    x_err_col_name: str = field(default=None)
    y_err_col_name: str = field(default=None)

    # field(...) は、@dataclass でデフォルト値を設定する際の高度な方法です
    # default=None とすることで、初期化時に指定されなければ None が入ります
    fit_info: str = field(default=None) # 曲線フィットの結果文字列 (例: "y = 1.2x + 0.5")

    # default=False とすることで、初期値は False になります
    use_secondary_y: bool = field(default=False) # 第2Y軸（右側）を使うかどうか
    subplot_target: int = field(default=0)     # 描画先のサブプロット番号 (0始まり)
    
    # repr=False は、print(dataset) した時に、このフィールドを表示しない設定
    # (Matplotlib の <Figure ...> のような巨大なオブジェクトは表示しないのが一般的)
    artist: object = field(default=None, repr=False)

    # データセットのフォルダ分け機能 (gui/mixins/dataset_mixin.py) で、
    # ツリー上のどのアイテムがこの Dataset に対応するかを、名前に依存せず
    # 一意に特定するための ID。
    dataset_id: str = field(default_factory=lambda: uuid.uuid4().hex, repr=False)

    # --- データ編集操作 (core/commands.py の Undo/Redo コマンドから呼ばれる) ---
    # GUI (DataEditorDialog) の内部実装に依存させないため、
    # df の変更はすべてこのクラスの公開メソッド経由で行う。

    def set_cell(self, row_idx, col_name, value):
        """指定したセル (行インデックス, 列名) の値を更新する"""
        self.df.loc[row_idx, col_name] = value

    def add_row(self):
        """NaN で埋めた行を末尾に追加する"""
        new_row = pd.Series([np.nan] * len(self.df.columns), index=self.df.columns)
        self.df = pd.concat([self.df, new_row.to_frame().T], ignore_index=True)

    def delete_last_row(self):
        """末尾の行を削除する (add_row の取り消し用)"""
        if len(self.df) > 0:
            self.df = self.df.drop(self.df.index[-1])

    def delete_rows(self, row_indices):
        """指定したインデックスの行を削除し、インデックスを振り直す"""
        self.df = self.df.drop(row_indices).reset_index(drop=True)

    def restore_rows(self, deleted_data):
        """delete_rows で削除した行 (元のインデックス付き) を復元する"""
        restored_df = pd.concat([self.df, deleted_data])
        self.df = restored_df.sort_index().reset_index(drop=True)

    def is_column_in_use(self, col_name) -> bool:
        """列がプロットのX軸・Y軸、またはエラーバー用の誤差列として使用中かどうか"""
        return col_name in (self.x_col_name, self.y_col_name, self.x_err_col_name, self.y_err_col_name)

    def add_column(self, col_name):
        """NaN で埋めた列を追加する"""
        if col_name not in self.df.columns:
            self.df[col_name] = np.nan

    def remove_column(self, col_name):
        """列を削除する"""
        if col_name in self.df.columns:
            self.df = self.df.drop(columns=[col_name])

    def restore_column(self, col_name, column_data):
        """remove_column で削除した列を末尾に復元する"""
        if col_name not in self.df.columns:
            self.df[col_name] = column_data

    def __getstate__(self):
        """
        pickle保存時、artist (matplotlibのArtistへの生参照) は除外する。
        artist は再描画のたびに作り直される一時的なハンドルであり、
        Figure/Axes を巻き込んだ巨大なオブジェクトグラフになるため保存する意味がない。
        """
        state = self.__dict__.copy()
        state['artist'] = None
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        # 古い形式の.pklファイル(このフィールドが追加される前に保存されたもの)には
        # キーが存在しないため、dataclassのデフォルト値で補う。
        # (補わないと、後から追加したフィールドにアクセスした際にAttributeErrorになる)
        for f in fields(self):
            if f.name not in self.__dict__:
                if f.default is not MISSING:
                    self.__dict__[f.name] = f.default
                elif f.default_factory is not MISSING:
                    self.__dict__[f.name] = f.default_factory()