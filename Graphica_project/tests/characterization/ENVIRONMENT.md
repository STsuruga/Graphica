# 特性テストの基準を取った環境

`tests/characterization/golden/` の基準はこの環境で作った。**特性テストは基準を取った OS(Windows)でだけ比べ、
画素のハッシュとファイルのバイト列はさらに版まで一致するときだけ比べる。** ほかの OS では記録器のテスト(`any_os`)
以外を飛ばす。最初は保存内容や操作の結果の JSON をすべての OS で比べる予定だったが、macOS の CI で、数値の最後の
桁(libm と SIMD の違い。条件の悪いフィットではそれが 1e-5 ほどに広がる)、書き出したファイルのバイト列、
フォントで変わる図の大きさが食い違ったため、OS ごとに基準を持つのをやめた。
版を上げるときは、フルスイートと特性テストを通したうえで、`fix:` ではなく専用のコミットで
`scripts/update_characterization.py` を回し、この表も同じコミットで書き換える。

## 数値の比べ方

同じ版でも、numpy と OpenBLAS は CPU ごとに別の計算経路(SIMD の命令、BLAS の核)を選ぶので、計算結果の最後の
数ビットが機械によって変わる。GitHub の Windows ランナーは実行ごとに CPU が違い、同じコードで通ったり落ちたりした。
そこで、**基準を作った機械(`golden/MACHINE.json`)では数値をビット単位で比べ、ほかの機械では許容差で比べる。**

- 機械の識別: CPU の文字列、numpy が使える SIMD の機能、numpy と scipy の版、`OPENBLAS_CORETYPE` と
  `NPY_DISABLE_CPU_FEATURES`。
- 許容差: 相対 1e-9(`NUMERIC_REL_TOL`)。配列の要素は、その配列の最大の大きさに対する絶対差としても使う。
  範囲制約つき・頑健な損失のフィット(`fit_models/options`)は、`least_squares` が ftol=xtol=1e-8 で止まるため
  1e-6(`OPTIMIZER_REL_TOL`)。
- 浮動小数の配列は、ハッシュのほかに等間隔の 16 点・最小・最大・合計・NaN の数を記録し、別の機械ではこちらで比べる。
- 手元で `OPENBLAS_CORETYPE` を Sandybridge・Prescott・Nehalem にすると CI と同じ種類の差が出る(Haswell・Zen は
  この機械と同じ)。測った最大の差は `fit_models/options` で 1.2e-8、ほかは 1e-16 以下。
- 基準を作った機械で許容差の比較に落ちていないかは `test_recorder.py::test_this_machine_made_the_goldens` が見る
  (`CI` があれば飛ばす)。基準の機械を変えるときは `scripts/update_characterization.py` を `-k` なしで回す。

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
| CPU | AMD64 Family 23 Model 113(Zen 2、AVX2 まで。AVX-512 なし)、OpenBLAS の核は Zen(Haswell と同じ結果) |
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
