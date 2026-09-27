# テストカバレッジ

計測日: 2026-09-28  
対象: `graphica`(設定は `pyproject.toml` の `[tool.coverage.*]`)

このファイルは `bash scripts/run_coverage.sh` が自動生成する。手で編集しても次回の実行で上書きされる。

**最新のレポート(ソースの行ごとの色付き表示): https://stsuruga.github.io/Graphica/coverage/**  
CI が master への push ごとに更新する。このファイルの数字はリリース前に手元で計測してコミットしたもの。

## 全体

| 指標 | 値 |
|---|---|
| 行カバレッジ | **95.3%** (16,093 / 16,676 行) |
| 分岐カバレッジ | 90.3% (3,716 / 4,114) |
| 対象ファイル数 | 134 |

## パッケージ別

| パッケージ | ファイル | 行カバレッジ |
|---|---:|---:|
| `graphica` | 2 | 27.0% |
| `graphica/assets` | 1 | 0.0% |
| `graphica/assets/icons` | 1 | 0.0% |
| `graphica/core` | 32 | 97.4% |
| `graphica/gui` | 37 | 96.3% |
| `graphica/gui/builders` | 6 | 99.3% |
| `graphica/gui/datasets` | 12 | 97.7% |
| `graphica/gui/datasets/operations` | 6 | 96.3% |
| `graphica/gui/dialogs` | 7 | 97.6% |
| `graphica/gui/mixins` | 6 | 95.4% |
| `graphica/gui/panels` | 3 | 92.4% |
| `graphica/gui/rendering` | 6 | 98.7% |
| `graphica/gui/tools` | 9 | 94.2% |
| `graphica/models` | 2 | 99.1% |
| `graphica/plugin` | 2 | 95.8% |
| `graphica/plugins/example_plugin` | 1 | 66.7% |
| `graphica/sample_data` | 1 | 0.0% |

## カバーが薄いモジュール(行カバレッジ 60% 未満、20行以上のもの)

| モジュール | 行カバレッジ | 行数 |
|---|---:|---:|
| `graphica\__main__.py` | 22.7% | 63 |

## 数字の読み方

- **GUIのコードは行カバレッジが低く出やすい**。ダイアログのボタンハンドラのように「実際に押さないと通らない」経路が多く、ここを100%に近づけること自体は目的ではない。
- `tests/test_export_preview_panel.py` は全件パスした後の終了処理でセグフォルトする既知の問題があり、そのチャンクの計測結果は書き出されない。関係するモジュールは**実際より低く出る**。
- モジュールごとの数字と**通っていない行番号**は [`COVERAGE_DETAILS.md`](COVERAGE_DETAILS.md)。ソースと並べて色付きで見たい場合は https://stsuruga.github.io/Graphica/coverage/ (手元なら `htmlcov/index.html`)。
- **公開レポートは macOS の CI で計測している**。Windows でしか通らない分岐は未到達になるため、手元(Windows)で計測したこのファイルの数字とはわずかにずれることがある。
