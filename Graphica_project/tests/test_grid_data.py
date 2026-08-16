# tests/test_grid_data.py
"""core/grid_data.py (項目C-508/C-510: 散布データ→2Dグリッド変換) に対するテスト。"""
import numpy as np
import pytest

from core.grid_data import compute_z_grid, is_regular_grid, GridDataError


def _make_regular_grid_points(xs, ys, z_func):
    """xs×ysの直積格子から、長形式の(x, y, z)配列を組み立てるテスト用ヘルパー。"""
    x, y, z = [], [], []
    for yi in ys:
        for xi in xs:
            x.append(xi)
            y.append(yi)
            z.append(z_func(xi, yi))
    return np.array(x), np.array(y), np.array(z)


# --- is_regular_grid ---

def test_is_regular_grid_true_for_full_cartesian_product():
    x, y, _ = _make_regular_grid_points([0, 1, 2], [10, 20], lambda a, b: a + b)
    assert is_regular_grid(x, y) is True


def test_is_regular_grid_false_for_missing_combination():
    x, y, _ = _make_regular_grid_points([0, 1, 2], [10, 20], lambda a, b: a + b)
    # 1組だけ欠けさせる(不完全な格子)
    x, y = x[:-1], y[:-1]
    assert is_regular_grid(x, y) is False


def test_is_regular_grid_false_for_scattered_points():
    rng = np.random.default_rng(0)
    x = rng.uniform(0, 10, size=20)
    y = rng.uniform(0, 10, size=20)
    assert is_regular_grid(x, y) is False


def test_is_regular_grid_false_for_duplicate_pair():
    x = np.array([0.0, 0.0, 1.0, 1.0, 0.0])
    y = np.array([0.0, 1.0, 0.0, 1.0, 0.0])  # (0,0)が2回
    assert is_regular_grid(x, y) is False


# --- compute_z_grid: 規則格子 ---

def test_compute_z_grid_regular_reconstructs_exact_values():
    xs, ys = [0.0, 1.0, 2.0], [10.0, 20.0]
    x, y, z = _make_regular_grid_points(xs, ys, lambda a, b: a * 10 + b)
    result = compute_z_grid(x, y, z)

    assert result['is_regular'] is True
    np.testing.assert_array_equal(result['x_grid'], xs)
    np.testing.assert_array_equal(result['y_grid'], ys)
    assert result['z_grid'].shape == (2, 3)
    # z_grid[i, j] は y_grid[i], x_grid[j] に対応する
    for i, yi in enumerate(ys):
        for j, xi in enumerate(xs):
            assert result['z_grid'][i, j] == pytest.approx(xi * 10 + yi)


def test_compute_z_grid_regular_excludes_nan_points():
    xs, ys = [0.0, 1.0], [10.0, 20.0]
    x, y, z = _make_regular_grid_points(xs, ys, lambda a, b: a + b)
    z = z.astype(float)
    z[0] = np.nan  # 1点だけ欠損させる(NaN除外後も残り3点で規則格子と判定されるべき)
    x, y, z = x[1:], y[1:], z[1:]  # NaN行そのものを除いた3点

    result = compute_z_grid(x, y, z)
    # 3点だけでは(0,10)が欠けるため完全な直積格子ではない → 補間経路に落ちる
    assert result['is_regular'] is False


# --- compute_z_grid: 散在データ(補間) ---

def test_compute_z_grid_scattered_uses_interpolation_and_fills_requested_resolution():
    rng = np.random.default_rng(1)
    x = rng.uniform(0, 10, size=50)
    y = rng.uniform(0, 10, size=50)
    z = x + y

    result = compute_z_grid(x, y, z, interp_method='linear', resolution=(20, 15))

    assert result['is_regular'] is False
    assert result['x_grid'].shape == (20,)
    assert result['y_grid'].shape == (15,)
    assert result['z_grid'].shape == (15, 20)


def test_compute_z_grid_scattered_auto_resolution_when_unspecified():
    rng = np.random.default_rng(2)
    x = rng.uniform(0, 10, size=100)
    y = rng.uniform(0, 10, size=100)
    z = np.sin(x) + np.cos(y)

    result = compute_z_grid(x, y, z)

    assert result['is_regular'] is False
    assert len(result['x_grid']) >= 10
    assert len(result['y_grid']) >= 10


def test_compute_z_grid_scattered_interpolated_values_are_reasonable():
    # 既知の平面 z = 2x + 3y を散在点から補間し、格子上の値が近似的に一致することを確認
    rng = np.random.default_rng(3)
    x = rng.uniform(0, 10, size=200)
    y = rng.uniform(0, 10, size=200)
    z = 2 * x + 3 * y

    result = compute_z_grid(x, y, z, interp_method='linear', resolution=(10, 10))
    xx, yy = np.meshgrid(result['x_grid'], result['y_grid'])
    expected = 2 * xx + 3 * yy
    # 凸包の内側(補間領域)はNaNにならないはずで、近い値になる
    valid = ~np.isnan(result['z_grid'])
    assert valid.sum() > 0
    np.testing.assert_allclose(result['z_grid'][valid], expected[valid], atol=1.0)


def test_compute_z_grid_rejects_unknown_interp_method():
    x, y, z = _make_regular_grid_points([0, 1], [0, 1], lambda a, b: a + b)
    with pytest.raises(GridDataError, match="不明な補間方法"):
        compute_z_grid(x, y, z, interp_method='not_a_method')


def test_compute_z_grid_rejects_all_nan_data():
    x = np.array([np.nan, np.nan])
    y = np.array([1.0, 2.0])
    z = np.array([1.0, 2.0])
    with pytest.raises(GridDataError, match="有効なデータ点がありません"):
        compute_z_grid(x, y, z)


def test_compute_z_grid_rejects_too_few_scattered_points():
    x = np.array([0.0, 1.0])
    y = np.array([0.0, 1.0])
    z = np.array([0.0, 1.0])
    with pytest.raises(GridDataError, match="最低3点"):
        compute_z_grid(x, y, z)


def test_compute_z_grid_rejects_invalid_resolution():
    rng = np.random.default_rng(4)
    x = rng.uniform(0, 10, size=10)
    y = rng.uniform(0, 10, size=10)
    z = x + y
    with pytest.raises(GridDataError, match="2以上"):
        compute_z_grid(x, y, z, resolution=(1, 5))
