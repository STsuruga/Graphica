# core/methods_text.py
"""
provenance(処理履歴、項目C-1101)から人間可読な説明を組み立てる共通ロジック。
gui/provenance_panel.py(ツリー表示のノードラベル)と generate_methods_text()
(項目C-1102、「方法」文の自動生成)の両方から使う、operation文字列→日本語の
説明文への変換をここに一本化する(表記のズレを防ぐため)。
"""


def describe_operation(provenance):
    """
    provenance dict(Dataset.provenance、項目C-1101)から、1つの処理ステップを
    要約した日本語の文字列を組み立てる。ツリー表示のノードラベル・方法文の
    1文単位のどちらにも使える粒度にしてある。
    """
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
        return f"データセット間演算({params.get('operation_symbol')})"
    if operation == 'mean_sd':
        return f"複数データセットの平均±SD生成({params.get('n_source')}件、手法: {params.get('method')})"
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
    """
    データセットのprovenanceチェーンを祖先から順にたどり、処理の流れを
    説明する日本語の「方法」文を1つの文字列として組み立てる(項目C-1102)。
    元データ(provenanceを持たないデータセット)にたどり着くか、親が既に
    削除されている(project.datasetsに見つからない)場合はそこで打ち切る。
    循環参照(理論上発生しないはずだが、壊れた/手編集されたプロジェクト
    ファイルへの安全策として)は visited セットで検知し打ち切る。
    """
    chain = []
    visited = set()
    current = dataset
    while current is not None and current.provenance and current.dataset_id not in visited:
        visited.add(current.dataset_id)
        chain.append(current.provenance)
        source_ids = current.provenance.get('source_dataset_ids') or []
        if len(source_ids) != 1:
            # 複数の親(データセット間演算等)を持つ場合、単一の直線的な
            # 文章では表現しきれないため、そこで祖先探索を打ち切り
            # (自分自身のoperationは既にchainに含めてある)、この後
            # 別途「親データセット名」を列挙する形で文章に反映する。
            break
        source_id = source_ids[0]
        current = next((ds for ds in project.datasets if ds.dataset_id == source_id), None)

    if not chain:
        return f"「{dataset.name}」は処理履歴を持たない元データです。"

    chain.reverse()  # 祖先(最も古い操作)から順に並べる
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
