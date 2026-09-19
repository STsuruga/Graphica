"""派生データセットの由来(Dataset.provenance)。core/methods_text.py がここから「方法」文を作る。"""
from datetime import datetime, timezone


def build_provenance(operation, params, source_datasets):
    """
    Args:
        operation (str): 操作の名前(methods_text の説明の引き当てに使う)。
        params (dict): 操作の設定。pickle と JSON の両方で往復できるよう素の Python 型だけにする。
        source_datasets (list[Dataset]): 元になったデータセット(複数なら合成)。
    """
    return {
        'operation': operation,
        'params': params,
        'source_dataset_ids': [ds.dataset_id for ds in source_datasets],
        'source_dataset_names': [ds.name for ds in source_datasets],
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
