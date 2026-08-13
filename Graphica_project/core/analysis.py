# core/analysis.py
import re
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve
from scipy.interpolate import CubicSpline
from scipy.optimize import curve_fit
from scipy.signal import find_peaks, savgol_filter

from core.safe_eval import DEFAULT_FUNCTIONS, safe_eval_formula

CURVE_FIT_MAX_ITERATIONS = 5000

# --- プラグインが追加するカーブフィット関数のレジストリ ---
# {name: {"func": f(x, *params), "params": [param_name, ...], "p0": [float,...] | callable | None}}
# core/plugin_api.py の GraphicaPluginAPI.register_fit_function() 経由で登録される。
_PLUGIN_FIT_FUNCTIONS = {}

# calculate_curve_fit() の組み込みフィットタイプ判定(部分一致)で使われる文字列。
# register_fit_function() が組み込み名と衝突する名前を弾くためのチェックにも使う。
_BUILTIN_FIT_TYPE_SUBSTRINGS = (
    "カスタム数式", "線形", "2次多項式", "3次多項式", "指数関数",
    "対数", "べき乗", "ガウシアン", "シグモイド",
)


def register_fit_function(name, func, param_names, p0=None):
    """
    プラグインから、カーブフィットの選択肢に新しい関数を追加する。

    Args:
        name (str): フィットタイプ名(組み込みのフィットタイプ名や既存の
            プラグイン名と重複してはならない)。
        func (callable): f(x, *params) 形式の関数。
        param_names (list[str]): パラメータ名のリスト。
        p0 (list[float] | callable | None): 初期値、または
            (x_data, y_data) -> list[float] を返す関数。省略時は全て1.0。
    """
    if not name or not name.strip():
        raise ValueError("フィット関数名が空です。")
    if name in _BUILTIN_FIT_TYPE_SUBSTRINGS:
        raise ValueError(f"'{name}' は組み込みのフィットタイプ名と衝突します。")
    if name in _PLUGIN_FIT_FUNCTIONS:
        raise ValueError(f"フィット関数 '{name}' は既に登録されています。")
    if not param_names:
        raise ValueError("param_names が空です。")
    _PLUGIN_FIT_FUNCTIONS[name] = {"func": func, "params": list(param_names), "p0": p0}


def get_plugin_fit_type_names():
    """プラグインが登録したフィットタイプ名の一覧を返す(UIのコンボボックス表示用)"""
    return list(_PLUGIN_FIT_FUNCTIONS.keys())

# --- カスタム数式で使用可能な関数・定数 ---
# 数式の評価自体は core/safe_eval.py の AST制限評価器が行う(eval/execは不使用)。
_RESERVED_FORMULA_NAMES = set(DEFAULT_FUNCTIONS.keys()) | {'x'}


def _extract_formula_params(formula):
    """
    数式文字列 (例: "a*exp(-b*x)+c") から、xでも既知の関数名でもない
    識別子を「フィットパラメータ」として、出現順を保ったまま抽出する。
    """
    params = []
    for name in re.findall(r'[a-zA-Z_][a-zA-Z_0-9]*', formula):
        if name in _RESERVED_FORMULA_NAMES or name in params:
            continue
        params.append(name)
    if not params:
        raise ValueError("数式にフィットパラメータ(x以外の文字)が見つかりません。")
    return params


def _build_custom_fit_func(formula, param_names):
    """数式文字列から、curve_fit に渡せる関数 f(x, *params) を作る。"""
    def custom_func(x, *params):
        variables = {'x': x}
        variables.update(zip(param_names, params))
        try:
            return safe_eval_formula(formula, variables)
        except Exception as e:
            raise ValueError(f"数式の評価に失敗しました: {e}") from e
    return custom_func


def calculate_curve_fit(x_data, y_data, fit_type, custom_formula=None, sigma=None, x_range=None):
    """
    曲線フィットの計算を行い、パラメータとフィット曲線のデータを返す。

    Args:
        sigma (array-like | None): 各点の重み付けに使う誤差(項目C-402)。
            scipy.optimize.curve_fitにabsolute_sigma=Trueとともにそのまま渡す
            (値が大きい=不確かさが大きい点ほどフィットへの影響が小さくなる)。
            x_rangeで点を絞り込む場合は、絞り込み後の点数と揃うようここで
            同じマスクを適用する。
        x_range (tuple(float, float) | None): フィットに使うXの範囲(項目C-404、
            両端を含む)。指定した場合、範囲外の点はp0の初期値推定も含めて
            一切使わない(フィット後の曲線・残差もこの範囲の点のみに基づく)。

    Returns:
        dict: popt(最適化されたパラメータ配列)/pcov(共分散行列)/
            perr(パラメータ標準誤差、sqrt(diag(pcov)))/param_names/
            x_fit・y_fit(200点の滑らかな曲線)/r_squared/residuals/
            x_data_used・y_data_used(NaN除外・x_range適用後の実際の入力、
            residualsと同じ長さ)を持つ(項目C-401、呼び出し側が
            Dataset.fit_resultとして構造化保持するための土台)。
    """
    x_data = np.asarray(x_data)
    y_data = np.asarray(y_data)
    if sigma is not None:
        sigma = np.asarray(sigma)
    if x_range is not None:
        x_min, x_max = x_range
        range_mask = (x_data >= x_min) & (x_data <= x_max)
        x_data, y_data = x_data[range_mask], y_data[range_mask]
        if sigma is not None:
            sigma = sigma[range_mask]

    # ★ バグ修正: x_data/y_dataにNaN(欠損値、マスクしていない未入力セル等)が
    # 含まれると、scipy.optimize.curve_fitが素の"array must not contain infs
    # or NaNs"というValueErrorを送出し、下のRuntimeErrorハンドリング(収束
    # しなかった場合の分かりやすいメッセージ)を素通りしてしまう。さらに
    # ガウシアンフィットのp0推定(np.nanargmax)は、Y列が丸ごとNaNの場合
    # "All-NaN slice encountered"で未捕捉のままクラッシュする。
    # core/dataset.pyのnormalize/savgol/arithmetic等の他の演算系メソッドは
    # いずれも同様にNaN行を除外してから計算しており、それと挙動を揃える。
    nan_mask = np.isnan(x_data) | np.isnan(y_data)
    if sigma is not None:
        nan_mask |= np.isnan(sigma)
    if nan_mask.any():
        x_data, y_data = x_data[~nan_mask], y_data[~nan_mask]
        if sigma is not None:
            sigma = sigma[~nan_mask]

    if len(x_data) == 0:
        raise ValueError("有効なデータ点がありません(すべて欠損値です)。フィッティングできません。")

    def linear_func(x, a, b):
        return a * x + b

    def poly2_func(x, a, b, c):
        return a * x**2 + b * x + c

    def poly3_func(x, a, b, c, d):
        return a * x**3 + b * x**2 + c * x + d

    def exp_func(x, a, b):
        return a * np.exp(b * x)

    def log_func(x, a, b):
        return a * np.log(x) + b

    def power_func(x, a, b):
        return a * np.power(x, b)

    def gaussian_func(x, a, b, c, d):
        return a * np.exp(-((x - b) ** 2) / (2 * c ** 2)) + d

    def sigmoid_func(x, a, b, c):
        return a / (1 + np.exp(-b * (x - c)))

    if "カスタム数式" in fit_type:
        if not custom_formula or not custom_formula.strip():
            raise ValueError("カスタム数式が入力されていません。")
        params_info = _extract_formula_params(custom_formula)
        fit_func = _build_custom_fit_func(custom_formula, params_info)
        # *params 形式の関数はscipyがパラメータ数を自動推定できないため、明示的に指定する
        p0 = [1.0] * len(params_info)
    elif "線形" in fit_type:
        fit_func, params_info = linear_func, ['a', 'b']
        p0 = [1.0, 0.0]
    elif "2次多項式" in fit_type:
        fit_func, params_info = poly2_func, ['a', 'b', 'c']
        p0 = [1.0, 1.0, 0.0]
    elif "3次多項式" in fit_type:
        fit_func, params_info = poly3_func, ['a', 'b', 'c', 'd']
        p0 = [1.0, 1.0, 1.0, 0.0]
    elif "指数関数" in fit_type:
        fit_func, params_info = exp_func, ['a', 'b']
        # y の符号に合わせた初期振幅で収束しやすくする
        amplitude = np.nanmean(np.abs(y_data)) or 1.0
        p0 = [amplitude, 0.01]
    elif "対数" in fit_type:
        if np.any(x_data <= 0):
            raise ValueError("対数フィットは X > 0 のデータにのみ使用できます。")
        fit_func, params_info = log_func, ['a', 'b']
        p0 = [1.0, 0.0]
    elif "べき乗" in fit_type:
        if np.any(x_data <= 0):
            raise ValueError("べき乗フィットは X > 0 のデータにのみ使用できます。")
        fit_func, params_info = power_func, ['a', 'b']
        p0 = [1.0, 1.0]
    elif "ガウシアン" in fit_type:
        fit_func, params_info = gaussian_func, ['a', 'b', 'c', 'd']
        amplitude = (np.nanmax(y_data) - np.nanmin(y_data)) or 1.0
        center = x_data[np.nanargmax(y_data)] if len(x_data) else 0.0
        width = (np.nanmax(x_data) - np.nanmin(x_data)) / 4 or 1.0
        p0 = [amplitude, center, width, np.nanmin(y_data)]
    elif "シグモイド" in fit_type:
        fit_func, params_info = sigmoid_func, ['a', 'b', 'c']
        amplitude = np.nanmax(y_data) or 1.0
        p0 = [amplitude, 1.0, np.nanmean(x_data)]
    elif fit_type in _PLUGIN_FIT_FUNCTIONS:
        # プラグインが register_fit_function() で追加したフィット関数
        plugin_entry = _PLUGIN_FIT_FUNCTIONS[fit_type]
        fit_func, params_info = plugin_entry["func"], plugin_entry["params"]
        plugin_p0 = plugin_entry["p0"]
        if callable(plugin_p0):
            p0 = list(plugin_p0(x_data, y_data))
        elif plugin_p0 is not None:
            p0 = list(plugin_p0)
        else:
            p0 = [1.0] * len(params_info)
    else:
        raise ValueError(f"不明なフィットタイプ: {fit_type}")

    if len(x_data) < len(params_info):
        raise ValueError(
            f"データ点数 ({len(x_data)}) がフィットに必要なパラメータ数 "
            f"({len(params_info)}) より少ないため、フィッティングできません。"
        )

    # 最適化の実行 (収束しないケースに備え、初期値と最大反復回数を指定)
    try:
        popt, pcov = curve_fit(
            fit_func, x_data, y_data, p0=p0, maxfev=CURVE_FIT_MAX_ITERATIONS,
            sigma=sigma, absolute_sigma=sigma is not None,
        )
    except RuntimeError as e:
        raise RuntimeError(
            f"フィッティングが収束しませんでした（{fit_type}）。データの分布が"
            f"このモデルに適していない可能性があります。詳細: {e}"
        ) from e

    # パラメータの標準誤差(項目C-401、後続のC-403初期値表示・C-405信頼帯の土台)。
    # pcovの対角成分が負/infになる退化したフィット(パラメータ数=データ点数等)でも
    # 例外にはせず、そのままnp.sqrtに通す(infはinfのまま、負値はnanになる。
    # どちらも「不確かさ不明」として呼び出し側が表示で弾ける値)。
    perr = np.sqrt(np.diag(pcov))

    # 滑らかなフィット曲線用データ (200点) を生成
    x_fit = np.linspace(x_data.min(), x_data.max(), 200)
    y_fit = fit_func(x_fit, *popt)

    # 当てはまりの良し悪しを判断するための決定係数(R²)と残差
    residuals = y_data - fit_func(x_data, *popt)
    ss_res = np.sum(residuals ** 2)
    ss_tot = np.sum((y_data - np.mean(y_data)) ** 2)
    r_squared = 1.0 if ss_tot == 0 else 1.0 - (ss_res / ss_tot)

    return {
        'popt': popt,
        'pcov': pcov,
        'perr': perr,
        'param_names': params_info,
        'x_fit': x_fit,
        'y_fit': y_fit,
        'r_squared': r_squared,
        'residuals': residuals,
        # 呼び出し側(gui/mixins/dataset_mixin.py)がresidualsと同じ長さの
        # xを組み立てられるよう、範囲/NaN除外後の実際のx_dataも返す
        # (項目C-401: フィット結果を後から再利用するための構造化保持)。
        'x_data_used': x_data,
        'y_data_used': y_data,
    }


def calculate_peaks(x_data, y_data, peak_type, settings):
    """ピーク/谷検出の計算を行い、該当するX,Y座標を返す"""
    y_data_to_find = y_data
    height = settings["height"]

    if "下に凸" in peak_type:
        # ★ バグ修正: 谷検出は find_peaks(-y_data) で行うため、しきい値も
        # 符号を反転させないと噛み合わない。GUI側(PeakSettingsDialog)の
        # ツールチップは「Y < -10 の谷のみ検出」のように谷側でも負の閾値を
        # そのまま入力する使い方を明示しているため、この反転を怠ると
        # 「-y_data >= height」という無関係な条件で判定してしまい、
        # 意図と異なる(むしろ逆の)点がヒットしていた。
        y_data_to_find = -y_data
        height = -height

    kwargs = {"height": height}

    if settings["prominence"] is not None:
        kwargs["prominence"] = settings["prominence"]

    # X軸距離をインデックス数に変換
    if len(x_data) > 1 and settings["distance_x"] > 0:
        sorted_x = np.sort(x_data)
        avg_x_diff = np.mean(np.diff(sorted_x))
        if avg_x_diff > 0:
            kwargs["distance"] = max(1, int(np.ceil(settings["distance_x"] / avg_x_diff)))
        else:
            kwargs["distance"] = 1
    else:
        kwargs["distance"] = 1

    peak_indices, _ = find_peaks(y_data_to_find, **kwargs)

    if len(peak_indices) == 0:
        return np.array([]), np.array([])

    return x_data[peak_indices], y_data[peak_indices]


def calculate_savgol(x_data, y_data, window_length, polyorder, deriv=0):
    """
    Savitzky-Golayフィルタによる平滑化(deriv=0、項目C-301)または
    微分スペクトル(deriv=1/2、項目C-302)を計算する。

    x_dataは昇順に並んでいる保証がないため先にソートし、Xの間隔が
    (概ね)等間隔であることを前提に、中央値ステップ幅をdeltaとして
    scipy.signal.savgol_filterに渡す(deriv>=1のとき、出力がdy/dx相当の
    スケールになるようにするため)。

    Returns:
        tuple (np.ndarray, np.ndarray): (ソート済みのx, フィルタ適用後のy)
    """
    if window_length % 2 == 0:
        raise ValueError("窓幅(window_length)は奇数である必要があります。")
    if polyorder >= window_length:
        raise ValueError("多項式の次数は窓幅より小さくする必要があります。")
    if window_length > len(y_data):
        raise ValueError(f"窓幅({window_length})がデータ点数({len(y_data)})を超えています。")

    order = np.argsort(x_data)
    x_sorted, y_sorted = x_data[order], y_data[order]
    diffs = np.diff(x_sorted)
    dx = float(np.median(diffs)) if len(diffs) > 0 and np.median(diffs) > 0 else 1.0

    y_result = savgol_filter(y_sorted, window_length, polyorder, deriv=deriv, delta=dx)
    return x_sorted, y_result


# ==============================================================================
# ベースライン補正(項目C-308): ALS / 多項式 / ラバーバンド / 手動点
# ==============================================================================
# 4手法とも同じ戻り値の形((ソート済みx, 推定ベースライン, 差し引き後のy)の3つ組)
# にそろえてあり、呼び出し側(gui/mixins/dataset_mixin.py)はどの手法でも同じ
# 後処理(DataFrame化してDatasetとして追加)で済む。

def _sort_xy_for_baseline(x_data, y_data):
    """
    ベースライン補正の4手法に共通する前処理。ALS/多項式/ラバーバンドは
    いずれも「Xに沿って並んだ系列」であることを前提にするアルゴリズムなので、
    calculate_savgolと同様にXの昇順に先にソートしておく。
    """
    x_data = np.asarray(x_data, dtype=float)
    y_data = np.asarray(y_data, dtype=float)
    order = np.argsort(x_data)
    return x_data[order], y_data[order]


def calculate_baseline_als(x_data, y_data, lam=1e5, p=0.01, niter=10):
    """
    Asymmetric Least Squares (ALS, Eilers & Boelens 2005) によるベースライン推定。

    2階差分による滑らかさの正則化(lam)を効かせたリッジ回帰的な当てはめと、
    「現在のベースラインより上側の点(=ピーク)の重みをpに、下側または
    同じ点の重みを(1-p)にする」非対称な重み更新をniter回繰り返すことで、
    信号のピーク部分には引っ張られず、ピークの下側だけをなぞる滑らかな
    ベースラインへ収束させる。

    Args:
        lam (float): 滑らかさの正則化パラメータ(>0)。大きいほどベースラインが
            滑らか(硬く曲がりにくく)なる。
        p (float): 非対称重み(0<p<1)。小さいほどベースラインがピークを
            避けて下側を通りやすくなる(一般的な目安は0.001〜0.1程度)。
        niter (int): 重み更新の反復回数(1以上)。

    Returns:
        tuple (np.ndarray, np.ndarray, np.ndarray):
            (Xの昇順にソートしたx, 推定ベースライン, ベースライン差し引き後のy)
    """
    if lam <= 0:
        raise ValueError("lam(平滑化パラメータ)は正の値である必要があります。")
    if not (0 < p < 1):
        raise ValueError("p(非対称重み)は0より大きく1より小さい値である必要があります。")
    if niter < 1:
        raise ValueError("反復回数(niter)は1以上である必要があります。")

    x_sorted, y_sorted = _sort_xy_for_baseline(x_data, y_data)
    n_points = len(y_sorted)
    if n_points < 3:
        raise ValueError(f"ALSベースライン補正には少なくとも3点のデータが必要です(現在{n_points}点)。")

    # 2階差分行列D(n_points x n_points-2)によるTikhonov正則化項。
    # lam * D @ D.T が「隣接する2階差分の二乗和」に対するペナルティになる。
    diff_matrix = sparse.diags([1, -2, 1], [0, -1, -2], shape=(n_points, n_points - 2))
    penalty = lam * (diff_matrix @ diff_matrix.transpose())

    weights = np.ones(n_points)
    baseline = y_sorted.copy()
    for _ in range(niter):
        weight_matrix = sparse.diags(weights, 0, shape=(n_points, n_points))
        baseline = spsolve((weight_matrix + penalty).tocsc(), weights * y_sorted)
        weights = p * (y_sorted > baseline) + (1 - p) * (y_sorted <= baseline)

    return x_sorted, baseline, y_sorted - baseline


def calculate_baseline_polynomial(x_data, y_data, degree=3, iterations=10):
    """
    反復多項式フィットによるベースライン推定
    (Lieber & Mahadevan-Jansen, 2003 の "ModPoly" 法)。

    degree次の多項式をyにフィットし、フィット曲線を上回る点(ピーク由来と
    みなす)をフィット曲線の値で置き換えてから再フィットする、という手順を
    iterations回繰り返す。反復のたびにピーク領域が徐々に切り下げられ、
    多項式がピークの下を通るベースラインへ収束していく。

    Args:
        degree (int): 多項式の次数(0以上、データ点数未満)。
        iterations (int): 反復回数(1以上)。

    Returns:
        tuple (np.ndarray, np.ndarray, np.ndarray):
            (Xの昇順にソートしたx, 推定ベースライン, ベースライン差し引き後のy)
    """
    if degree < 0:
        raise ValueError("多項式の次数は0以上である必要があります。")
    if iterations < 1:
        raise ValueError("反復回数(iterations)は1以上である必要があります。")

    x_sorted, y_sorted = _sort_xy_for_baseline(x_data, y_data)
    if degree >= len(y_sorted):
        raise ValueError(f"多項式の次数({degree})がデータ点数({len(y_sorted)})以上です。")

    work_y = y_sorted.copy()
    baseline = work_y
    for _ in range(iterations):
        coeffs = np.polyfit(x_sorted, work_y, degree)
        baseline = np.polyval(coeffs, x_sorted)
        work_y = np.minimum(work_y, baseline)

    return x_sorted, baseline, y_sorted - baseline


def calculate_baseline_rubberband(x_data, y_data):
    """
    ラバーバンド法(下側凸包)によるベースライン推定。

    データ点群の下側凸包(lower convex hull)の頂点をAndrewのmonotone chain
    アルゴリズムで求め、その頂点間を区分線形補間したものをベースラインとする。
    ちょうどグラフの下からゴムひも(rubber band)を張って持ち上げたときに
    データの下側に張り付く曲線に相当する。

    Returns:
        tuple (np.ndarray, np.ndarray, np.ndarray):
            (Xの昇順にソートしたx, 推定ベースライン, ベースライン差し引き後のy)
    """
    x_sorted, y_sorted = _sort_xy_for_baseline(x_data, y_data)
    n_points = len(x_sorted)
    if n_points < 3:
        raise ValueError(f"ラバーバンド法には少なくとも3点のデータが必要です(現在{n_points}点)。")

    # 下側凸包のみを構築する(Andrewのmonotone chainのlower部分)。
    # cross <= 0(左折でない)の間は直前の頂点が凸包の内側にあるので取り除く。
    hull_indices = []
    for i in range(n_points):
        while len(hull_indices) >= 2:
            o, a = hull_indices[-2], hull_indices[-1]
            cross = ((x_sorted[a] - x_sorted[o]) * (y_sorted[i] - y_sorted[o])
                     - (y_sorted[a] - y_sorted[o]) * (x_sorted[i] - x_sorted[o]))
            if cross <= 0:
                hull_indices.pop()
            else:
                break
        hull_indices.append(i)

    x_hull = x_sorted[hull_indices]
    y_hull = y_sorted[hull_indices]
    baseline = np.interp(x_sorted, x_hull, y_hull)

    return x_sorted, baseline, y_sorted - baseline


def calculate_baseline_manual(x_data, y_data, anchor_x, method="linear"):
    """
    手動点によるベースライン推定。

    ユーザーが指定したX座標群(anchor_x)それぞれについて、実データを線形
    補間してYを求め(=「その付近のデータ曲線上」にアンカー点を置く)、
    アンカー点どうしを線形補間(method="linear")または3次スプライン補間
    (method="spline", scipy.interpolate.CubicSpline。gui/canvas.pyの
    ds.smoothingが使っているのと同じクラス)で結んでベースライン曲線とする。

    Args:
        anchor_x (array-like): ベースラインのアンカー点のX座標。重複しない値を
            2点以上、データのX範囲内で指定する。
        method (str): "linear" または "spline"。"spline"は3点以上必要。

    Returns:
        tuple (np.ndarray, np.ndarray, np.ndarray):
            (Xの昇順にソートしたx, 推定ベースライン, ベースライン差し引き後のy)
    """
    if method not in ("linear", "spline"):
        raise ValueError(f"未知の補間方法です: {method}")

    x_sorted, y_sorted = _sort_xy_for_baseline(x_data, y_data)

    anchor_x = np.unique(np.asarray(anchor_x, dtype=float))  # 重複除去+昇順ソート
    if len(anchor_x) < 2:
        raise ValueError("アンカー点は重複しない値で2点以上指定してください。")
    if method == "spline" and len(anchor_x) < 3:
        raise ValueError("スプライン補間には3点以上のアンカー点が必要です。")

    x_min, x_max = x_sorted[0], x_sorted[-1]
    if anchor_x[0] < x_min or anchor_x[-1] > x_max:
        raise ValueError(
            f"アンカー点はデータのX範囲({x_min:.6g} 〜 {x_max:.6g})内で指定してください。"
        )

    anchor_y = np.interp(anchor_x, x_sorted, y_sorted)

    if method == "linear":
        baseline = np.interp(x_sorted, anchor_x, anchor_y)
    else:
        baseline = CubicSpline(anchor_x, anchor_y)(x_sorted)

    return x_sorted, baseline, y_sorted - baseline