# Graphica への貢献

Graphica に関心を持っていただきありがとうございます。不具合の報告、機能の要望、
ドキュメントの修正、コードの改善、どれも歓迎します。

## 不具合の報告・機能の要望

[Issues](https://github.com/STsuruga/Graphica/issues/new/choose) からテンプレートを選んで送ってください。

- **不具合**: バージョン、OS、再現手順を書き、**ヘルプ ▸ 診断情報をエクスポート...** で作った zip を
  添付してもらえると原因をすばやく特定できます(添付前に中身を確認してください。PC 内のフォルダ名が含まれます)。
- **要望**: 実現方法よりも「どんな作業で何に困っているか」を教えてもらえると助かります。
- 使い方の質問は、まず [Wiki](https://github.com/STsuruga/Graphica/wiki) を確認してください。

## 開発環境

Python 3.10 以降が必要です。作業ディレクトリは `Graphica_project/` です。

```
git clone https://github.com/STsuruga/Graphica.git
cd Graphica/Graphica_project
pip install -r requirements.txt
python main.py
```

## テスト

```
pytest tests/test_dataset.py                 # 1ファイル
pytest tests/test_dataset.py -k waterfall    # 絞り込み
bash scripts/run_tests_chunked.sh            # フルスイート(約20分)
```

- **フルスイートを `pytest` 一発で実行しないでください。** GUI テストが1プロセスにリソースを溜め込んで
  進むほど遅くなるため、`scripts/run_tests_chunked.sh` がファイル単位にプロセスを分けて実行します。
- `tests/test_export_preview_panel.py` は全件成功した後の終了処理でクラッシュする既知の問題があり、
  ランナーは `!!! WARN` と表示します。これだけなら成功です。
- テストは画面を表示せずに(offscreen)動きます。**実際のモーダルダイアログを開くテストは、
  そこで止まって戻ってきません。** ダイアログを出す処理は `monkeypatch` で置き換えてください。
- 変更が `core/`、`gui/theme.py`、プロジェクトの保存形式など、多くの箇所から使われる仕組みに
  触れる場合は、フルスイートを実行してから Pull Request を送ってください。
- カバレッジは `bash scripts/run_coverage.sh` で計測できます。master の最新結果は
  [カバレッジレポート](https://stsuruga.github.io/Graphica/coverage/) で見られます。

## コードを変更するときに知っておくとよいこと

設計の要点と、過去に実際に不具合の原因になった落とし穴は、リポジトリ直下の
[`CLAUDE.md`](CLAUDE.md) にまとめています(AI エージェント向けに書き始めたものですが、
人が読んでもそのまま使えます)。特に次の点は壊しやすいので、該当箇所を触る前に読んでください。

- `ui_main_window.py` は Qt Designer の生成物なので手で編集しない
- データセットのプロパティパネルには、行を末尾に追加する(`_prop_form(...).addRow`)
- マウスモードの排他制御は `gui/mixins/mouse_mode_mixin.py` の一覧に1行足す
- `Dataset` / `ProjectModel` に項目を足すときは、既存のプロジェクトの見た目が変わらない既定値にする
- リソースの読み込みは `resource_path()` を通す(カレントディレクトリに依存しない)

リンターやフォーマッターは導入していません。周りのコードの書き方に合わせてください。
開発計画や引き継ぎ用の資料は `Graphica_project/docs/dev/` にあります。

## プラグイン

新しい読み込み形式、解析、フィット関数などは、本体を変更せずにプラグインとして追加できます。
作り方は [`Graphica_project/docs/plugin_development.md`](Graphica_project/docs/plugin_development.md) を、
リポジトリの構成は [graphica-plugin-element-constants](https://github.com/STsuruga/graphica-plugin-element-constants)
を参考にしてください。プラグインは1つにつき1つの独立したリポジトリで開発します(このリポジトリの
`plugins/` にはサンプルだけを置いています)。

## Pull Request

1. `master` からブランチを作って変更します。
2. 変更に対応するテストを追加・更新します。
3. 利用者から見て変わる点があれば `CHANGELOG.md` の先頭に書きます。
4. コミットは「データモデル」「描画」「UI の配線」のような論理的な単位に分けてもらえると、
   レビューしやすくなります。
5. Pull Request のテンプレートのチェック項目を確認して送ってください。

## ライセンス

送っていただいた変更は、このリポジトリと同じ [MIT License](LICENSE) で公開されることに
同意したものとみなします。
