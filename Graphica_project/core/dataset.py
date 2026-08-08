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
    
    def __setattr__(self, name, value):
        """
        df / masked_row_indices への再代入 (dataset.df = new_df,
        dataset.masked_row_indices = [...]) を検知して、visible_df の
        キャッシュ(項目C-002)を自動的に無効化する。dfをインプレースで
        書き換える呼び出し (dataset.df[col] = ... 等) はこの経路を通らないため、
        呼び出し側で invalidate_visible_df_cache() を明示的に呼ぶ必要がある。
        """
        object.__setattr__(self, name, value)
        if name in ('df', 'masked_row_indices'):
            self.invalidate_visible_df_cache()

    def invalidate_visible_df_cache(self):
        """
        df を dataset.df[col] = ... のようにインプレースで書き換えた後に
        明示的に呼び出す(df/masked_row_indices の再代入自体は __setattr__
        経由で自動的に無効化されるため、この呼び出しは不要)。
        """
        self.__dict__['_version'] = self.__dict__.get('_version', 0) + 1

    @property
    def visible_df(self) -> pd.DataFrame:
        """
        masked_row_indices に含まれる行(フィット/プロットから除外された行)を
        取り除いた DataFrame。行そのものは dataset.df から削除しない
        「非破壊的なマスク」機能(項目36)のため、x_data/y_data等はすべて
        こちらを経由してデータを取得する。

        1回の描画で x_data/y_data/x_err_data/y_err_data が独立にこのプロパティを
        呼ぶため、都度フィルタし直すと最大4回の無駄なDataFrameコピーが発生する
        (項目C-002)。version番号(__setattr__/invalidate_visible_df_cache()で
        更新)が前回と同じ間はキャッシュを再利用する。
        """
        version = self.__dict__.get('_version', 0)
        if self.__dict__.get('_visible_df_cache_version') != version:
            if not self.masked_row_indices:
                cache = self.df
            else:
                cache = self.df[~self.df.index.isin(self.masked_row_indices)]
            self.__dict__['_visible_df_cache'] = cache
            self.__dict__['_visible_df_cache_version'] = version
        return self.__dict__['_visible_df_cache']

    @property
    def x_data(self) -> np.ndarray:
        """
        現在の X軸列名 (x_col_name) に基づいて、
        DataFrame (df) から X軸のデータを NumPy 配列として返します。
        (マスクされた行は除外される)
        """
        # .values は pandas Series を NumPy 配列に変換します
        return self.visible_df[self.x_col_name].values

    @property
    def y_data(self) -> np.ndarray:
        """
        現在の Y軸列名 (y_col_name) に基づいて、
        DataFrame (df) から Y軸のデータを NumPy 配列として返します。
        (マスクされた行は除外される)
        """
        return self.visible_df[self.y_col_name].values

    @property
    def x_err_data(self):
        """
        X軸の誤差列 (x_err_col_name) が設定されていれば、そのデータを
        NumPy 配列として返す。未設定 (None) ならエラーバーなしを表す None を返す。
        (マスクされた行は除外される。x_data/y_dataと長さを揃える必要があるため)
        """
        if self.x_err_col_name and self.x_err_col_name in self.df.columns:
            return self.visible_df[self.x_err_col_name].values
        return None

    @property
    def y_err_data(self):
        """Y軸の誤差列 (y_err_col_name) について x_err_data と同様。"""
        if self.y_err_col_name and self.y_err_col_name in self.df.columns:
            return self.visible_df[self.y_err_col_name].values
        return None

    # --- スタイルと状態に関する情報 (デフォルト値付き) ---
    plot_type: str = 'Line'       # 'Line', 'Scatter', 'Line+Scatter', 'Area', 'Bar'
    color: str = '#1f77b4'        # 16進数カラーコード (Matplotlib のデフォルト色)
    linestyle: str = '-'          # 実線 (Solid)
    linewidth: float = 1.5
    marker: str = 'o'             # マーカーの種類 (円)
    markersize: float = 6.0
    smoothing: bool = False       # CubicSpline で平滑化するかどうか
    alpha: float = 1.0            # 透明度 (0.0=完全に透明 ～ 1.0=不透明)

    # プロットへのグラデーション適用(項目79): 線の色を開始色(color)から終端色
    # (gradient_color2)へ連続的に変化させる「線ストロークグラデーション」、および
    # Area(塗りつぶし)プロットの塗り領域をグラデーションにする「塗りグラデーション」。
    # gradient_target は 'line'(線のみ) / 'fill'(塗りのみ) / 'both'(両方、Areaのみ意味を持つ)。
    gradient_enabled: bool = False
    gradient_color2: str = '#ffffff'   # グラデーションの終端色(開始色は既存の color を流用する)
    gradient_target: str = 'line'      # 'line' / 'fill' / 'both'

    # ウォーターフォールプロット(項目80、項目109で独立したプロット種別から
    # 「積み重ねオプション」に変更): 時間/濃度変化などのスペクトルを、Z軸方向に
    # ずらして立体的に配置したように見せる表示。実際には3Dプロット
    # (mpl_toolkits.mplot3d)は使わず、同一サブプロット内の waterfall_enabled=True
    # なデータセットだけをリスト順に0始まりのインデックスで数え、そのインデックス
    # 番目のデータセットのX/Yを (index * waterfall_offset_x, index * waterfall_offset_y)
    # だけずらして通常の2D Axesに重ね描きすることで疑似的な立体感を出す
    # (gui/canvas.py の _draw_data)。plot_type とは独立したフラグなので、
    # Line/Scatter/Line+Scatter/Area/Bar のどの見た目とも組み合わせられる。
    waterfall_enabled: bool = False
    waterfall_offset_x: float = 0.0
    waterfall_offset_y: float = 1.0

    # データポイントラベル表示 (各点の脇に値を表示するかどうか、および表示する列)
    show_point_labels: bool = False
    # None なら Y値そのものをラベルにする。列名を指定するとその列の値を表示する。
    point_label_col_name: str = field(default=None)

    # エラーバー表示用の誤差列名。None ならその軸のエラーバーは表示しない。
    x_err_col_name: str = field(default=None)
    y_err_col_name: str = field(default=None)

    # 誤差の表示形式(項目C-502): 'bar'(エラーバー、既定) / 'band'(fill_betweenに
    # よる誤差バンド) / 'both'(両方)。x_err_col_name/y_err_col_nameがどちらも
    # Noneの場合はどの設定でも何も描画されない(gui/canvas.py参照)。
    error_display: str = 'bar'

    # 外れ値のマスク機能(項目36): 行を削除せず「フィット/プロットから除外」する
    # ためのマーカー。df.index のラベルのリスト(位置ではなく)。
    # x_data/y_data/x_err_data/y_err_data はこのリストに含まれる行を自動的に除いて返す。
    masked_row_indices: list = field(default_factory=list)

    # field(...) は、@dataclass でデフォルト値を設定する際の高度な方法です
    # default=None とすることで、初期化時に指定されなければ None が入ります
    fit_info: str = field(default=None) # 曲線フィットの結果文字列 (例: "y = 1.2x + 0.5")

    # プラグインのregister_processor/register_analyzer(項目C-1/C-2)が生成した
    # Datasetについて、生成元プラグイン名を残す(項目C-3、provenanceの土台)。
    # プラグイン以外の通常の操作で作られたDatasetはNoneのまま。
    source_plugin: str = field(default=None)

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
        self.invalidate_visible_df_cache()

    def add_row(self):
        """
        NaN で埋めた行を末尾に追加する。
        ignore_index=True で全行を振り直すと、delete_rows が (restore_rows との
        整合性のため) 保持しているインデックスの欠番が失われてしまうため、
        既存の行には触れず、新しい一意なラベルを1つだけ割り当てる。
        """
        new_index = (self.df.index.max() + 1) if len(self.df) > 0 else 0
        new_row = pd.Series([np.nan] * len(self.df.columns), index=self.df.columns, name=new_index)
        self.df = pd.concat([self.df, new_row.to_frame().T])

    def delete_last_row(self):
        """末尾の行を削除する (add_row の取り消し用)"""
        if len(self.df) > 0:
            self.df = self.df.drop(self.df.index[-1])

    def delete_rows(self, row_indices):
        """
        指定したインデックスの行を削除する。
        ★ reset_index(drop=True) はしない (意図的)。
        ここでインデックスを振り直してしまうと、restore_rows に渡される
        deleted_data (削除前のインデックスラベルを保持したスライス) のラベルと
        噛み合わなくなり、Undo(復元)時に行の並び順が崩れてしまう
        (元は中間の行を削除して復元すると隣の行と入れ替わってしまうバグがあった)。

        ★ バグ修正: masked_row_indices に削除対象のラベルが残っていると、
        add_row() が (df.index.max() + 1 により) 同じラベルを新しい行に
        再利用してしまい、その新規行が visible_df から除外されて
        グラフ/フィット/ピーク検出に一切現れなくなる(マスクした行を
        そのまま永久削除し、後で新しい行を追加した際に実際に発生する
        サイレントなデータ欠落バグだった)。削除される行は「マスク解除」
        したのと同じ意味になるため、ここで欠番を掃除しておく。
        """
        self.df = self.df.drop(row_indices)
        if self.masked_row_indices:
            deleted_set = set(row_indices)
            remaining_mask = [idx for idx in self.masked_row_indices if idx not in deleted_set]
            if len(remaining_mask) != len(self.masked_row_indices):
                self.masked_row_indices = remaining_mask

    def restore_rows(self, deleted_data):
        """delete_rows で削除した行 (元のインデックス付き) を、元の位置に復元する。
        ★ バグ修正: delete_rows と同じ理由で reset_index(drop=True) はしない。
        ここでラベルを振り直すと、それ以前に(このUndoとは無関係に)別の行が
        永久に削除されていた場合、既存の全行のラベルがずれてしまい、後続の
        EditCellCommand.undo() 等が古いラベルで別の行(あるいは存在しない
        ラベル=新規のゴースト行)を誤って操作してしまう(delete_rowsが
        意図的に欠番を保持しているのと矛盾していた、実際に発生するデータ
        破損バグだった)。"""
        restored_df = pd.concat([self.df, deleted_data])
        self.df = restored_df.sort_index()

    def is_column_in_use(self, col_name) -> bool:
        """列がプロットのX軸・Y軸、またはエラーバー用の誤差列として使用中かどうか"""
        return col_name in (self.x_col_name, self.y_col_name, self.x_err_col_name, self.y_err_col_name)

    def add_column(self, col_name):
        """NaN で埋めた列を追加する"""
        if col_name not in self.df.columns:
            self.df[col_name] = np.nan
            self.invalidate_visible_df_cache()

    def remove_column(self, col_name):
        """列を削除する"""
        if col_name in self.df.columns:
            self.df = self.df.drop(columns=[col_name])

    def rename_column(self, old_name, new_name):
        """
        列名を変更する(項目64)。X/Y軸・誤差列・データ点ラベル列としてその列名を
        参照している設定があれば、新しい列名に追従させる(参照が切れないようにするため)。
        """
        if old_name not in self.df.columns or old_name == new_name:
            return
        self.df = self.df.rename(columns={old_name: new_name})
        if self.x_col_name == old_name:
            self.x_col_name = new_name
        if self.y_col_name == old_name:
            self.y_col_name = new_name
        if self.x_err_col_name == old_name:
            self.x_err_col_name = new_name
        if self.y_err_col_name == old_name:
            self.y_err_col_name = new_name
        if self.point_label_col_name == old_name:
            self.point_label_col_name = new_name

    def restore_column(self, col_name, column_data):
        """remove_column で削除した列を末尾に復元する"""
        if col_name not in self.df.columns:
            self.df[col_name] = column_data
            self.invalidate_visible_df_cache()

    # --- JSON形式でのプロジェクト保存(.graphica)対応 (models/project.py から利用) ---
    # pickleの__getstate__/__setstate__と同様の役割を、JSONでも往復できる
    # プレーンなdict形式で提供する。

    def to_dict(self) -> dict:
        """
        このDatasetをJSONシリアライズ可能なdictに変換する。
        artist (matplotlibのArtistへの生参照) は__getstate__同様に除外する。
        df はdtype情報を失わないよう専用の形式(_df_to_dict)に変換する。
        """
        result = {}
        for f in fields(self):
            if f.name in ('artist', 'df'):
                continue
            value = getattr(self, f.name)
            if f.name == 'masked_row_indices':
                # numpy.int64 が紛れ込むことがあるため、素のintに揃えておく
                # (JSONEncoder側の安全網に頼らず、発生源で明示的に変換する)
                value = [int(v) for v in value]
            result[f.name] = value
        result['df'] = self._df_to_dict(self.df)
        return result

    @classmethod
    def from_dict(cls, data: dict) -> 'Dataset':
        """to_dict() で得たdictからDatasetを復元する。

        古いスキーマ(このメソッド/フィールドが追加される前)のJSONファイルでも
        クラッシュしないよう、__setstate__ と同じ「dataclassのデフォルト値で
        不足分を補う」方式を踏襲する。
        """
        obj = cls.__new__(cls)
        state = {}
        df_data = data.get('df')
        state['df'] = cls._df_from_dict(df_data) if df_data is not None else pd.DataFrame()
        state['artist'] = None
        for f in fields(cls):
            if f.name in ('df', 'artist'):
                continue
            if f.name in data:
                value = data[f.name]
                if f.name == 'masked_row_indices' and value is not None:
                    value = [int(v) for v in value]
                state[f.name] = value
            elif f.default is not MISSING:
                state[f.name] = f.default
            elif f.default_factory is not MISSING:
                state[f.name] = f.default_factory()
            else:
                # デフォルト値を持たない必須フィールド(name/x_col_name/y_col_name)が
                # 欠けている場合、黙って未設定のままにすると後で無関係な箇所での
                # AttributeError として現れ原因が分かりにくくなる。壊れた/手編集された
                # .graphicaファイルであることが明確になるよう、この場でエラーにする。
                raise ValueError(
                    f"Datasetの復元に失敗しました: 必須フィールド '{f.name}' がありません。"
                    "壊れているか、対応していない形式のファイルの可能性があります。"
                )
        # 項目109: ウォーターフォールは独立したplot_type値から、任意の種別と
        # 組み合わせられる独立フラグ(waterfall_enabled)に変更した。移行期間の
        # プロジェクトファイルに残っている可能性がある古い値を読み替える。
        if state.get('plot_type') == 'Waterfall':
            state['plot_type'] = 'Line'
            state['waterfall_enabled'] = True

        obj.__dict__.update(state)
        return obj

    @staticmethod
    def _df_to_dict(df: pd.DataFrame) -> dict:
        """
        DataFrameを、dtypeフィデリティを保ったままJSON化できるdictに変換する。
        datetime64列はTimestampがJSON非対応のため、ISO8601文字列(NaTはNone)に
        変換してから格納する。それ以外の列は素のリストに変換する(float列の
        NaNはPythonのfloat('nan')のまま残り、json.dumpのデフォルト挙動で
        `NaN`トークンとして出力され、json.loadで読み戻すとfloat('nan')に
        戻るため、NaNがnull等の別の値に化けることはない)。
        """
        dtypes = {col: str(dtype) for col, dtype in df.dtypes.items()}
        data = {}
        for col in df.columns:
            series = df[col]
            if pd.api.types.is_datetime64_any_dtype(series):
                data[col] = [
                    None if pd.isna(v) else pd.Timestamp(v).isoformat()
                    for v in series
                ]
            else:
                data[col] = series.tolist()
        return {
            'columns': list(df.columns),
            'index': list(df.index),
            'index_dtype': str(df.index.dtype),
            'data': data,
            'dtypes': dtypes,
        }

    @staticmethod
    def _df_from_dict(d: dict) -> pd.DataFrame:
        """_df_to_dict() の逆変換。dtypes情報を使って元の型に復元する。"""
        columns = d.get('columns', [])
        index = d.get('index', [])
        data = d.get('data', {})
        dtypes = d.get('dtypes', {})
        index_dtype = d.get('index_dtype')

        df = pd.DataFrame(index=index)
        if index_dtype:
            # ★ 0行のDataFrameは index=[] から素のIndexを作ると dtype が
            # 'object' になり、元(RangeIndex/int64等)と食い違うため明示的に揃える。
            # 行が1件以上あれば通常pandasが値からdtypeを正しく推定するため
            # 実害は出ないが、この境界条件を含めて常に明示しておく。
            try:
                df.index = df.index.astype(index_dtype)
            except (TypeError, ValueError):
                pass
        for col in columns:
            col_data = data.get(col, [])
            dtype_str = dtypes.get(col)
            if dtype_str and dtype_str.startswith('datetime64'):
                series = pd.to_datetime(pd.Series(col_data, index=index))
            else:
                series = pd.Series(col_data, index=index)
                if dtype_str:
                    try:
                        series = series.astype(dtype_str)
                    except (TypeError, ValueError):
                        # 未知/変換不能なdtype文字列の場合は推定された型のまま使う
                        pass
            df[col] = series
        # 列の並び順を元の順序に揃える(dictのキー順に依存しないように)
        if columns:
            df = df[columns]
        return df

    def __getstate__(self):
        """
        pickle保存時、artist (matplotlibのArtistへの生参照) は除外する。
        artist は再描画のたびに作り直される一時的なハンドルであり、
        Figure/Axes を巻き込んだ巨大なオブジェクトグラフになるため保存する意味がない。
        """
        state = self.__dict__.copy()
        state['artist'] = None
        # visible_dfキャッシュ(C-002)は内部実装の都合であり、シリアライズ対象外
        # (再構築後は次回アクセス時に自動的に再計算される)。
        for cache_key in ('_visible_df_cache', '_visible_df_cache_version', '_version'):
            state.pop(cache_key, None)
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
        # 項目109: ウォーターフォールを独立したplot_type値から独立フラグに変更した
        # 際の移行(from_dictと同じ理由)。
        if self.__dict__.get('plot_type') == 'Waterfall':
            self.__dict__['plot_type'] = 'Line'
            self.__dict__['waterfall_enabled'] = True