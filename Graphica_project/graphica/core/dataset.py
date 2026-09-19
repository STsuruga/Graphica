import uuid
import warnings
import numpy as np
import pandas as pd
from dataclasses import dataclass, field, fields, MISSING

# 線種は短い記号('-')とコンボの表示名('solid')の両方で保存されている。保存値は書き換えず
# (既存のプロジェクトのため)、表示と比較の直前に揃える。
LINESTYLE_NAMES = ('solid', 'dashed', 'dotted', 'dashdot')
_LINESTYLE_ALIASES = {
    '-': 'solid', 'solid': 'solid',
    '--': 'dashed', 'dashed': 'dashed',
    ':': 'dotted', 'dotted': 'dotted',
    '-.': 'dashdot', 'dashdot': 'dashdot',
}


def linestyle_name(value):
    """プロパティ欄の表示名に揃える。線を描かない値や未知の値は None。"""
    if value is None:
        return None
    return _LINESTYLE_ALIASES.get(str(value).strip().lower())

# z_col_name の値で点を配色する散布図。値は保存されるので変えない(変えると既存のプロジェクトが Line に戻る)。
# 種類の欄の幅は最長の項目で決まり、長くするとドックに横スクロールバーが出るので 15 文字に収めている。
COLOR_BY_COLUMN_PLOT_TYPE = 'Z-Color Scatter'


@dataclass
class Dataset:
    """1つの系列のデータと見た目。"""
    
    name: str             # 凡例に出る名前
    df: pd.DataFrame
    x_col_name: str
    y_col_name: str


    def __setattr__(self, name, value):
        """df と masked_row_indices の再代入で visible_df のキャッシュを捨てる。

        df をその場で書き換えたとき(dataset.df[col] = ...)はここを通らないので、invalidate_visible_df_cache() を呼ぶ。
        """
        object.__setattr__(self, name, value)
        if name in ('df', 'masked_row_indices'):
            self.invalidate_visible_df_cache()

    def invalidate_visible_df_cache(self):
        """df をその場で書き換えた後に呼ぶ(再代入なら自動で捨てられる)。"""
        self.__dict__['_version'] = self.__dict__.get('_version', 0) + 1

    @property
    def visible_df(self) -> pd.DataFrame:
        """masked_row_indices の行を除いた DataFrame。x_data などはすべてここを通る。

        1回の描画で x_data / y_data / 誤差が別々に呼ぶので、版が同じ間はキャッシュを使う。
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
    def z_grid(self):
        """data_kind='2d_grid' の格子({'x_grid', 'y_grid', 'z_grid', 'is_regular'})。それ以外は None。

        散在データの補間は重いのでキャッシュする。列名や補間の設定は版番号を上げないので、キャッシュのキーに含める。
        """
        if self.data_kind != '2d_grid' or not self.z_col_name:
            return None

        from graphica.core.grid_data import compute_z_grid, GridDataError

        resolution_key = tuple(self.grid_resolution) if self.grid_resolution else None
        version = self.__dict__.get('_version', 0)
        cache_key = (
            version, self.x_col_name, self.y_col_name, self.z_col_name,
            self.grid_interp_method, resolution_key,
        )
        if self.__dict__.get('_z_grid_cache_key') != cache_key:
            df = self.visible_df
            if self.z_col_name not in df.columns:
                grid = None
            else:
                try:
                    grid = compute_z_grid(
                        df[self.x_col_name].values, df[self.y_col_name].values,
                        df[self.z_col_name].values,
                        interp_method=self.grid_interp_method, resolution=resolution_key,
                    )
                except GridDataError:
                    grid = None
            self.__dict__['_z_grid_cache'] = grid
            self.__dict__['_z_grid_cache_key'] = cache_key
        return self.__dict__['_z_grid_cache']

    @property
    def x_data(self) -> np.ndarray:
        """X の列の値(マスクした行を除く)。"""
        return self.visible_df[self.x_col_name].values

    @property
    def y_data(self) -> np.ndarray:
        """Y の列の値(マスクした行を除く)。"""
        return self.visible_df[self.y_col_name].values

    @property
    def x_err_data(self):
        """X の誤差の列の値。列が未設定なら None(エラーバーなし)。x_data と長さが揃う。"""
        if self.x_err_col_name and self.x_err_col_name in self.df.columns:
            return self.visible_df[self.x_err_col_name].values
        return None

    @property
    def z_data(self):
        """Z の列の値。未設定か列が無ければ None。

        2D マップと 'Z-Color Scatter' の色が使う。visible_df を通すので、マスクしても点と色がずれない。
        """
        if self.z_col_name and self.z_col_name in self.df.columns:
            return self.visible_df[self.z_col_name].values
        return None

    @property
    def y_err_data(self):
        """Y の誤差の列の値。x_err_data と同じ。"""
        if self.y_err_col_name and self.y_err_col_name in self.df.columns:
            return self.visible_df[self.y_err_col_name].values
        return None

    # 'Line', 'Scatter', 'Line+Scatter', 'Area', 'Bar', 'Step', 'Density Scatter', 'Z-Color Scatter'、またはプラグインの種類
    plot_type: str = 'Line'
    color: str = '#1f77b4'
    linestyle: str = '-'
    linewidth: float = 1.5
    marker: str = 'o'
    markersize: float = 6.0
    smoothing: bool = False
    # 'cubic_spline'(200点に補間)/ 'moving_average' / 'median' / 'gaussian'(点の数はそのまま)
    smoothing_method: str = 'cubic_spline'
    alpha: float = 1.0

    # 線の色を color から gradient_color2 へ変える。'fill' と 'both' は Area の塗りにも効く
    gradient_enabled: bool = False
    gradient_color2: str = '#ffffff'
    gradient_target: str = 'line'      # 'line' / 'fill' / 'both'

    # ウォーターフォール(積み重ね)。種類とは独立で、同じサブプロットの有効な系列を順に offset ずつずらして重ねる
    waterfall_enabled: bool = False
    waterfall_offset_x: float = 0.0
    waterfall_offset_y: float = 1.0
    # 手前の系列の下を背景色で塗り、奥の系列を隠す
    waterfall_occlusion_enabled: bool = True

    # 奥の系列ほど Y をわずかに縮めて奥行きを出す
    waterfall_depth_shrink_enabled: bool = False
    # 1段あたりの縮小率(下限は canvas の WATERFALL_DEPTH_SHRINK_MIN_SCALE)
    waterfall_depth_shrink_ratio: float = 0.03

    show_point_labels: bool = False
    # None なら Y の値をラベルにする
    point_label_col_name: str = field(default=None)

    # None ならその軸のエラーバーは描かない
    x_err_col_name: str = field(default=None)
    y_err_col_name: str = field(default=None)

    # 'bar' / 'band' / 'both'
    error_display: str = 'bar'

    # 描画・フィット・解析から除く行。位置ではなく df.index のラベル
    masked_row_indices: list = field(default_factory=list)

    fit_info: str = field(default=None)  # 表示用のフィット結果の文字列

    # フィット結果(fit_type, params, param_errors, covariance, r_squared, residuals など)。
    # pickle と JSON の両方で往復できるよう、Python の素の型だけにする。
    fit_result: dict = field(default=None)

    # "confidence" / "prediction" / None。df の 'y_lower' / 'y_upper' 列を帯として描く
    fit_band_display: str = field(default=None)

    # プラグインの処理・解析が作った系列なら、そのプラグイン名
    source_plugin: str = field(default=None)

    # 読み込んだファイルの絶対パス(「再読み込み」用)。ファイルから作っていない系列は None。
    # source_sheet は Excel のシート名(CSV と単一シートでは None)
    source_file: str = field(default=None)
    source_sheet: str = field(default=None)

    # 欠損値の描き方。描くときだけ効き、データは変えない。
    # 'gap'(線を切る)/ 'ffill'(前の値で埋める)/ 'drop'(除いてつなぐ)
    nan_policy: str = field(default='gap')

    # この系列を作った直近1回の操作({operation, params, source_dataset_ids, source_dataset_names, timestamp})。
    # 全体の履歴は source_dataset_ids を辿って組み立てる。読み込んだデータは None
    provenance: dict = field(default=None)

    use_secondary_y: bool = field(default=False)
    subplot_target: int = field(default=0)     # 描画先のサブプロット(0始まり)

    # '2d_grid' なら df は x/y/z の長形式で、z_grid が格子を組み立てる
    data_kind: str = field(default='1d')
    z_col_name: str = field(default=None)
    # 散在データの補間: 'linear' / 'cubic' / 'nearest'
    grid_interp_method: str = field(default='linear')
    # [nx, ny]、None なら自動。JSON で tuple が list になるので最初から list
    grid_resolution: list = field(default=None)
    # vmin / vmax が None ならデータの最小・最大
    colormap: str = field(default='viridis')
    vmin: float = field(default=None)
    vmax: float = field(default=None)

    # 'heatmap' / 'contour' / 'contour_filled' / 'heatmap_contour'
    map_display_mode: str = field(default='heatmap')
    contour_levels: int = field(default=10)

    # False なら描画とエクスポートから外す(系列は残る)
    visible: bool = field(default=True)
    
    artist: object = field(default=None, repr=False)

    # 名前に依らずに系列を特定する ID
    dataset_id: str = field(default_factory=lambda: uuid.uuid4().hex, repr=False)

    # df はこのクラスのメソッドで変える(Undo のコマンドがこれを呼ぶ)

    def set_cell(self, row_idx, col_name, value):
        # 列の型に入らない値(bool 列の NaN、日時列の文字列など)は、列を object 型に
        # してから入れる。pandas 3 は暗黙の型変換をやめて例外を出す。
        with warnings.catch_warnings():
            warnings.simplefilter("error", FutureWarning)
            try:
                self.df.loc[row_idx, col_name] = value
            except (FutureWarning, TypeError):
                self.df[col_name] = self.df[col_name].astype(object)
                self.df.loc[row_idx, col_name] = value
        self.invalidate_visible_df_cache()

    def add_row(self):
        """NaN の行を末尾に足す。

        全体を振り直すと delete_rows が残した欠番(restore_rows に要る)が消えるので、新しいラベルを1つだけ割り当てる。
        """
        new_index = (self.df.index.max() + 1) if len(self.df) > 0 else 0
        new_row = pd.Series([np.nan] * len(self.df.columns), index=self.df.columns, name=new_index)
        self.df = pd.concat([self.df, new_row.to_frame().T])

    def delete_last_row(self):
        """末尾の行を削除する(add_row の取り消し用)。"""
        if len(self.df) > 0:
            self.df = self.df.drop(self.df.index[-1])

    def delete_rows(self, row_indices):
        """行を削除する。index は振り直さない(restore_rows が元のラベルで戻すため)。

        削除した行のラベルは masked_row_indices からも消す(残すと、同じラベルで足した新しい行が隠れる)。
        """
        self.df = self.df.drop(row_indices)
        if self.masked_row_indices:
            deleted_set = set(row_indices)
            remaining_mask = [idx for idx in self.masked_row_indices if idx not in deleted_set]
            if len(remaining_mask) != len(self.masked_row_indices):
                self.masked_row_indices = remaining_mask

    def restore_rows(self, deleted_data):
        """delete_rows で消した行を元のラベルで戻す。

        振り直すと、ほかの削除で空いた欠番がずれ、後続の Undo が別の行を触る。
        """
        restored_df = pd.concat([self.df, deleted_data])
        self.df = restored_df.sort_index()

    def is_column_in_use(self, col_name) -> bool:
        """X/Y、または誤差の列として使っているか。"""
        return col_name in (self.x_col_name, self.y_col_name, self.x_err_col_name, self.y_err_col_name)

    def add_column(self, col_name):
        if col_name not in self.df.columns:
            self.df[col_name] = np.nan
            self.invalidate_visible_df_cache()

    def remove_column(self, col_name):
        if col_name in self.df.columns:
            self.df = self.df.drop(columns=[col_name])

    def rename_column(self, old_name, new_name):
        """列名を変える。X/Y・誤差・点のラベルの列として使っていれば、そちらも新しい名前にする。"""
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
        """remove_column で消した列を末尾に戻す。"""
        if col_name not in self.df.columns:
            self.df[col_name] = column_data
            self.invalidate_visible_df_cache()


    def to_dict(self) -> dict:
        """JSON に保存できる dict にする。artist は含めない。"""
        result = {}
        for f in fields(self):
            if f.name in ('artist', 'df'):
                continue
            value = getattr(self, f.name)
            if f.name == 'masked_row_indices':
                # numpy.int64 が混ざることがある
                value = [int(v) for v in value]
            result[f.name] = value
        result['df'] = self._df_to_dict(self.df)
        return result

    @classmethod
    def from_dict(cls, data: dict) -> 'Dataset':
        """to_dict() の逆。古いファイルに無いフィールドは既定値で補う。"""
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
                # 既定値の無いフィールドが欠けていれば、後の関係ない場所で落ちる前にここで止める
                raise ValueError(
                    f"Datasetの復元に失敗しました: 必須フィールド '{f.name}' がありません。"
                    "壊れているか、対応していない形式のファイルの可能性があります。"
                )
        # 古いファイルの plot_type 'Waterfall' は、今のウォーターフォールのフラグに読み替える
        if state.get('plot_type') == 'Waterfall':
            state['plot_type'] = 'Line'
            state['waterfall_enabled'] = True

        obj.__dict__.update(state)
        return obj

    @staticmethod
    def _df_to_dict(df: pd.DataFrame) -> dict:
        """dtype を保ったまま JSON にできる dict にする。

        datetime64 は ISO 8601 の文字列(NaT は None)。float の NaN は json が NaN のまま往復する。
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
        """_df_to_dict() の逆。"""
        columns = d.get('columns', [])
        index = d.get('index', [])
        data = d.get('data', {})
        dtypes = d.get('dtypes', {})
        index_dtype = d.get('index_dtype')

        df = pd.DataFrame(index=index)
        if index_dtype:
            # 0 行だと index=[] の dtype が object になって元と食い違う
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
                        pass
            df[col] = series
        if columns:
            df = df[columns]
        return df

    def __getstate__(self):
        """artist は描くたびに作り直す Figure への参照なので保存しない。"""
        state = self.__dict__.copy()
        state['artist'] = None
        for cache_key in ('_visible_df_cache', '_visible_df_cache_version', '_version',
                          '_z_grid_cache', '_z_grid_cache_key'):
            state.pop(cache_key, None)
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        # 古い .pkl に無いフィールドは既定値で補う
        for f in fields(self):
            if f.name not in self.__dict__:
                if f.default is not MISSING:
                    self.__dict__[f.name] = f.default
                elif f.default_factory is not MISSING:
                    self.__dict__[f.name] = f.default_factory()
        # from_dict と同じ読み替え
        if self.__dict__.get('plot_type') == 'Waterfall':
            self.__dict__['plot_type'] = 'Line'
            self.__dict__['waterfall_enabled'] = True