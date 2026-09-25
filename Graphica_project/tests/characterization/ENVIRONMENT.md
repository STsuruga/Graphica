# 特性テストの基準を取った環境

`tests/characterization/golden/` の基準はこの環境で作った。保存内容・操作の結果・メッセージなどの JSON は
どの OS でも比べる。**画素のハッシュはこの表と同じ OS と版のときだけ**、画面の組み立てと描画の JSON
(`pytest.mark.pinned_os`)は**同じ OS のときだけ**比べる(標準ショートカットの割り当てや、フォントの違いによる
軸の位置が OS ごとに違うため)。それ以外では飛ばす。
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

`6b33bdc`(ブランチ `refactor/r0-characterization`、2026-09-25)。観点ごとに取ったコミットは、画面の組み立て `298c57c`、
描画 `0496c5a`、保存と読み込み `ec331de`、操作 `0e90da0`、書き出し `6b33bdc`。以後の `refactor:` コミットでは
`golden/` が変わらないこと。

- 2 回続けて回して 105 件すべて一致(各約 2 分 10 秒)。各シナリオは単独で回しても一致する。
- フルスイート(特性テストを含む)は 124 チャンク・3,254 件が緑、約 19 分。前後でレジストリ(HKCU\Software\Graphica)は不変。
- メニューの文字を 1 か所変えると `test_startup_window` が落ち、差分が 1 行で出ることを確かめた。
- 基準の中には今の不具合がそのまま入っている(K-3・K-5・K-17・K-18・K-19・K-21・K-27・K-28・K-29)。直すときは `fix:` で基準を更新する。
