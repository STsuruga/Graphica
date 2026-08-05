# プラグインAPI拡張 進捗管理

`Graphica_MASTER_SCHEDULE.md` のトラック0(着手前提条件)〜トラック4の進捗を記録する。
新しいセッションで作業を始める前に、このファイルで「どこまで完了しているか」を確認してから着手すること。

## トラック0: 着手前提条件(必須・最優先)

`Graphica_ROADMAP_PLUGIN_AND_GUI.md` フェーズA〜Gの着手前に、以下4項目が全てマージ済みであることが条件。

| ID | 項目 | 状態 | 完了日 | 備考 |
|---|---|---|---|---|
| C-001 | `.graphica` に `format_version` + migrationチェーンの追加 | ✅ 完了 | 2026-08-05 | `models/project.py`: `CURRENT_FORMAT_VERSION`定数 + `_migrate_project_data()`による移行チェーン。未バージョンファイルはversion 0として扱い、より新しいバージョンのファイルは明示的にエラー拒否する設計 |
| C-008 | 安全な数式評価器(`eval`/`exec`の排除) | ✅ 完了 | 2026-08-05 | `core/safe_eval.py`を新設し、AST制限評価器(eval/exec不使用)に統一。`core/analysis.py`(カーブフィットのカスタム数式)・`gui/data_editor.py`・`gui/mixins/dataset_mixin.py`(列計算、旧`pandas.eval(engine='python')`)の3箇所で使用していた`eval()`/`df.eval()`を全て置き換え。属性アクセスはカーブフィット用途では一切禁止、列計算用途のみ許可リスト化した`pandas.Series`/`Rolling`メソッド(`mean`/`rolling`/`cumsum`等)に限定。比較・論理演算子(`>`, `==`, `and`/`or`/`not`)もCalcHelpDialogの案内文言に合わせて要素ごとの`&`/`\|`/`~`として対応 |
| C-009 | `logging`基盤 + 出力先の統一 | ✅ 完了 | 2026-08-05 | `core/app_paths.py`を新設し`get_app_data_dir()`で`%LOCALAPPDATA%\Graphica`を解決(cwd非依存)。`main.py`の`_setup_logging()`と`gui/crash_handler.py`のログパス解決を、従来の`os.path.abspath(".")`(カレントディレクトリ依存、Program Files配下だと書込失敗しうる)から差し替え |
| C-1205 | 後方互換コーパス + シリアライズのラウンドトリップ検証 | ✅ 完了 | 2026-08-05 | `tests/fixtures/legacy_projects/`に静的な後方互換コーパス(v0の`.graphica`未指定ファイル、Dataset任意フィールド欠落、フォルダ機能追加前の`.pkl`、現実的な複数データセットプロジェクト)を追加。`_generate_corpus.py`で生成方法を文書化。`tests/test_backward_compat_corpus.py`で読込・デフォルト補完・再保存後の安定した固定点への到達(ラウンドトリップ安定性)を検証 |

**トラック0完了条件**: 上記4項目全てが✅になること。**達成(2026-08-05)**。トラック1(プラグインAPI拡張)への着手条件を満たした。

## トラック0': クイックウィン(トラック0と並行、いつでも着手可)

| ID | 項目 | 状態 |
|---|---|---|
| C-801 | PDFフォント埋め込み | ⬜ 未着手 |
| C-301/302 | Savitzky-Golay平滑化 + 微分スペクトル | ⬜ 未着手 |
| C-402 | 重み付きフィット | ⬜ 未着手 |
| C-404 | フィット範囲の指定 | ⬜ 未着手 |
| C-502 | 誤差バンド | ⬜ 未着手 |
| C-805 | カラーマップ自動配色 | ⬜ 未着手 |
| C-901 / C-007 | Undo履歴パネル + QUndoGroup | ⬜ 未着手 |
| C-1201 | 診断情報バンドル出力 | ⬜ 未着手 |
| C-712 | パネルラベル自動採番 | ⬜ 未着手 |

## トラック1〜4

未着手(トラック0完了が前提)。詳細は `Graphica_MASTER_SCHEDULE.md` / `Graphica_ROADMAP_PLUGIN_AND_GUI.md` を参照。

---

## 更新履歴

- 2026-08-05: 新規作成。C-001完了を反映。
- 2026-08-05: C-008・C-009・C-1205完了を反映。トラック0(必須4項目)が全て完了。
