# 同梱している第三者ソフトウェアとそのライセンス

Graphica 本体のライセンスは **MIT**(`LICENSE` 参照)ですが、配布している
Windows 実行ファイル(`Graphica.exe`)と macOS アプリケーション(`Graphica.app`)には、
PyInstaller によって下記のライブラリが**同梱**されています。再配布する場合は、
それぞれのライセンス条件も併せて満たす必要があります。

このファイルは、ソースから実行する場合(`pip install -r requirements.txt`)にも
そのまま当てはまります。

## 実行に必要なライブラリ

| ライブラリ | バージョン | ライセンス | 配布元 |
|---|---|---|---|
| PySide6 (Qt for Python) | 6.9.1 | **LGPL v3** | https://www.qt.io/qt-for-python |
| Matplotlib | 3.10.7 | Matplotlib License (PSF ベース、BSD互換) | https://matplotlib.org/stable/users/project/license.html |
| NumPy | 2.3.1 | BSD 3-Clause | https://numpy.org/doc/stable/license.html |
| pandas | 2.3.1 | BSD 3-Clause | https://github.com/pandas-dev/pandas/blob/main/LICENSE |
| SciPy | 1.16.0 | BSD 3-Clause | https://github.com/scipy/scipy/blob/main/LICENSE.txt |
| openpyxl | 3.1.5 | MIT | https://foss.heptapod.net/openpyxl/openpyxl |
| xlrd | 2.0.2 | BSD | https://github.com/python-excel/xlrd |

## ビルド・テストにのみ使うもの(配布物には含まれない)

| ツール | バージョン | ライセンス |
|---|---|---|
| PyInstaller | 6.16.0 | GPL v2 with a special exception(**生成した実行ファイルには伝播しない**) |
| pytest | 9.1.1 | MIT |
| coverage.py | 7.x | Apache-2.0 |

PyInstaller の例外条項により、PyInstaller で固めた実行ファイルそのものは
PyInstaller のライセンスに縛られません。

## バンドルしている素材

| 素材 | ライセンス | 出典 |
|---|---|---|
| Tabler Icons(`Graphica_project/graphica/assets/icons/*.svg`) | MIT | https://tabler.io/icons |

アイコンは SVG のまま同梱し、実行時に色を差し替えて `QIcon` として描画しています
(`Graphica_project/graphica/gui/icon_utils.py`)。

Tabler Icons のライセンス(https://github.com/tabler/tabler-icons/blob/main/LICENSE):

```
MIT License

Copyright (c) 2020-2026 Paweł Kuna

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## ★ Qt / PySide6 の LGPL v3 について

同梱ビルドを配布するうえで、実務上いちばん注意が要るのはここです。

- Graphica は PySide6 を **改変せずに動的リンクして利用**しています。この使い方の
  範囲では、**Graphica 自身のコードを MIT のままにしておくことができます**。
- 一方で LGPL は、受け取った人が **Qt 部分を自分のビルドしたものに差し替えられる**
  ことを求めます。Graphica はソースコード一式を
  https://github.com/STsuruga/Graphica で公開しており、利用者は任意のバージョンの
  PySide6 を入れて自分でビルドし直せます(`README.md` の環境構築手順どおり)。
- 配布物には本ファイルと `LICENSE` を同梱し、Qt が LGPL v3 であること、
  その入手先を示しています。LGPL v3 の条文そのものは
  https://www.gnu.org/licenses/lgpl-3.0.html を参照してください。

**注意**: 上記はライセンス条文の一般的な整理であって、法的助言ではありません。
商用配布や、Qt を改変しての配布を行う場合は、条文および必要に応じて専門家の
確認を取ってください。

## ライセンス表記の場所

- アプリ内: ヘルプ ▸ 「Graphica について...」に同じ一覧を表示しています
  (`Graphica_project/graphica/gui/dialogs/app.py` の `AboutDialog`)。
- 配布物: リリースの zip に `LICENSE` と本ファイルを同梱しています。
