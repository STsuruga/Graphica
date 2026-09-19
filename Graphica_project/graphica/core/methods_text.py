"""処理の履歴(provenance)を日本語の説明にする。履歴パネルと「方法」の文で表記を揃えるため、ここに1つにする。"""


def describe_operation(provenance):
    """1つの処理を要約した文(履歴パネルの項目にも、方法の文の1文にも使える)。"""
    if not provenance:
        return "不明な操作"
    operation = provenance.get('operation')
    params = provenance.get('params') or {}

    if operation == 'savgol':
        return (
            f"Savitzky-Golayフィルタ(window={params.get('window_length')}, "
            f"polyorder={params.get('polyorder')}, deriv={params.get('deriv')})"
        )
    if operation and operation.startswith('baseline_'):
        method = operation[len('baseline_'):]
        method_label = {
            'als': 'ALS法', 'polynomial': '多項式法',
            'rubberband': 'ラバーバンド法', 'manual': '手動点指定',
        }.get(method, method)
        return f"ベースライン補正({method_label})"
    if operation == 'normalize':
        mode = params.get('mode', '')
        if mode == '特定X値での強度基準':
            return f"規格化(X={params.get('reference_x')}での値基準)"
        return f"規格化({mode})" if mode else "規格化"
    if operation == 'resample':
        return f"共通X格子へのリサンプリング/補間(手法: {params.get('method')})"
    if operation == 'arithmetic':
        error_note = "、誤差を伝播" if params.get('error_propagated') else ""
        return f"データセット間演算({params.get('operation_symbol')}{error_note})"
    if operation == 'mean_sd':
        return f"複数データセットの平均±SD生成({params.get('n_source')}件、手法: {params.get('method')})"
    if operation == 'cumulative_integral':
        method_label = {'trapezoid': '台形則', 'simpson': 'Simpson則'}.get(
            params.get('method'), params.get('method')
        )
        return f"累積積分({method_label})"
    if operation == 'average_duplicate_x':
        return (
            f"重複X値の平均化({params.get('n_duplicate_groups')}グループ、"
            f"{params.get('n_points_in')}点 → {params.get('n_points_out')}点)"
        )
    if operation == 'xaxis_alignment':
        shift = params.get('shift')
        shift_text = f"{shift:+.4g}" if isinstance(shift, (int, float)) else "不明"
        return f"X軸アライメント(相互相関、シフト量: {shift_text})"
    if operation == 'histogram':
        density_text = "確率密度" if params.get('density') else "度数"
        return f"ヒストグラム(列: {params.get('column')}、{density_text}、ビン: {params.get('bins')})"
    if operation == 'kde':
        return f"カーネル密度推定(列: {params.get('column')}、評価点数: {params.get('n_points')})"
    if operation in ('curve_fit', 'batch_curve_fit'):
        fit_type = params.get('fit_type', '不明')
        r_squared = params.get('r_squared')
        r2_text = f", R²={r_squared:.4f}" if isinstance(r_squared, (int, float)) else ""
        return f"カーブフィット({fit_type}{r2_text})"
    if operation == 'multi_peak_fit':
        return f"多峰分離フィット({params.get('component_type', '不明')} x{params.get('n_components', '?')})"
    if operation == '2d_slice':
        start, end = params.get('start'), params.get('end')
        axis_label = {'x': 'X軸方向', 'y': 'Y軸方向', 'distance': '斜め方向'}.get(
            params.get('axis_kind'), params.get('axis_kind')
        )
        if start and end:
            return (
                f"2Dマップからの1Dスライス抽出({axis_label}、"
                f"始点=({start[0]:.4g}, {start[1]:.4g}), 終点=({end[0]:.4g}, {end[1]:.4g}))"
            )
        return f"2Dマップからの1Dスライス抽出({axis_label})"
    return operation or "不明な操作"


def generate_methods_text(dataset, project):
    """祖先から順に辿って「方法」の文にする。元データか、親が消されていればそこで止める(循環も止める)。"""
    chain = []
    visited = set()
    current = dataset
    while current is not None and current.provenance and current.dataset_id not in visited:
        visited.add(current.dataset_id)
        chain.append(current.provenance)
        source_ids = current.provenance.get('source_dataset_ids') or []
        if len(source_ids) != 1:
            # 親が複数(データセット間の演算など)なら一本の文にならないので、ここで止めて親の名前を並べる
            break
        source_id = source_ids[0]
        current = next((ds for ds in project.datasets if ds.dataset_id == source_id), None)

    if not chain:
        return f"「{dataset.name}」は処理履歴を持たない元データです。"

    chain.reverse()  # 古い処理から順に
    steps = [describe_operation(prov) for prov in chain]

    if len(steps) == 1:
        body = steps[0]
    else:
        body = "、続いて".join(steps[:-1]) + f"を行った上で、{steps[-1]}"

    root_provenance = chain[0]
    root_source_names = root_provenance.get('source_dataset_names') or []
    if len(root_source_names) > 1:
        origin_text = "、".join(f"「{name}」" for name in root_source_names) + "を元データとして"
    elif root_source_names:
        origin_text = f"元データ「{root_source_names[0]}」に対し"
    else:
        origin_text = ""

    return f"{origin_text}{body}を実施した(出力データセット: 「{dataset.name}」)。"
