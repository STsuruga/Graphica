"""Excel の読み込みの補助。

pandas は数式セルの計算済みの値を読むので、Excel 以外で書いたファイルや手動計算のまま保存したファイルでは
値が無く空になる。欠損に見えて気づきにくいので、読む前に見つけて知らせる。
"""
import logging

import openpyxl

logger = logging.getLogger(__name__)


def find_unevaluated_formula_cells(file_path: str, sheet_name: str | None = None, max_examples: int = 5,
                                  max_scan_cells: int = 200_000) -> tuple[bool, list[str], bool]:
    """数式なのに計算済みの値を持たないセルを探す。(見つかったか, 例のリスト, 全部を見たか)。

    大きなファイルで重くならないよう max_scan_cells で打ち切る。
    """
    # .xls は openpyxl で開けず、xlrd は計算済みの値しか持たないので確かめようがない
    if not str(file_path).lower().endswith('.xlsx'):
        return False, [], True

    wb_formulas = None
    wb_values = None
    try:
        # 検査に失敗したら「見つからなかった」扱いにする約束なので、開くところから try に入れる
        wb_formulas = openpyxl.load_workbook(file_path, data_only=False, read_only=True)
        wb_values = openpyxl.load_workbook(file_path, data_only=True, read_only=True)

        sheets = [sheet_name] if sheet_name else wb_formulas.sheetnames
        examples = []
        scanned = 0

        for sname in sheets:
            if sname not in wb_formulas.sheetnames or sname not in wb_values.sheetnames:
                continue
            ws_formulas = wb_formulas[sname]
            ws_values = wb_values[sname]

            for row_f, row_v in zip(ws_formulas.iter_rows(), ws_values.iter_rows()):
                for cell_f, cell_v in zip(row_f, row_v):
                    scanned += 1
                    if cell_f.data_type == 'f' and cell_v.value is None:
                        examples.append(f"{sname}!{cell_f.coordinate}")
                        if len(examples) >= max_examples:
                            return True, examples, (scanned < max_scan_cells)
                    if scanned >= max_scan_cells:
                        return bool(examples), examples, False

        return bool(examples), examples, True
    except Exception:
        logger.exception("数式セルの検査中にエラーが発生しました: %s", file_path)
        return False, [], True
    finally:
        if wb_formulas is not None:
            wb_formulas.close()
        if wb_values is not None:
            wb_values.close()
