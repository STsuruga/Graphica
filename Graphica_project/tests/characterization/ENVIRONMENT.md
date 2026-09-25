# 特性テストの基準を取った環境

`tests/characterization/golden/` の基準はこの環境で作った。軸の状態・保存内容・メッセージなどの JSON は
どの OS でも比べるが、**画素のハッシュはこの表と同じ OS と版のときだけ比べる**(それ以外では飛ばす)。
版を上げるときは、フルスイートと特性テストを通したうえで、`fix:` ではなく専用のコミットで
`scripts/update_characterization.py` を回し、この表も同じコミットで書き換える。

## 版

| 項目 | 版 |
|---|---|
| OS | Windows 11 Home 10.0.26200(`platform.platform()` = `Windows-11-10.0.26200-SP0`) |
| Python | 3.13.5(64 bit、MSC v.1943) |
| PySide6 / Qt | 6.9.1 / 6.9.1 |
| matplotlib | 3.10.7(FreeType 2.6.1) |
| numpy | 2.3.1 |
| pandas | 2.3.1 |
| scipy | 1.16.0 |
| openpyxl | 3.1.5 |
| xlrd | 2.0.2 |
| Pillow | 11.2.1 |
| pytest | 9.1.1 |

PySide6・matplotlib・numpy・pandas・scipy・openpyxl・xlrd は `requirements.txt` の固定版と同じ。

## 描画に効くそのほかの条件

- Qt は `QT_QPA_PLATFORM=offscreen`(`tests/conftest.py`)。画面は 800×800、論理 DPI 96、devicePixelRatio 1.0、
  スタイル `fusion`、既定の UI フォント `Sans Serif` 9pt。
- グラフの日本語は Windows の `Yu Gothic`(`C:\Windows\Fonts\YuGothR.ttc`)で描かれる。
  フォントが違う環境では画素が一致しない。
- ロケールは `Japanese_Japan.932`。

## 基準を取ったコミット

R-0.8 で記入する。
