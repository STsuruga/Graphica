# core/json_utils.py
"""
JSON形式でのプロジェクト保存(.graphica)のための共通ユーティリティ。

numpy のスカラ型(numpy.int64, numpy.float64 等)や ndarray は標準の
json.JSONEncoder ではそのままシリアライズできない場合があるため、
これらを素のPython型へ変換する安全網として GraphicaJSONEncoder を提供する。
プロジェクトデータ中のどこかに numpy スカラが紛れ込んでいても、この
エンコーダを使う限り個別に洗い出さなくても json.dump が失敗しないようにする。
"""
import json

import numpy as np


class GraphicaJSONEncoder(json.JSONEncoder):
    """numpy型を素のPython型に変換してからシリアライズするJSONEncoder。"""

    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)
