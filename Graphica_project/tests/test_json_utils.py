# tests/test_json_utils.py
"""core/json_utils.py の GraphicaJSONEncoder に対するテスト。"""
import json

import numpy as np
import pytest

from core.json_utils import GraphicaJSONEncoder


def test_encodes_numpy_integer_as_int():
    result = json.dumps({"v": np.int64(42)}, cls=GraphicaJSONEncoder)
    assert result == '{"v": 42}'
    assert json.loads(result)["v"] == 42


def test_encodes_numpy_floating_as_float():
    result = json.dumps({"v": np.float64(3.5)}, cls=GraphicaJSONEncoder)
    assert json.loads(result)["v"] == 3.5


def test_encodes_numpy_ndarray_as_list():
    result = json.dumps({"v": np.array([1, 2, 3])}, cls=GraphicaJSONEncoder)
    assert json.loads(result)["v"] == [1, 2, 3]


def test_encodes_nested_numpy_ndarray_of_floats():
    result = json.dumps({"v": np.array([1.5, 2.5])}, cls=GraphicaJSONEncoder)
    assert json.loads(result)["v"] == [1.5, 2.5]


def test_plain_python_types_still_work_normally():
    """numpy型を介さない通常のdictは、素のjson.dumpsと同じ結果になる。"""
    payload = {"a": 1, "b": "text", "c": [1, 2, 3], "d": None, "e": True}
    result = json.dumps(payload, cls=GraphicaJSONEncoder)
    assert json.loads(result) == payload


def test_unsupported_type_falls_through_to_default_and_raises_type_error():
    """numpy型でもJSON標準型でもないオブジェクトは、通常通りTypeErrorになる
    (superのdefault()に委譲されるパスを確認する)。"""

    class Unsupported:
        pass

    with pytest.raises(TypeError):
        json.dumps({"v": Unsupported()}, cls=GraphicaJSONEncoder)
