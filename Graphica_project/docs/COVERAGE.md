# テストカバレッジ

計測日: 2026-10-13  
対象: `graphica`(設定は `pyproject.toml` の `[tool.coverage.*]`)

このファイルは `bash scripts/run_coverage.sh` が自動生成する。手で編集しても次回の実行で上書きされる。

**最新のレポート(ソースの行ごとの色付き表示): https://stsuruga.github.io/Graphica/coverage/**  
CI が master への push ごとに更新する。このファイルの数字はリリース前に手元で計測してコミットしたもの。

## 全体

| 指標 | 値 |
|---|---|
| 行カバレッジ | **95.1%** (20,118 / 20,879 行) |
| 分岐カバレッジ | 89.8% (4,598 / 5,120) |
| 対象ファイル数 | 164 |

## パッケージ別

| パッケージ | ファイル | 行カバレッジ |
|---|---:|---:|
| `graphica` | 2 | 31.9% |
| `graphica/assets` | 1 | 0.0% |
| `graphica/assets/icons` | 1 | 0.0% |
| `graphica/core` | 34 | 97.3% |
| `graphica/gui` | 45 | 96.1% |
| `graphica/gui/builders` | 7 | 99.2% |
| `graphica/gui/datasets` | 12 | 97.6% |
| `graphica/gui/datasets/operations` | 6 | 96.3% |
| `graphica/gui/dialogs` | 7 | 97.7% |
| `graphica/gui/mixins` | 6 | 94.8% |
| `graphica/gui/panels` | 3 | 92.6% |
| `graphica/gui/rendering` | 6 | 98.8% |
| `graphica/gui/shell` | 11 | 97.3% |
| `graphica/gui/tools` | 11 | 92.9% |
| `graphica/gui/widgets` | 6 | 96.0% |
| `graphica/models` | 2 | 99.2% |
| `graphica/plugin` | 2 | 95.8% |
| `graphica/plugins/example_plugin` | 1 | 66.7% |
| `graphica/sample_data` | 1 | 0.0% |

## カバーが薄いモジュール(行カバレッジ 60% 未満、20行以上のもの)

| モジュール | 行カバレッジ | 行数 |
|---|---:|---:|
| `graphica\__main__.py` | 27.4% | 72 |

## 数字の読み方

- **GUIのコードは行カバレッジが低く出やすい**。ダイアログのボタンハンドラのように「実際に押さないと通らない」経路が多く、ここを100%に近づけること自体は目的ではない。
- `tests/test_export_preview_panel.py` は全件パスした後の終了処理でセグフォルトする既知の問題があり、そのチャンクの計測結果は書き出されない。関係するモジュールは**実際より低く出る**。
- モジュールごとの数字と**通っていない行番号**は [`COVERAGE_DETAILS.md`](COVERAGE_DETAILS.md)。ソースと並べて色付きで見たい場合は https://stsuruga.github.io/Graphica/coverage/ (手元なら `htmlcov/index.html`)。
- **公開レポートは macOS の CI で計測している**。Windows でしか通らない分岐は未到達になるため、手元(Windows)で計測したこのファイルの数字とはわずかにずれることがある。
