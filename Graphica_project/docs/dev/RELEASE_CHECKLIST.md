# リリース手順チェックリスト

Graphica を新しいバージョンとして公開するときの手順。過去のリリースで実際に
つまずいた点(CIのトリガ遅延、macOSのGatekeeper、ライセンス同梱)を手順に
織り込んである。

バージョン番号は**厳密なsemverではなく、変更の規模感で判断する**運用
(v1.2.1 は macOS 対応という新機能を含みながら patch だった)。

---

## 1. リリース前の確認

- [ ] **フルスイートが緑**。`bash scripts/run_tests_chunked.sh`(約18分)。
      `tests/test_export_preview_panel.py` の `!!! WARN`(全件パス後の終了時
      セグフォルト)だけなら緑とみなす。
- [ ] **カバレッジを更新**。`bash scripts/run_coverage.sh` → `docs/COVERAGE.md`(要約)と
      `docs/COVERAGE_DETAILS.md`(全モジュールの数字と未到達の行番号)が書き換わるので
      両方コミットする。
      (行ごとの色付き HTML は CI が master の push ごとに
      https://stsuruga.github.io/Graphica/coverage/ へ自動公開するので、手作業は不要)
- [ ] **アプリが起動する**。`python main.py` で立ち上げ、データを1つ読み込んで
      グラフが出ることを確認(テストはヘッドレスなので、実表示は別途見る)。
- [ ] **セーフモードでも起動する**。`python main.py --safe-mode`。
- [ ] **PyInstaller のビルドが通る**。`pyinstaller graphica.spec --noconfirm`
      してから `dist/Graphica/Graphica.exe` を実行する。
      ★ exe 化でしか出ない不具合が過去に複数回あった(SVGバックエンド・scipy の
      サブモジュールが `hiddenimports` から漏れて `ModuleNotFoundError`)。
      **新しいライブラリを使い始めたら `graphica.spec` の `hiddenimports` を
      見直すこと。** `tests/test_graphica_spec.py` が spec を静的に検査している。

## 2. バージョンとドキュメント

- [ ] `core/version.py` の `__version__` を更新(**ここが唯一の情報源**。
      `pyproject.toml` は `[tool.setuptools.dynamic]` でここを読む)。
- [ ] `CHANGELOG.md` の先頭に新しい節を追加。**利用者から見て何が変わったか**を
      書く(内部リファクタは「内部の変更(動作に影響はありません)」にまとめる)。
- [ ] `docs/dev/CURRENT_STATE.md` を更新。
- [ ] ロードマップ/改善ボードの項目を消化していれば、そちらの状態も更新。

## 3. 公開

- [ ] master に push し、CI(`.github/workflows/build.yml`)が緑になるのを確認。
- [ ] タグを打つ。`git tag v1.4.0 && git push origin v1.4.0`
- [ ] **タグ push 後、CIが現れるまで数分待つ**。
      ★ 過去に **webhook 配信が14分遅延**したことがある。`gh run list` に出て
      こなくても Actions 自体が止まっているとは限らない。切り分けたい場合は
      `workflow_dispatch` で手動起動してみる。ただし同じ ref への実行は
      `concurrency` 設定により互いにキャンセルされるので、**遅れて出てきた
      push トリガのランが手動起動分をキャンセルする**点に注意
      (タグ push は master とは別グループなので、両方必要なら個別に確認する)。
- [ ] CI の成果物(`Graphica-windows` / `Graphica-macos`)をダウンロードし、
      **中に `LICENSE` と `THIRD_PARTY_LICENSES.md` が入っていることを確認**。
      同梱している Qt/PySide6 が LGPL v3 なので、条文の提示は配布の条件。
- [ ] **PyPI への公開を確認**。同じタグで `.github/workflows/publish.yml` が走り、
      TestPyPI に上げる → そこから入れて起動を確かめる → 本番 PyPI に上げる、の順に進む。
      https://pypi.org/project/graphica-plot/ に新しい版が出ていること。
      タグと `__version__` が違うと最初で止まる。PyPI は同じ版を二度上げられないので、
      途中で失敗したら版を上げて打ち直す(TestPyPI だけ上がった版も再利用できない)。
- [ ] GitHub の Releases で新しいリリースを作成し、両OSの成果物を添付する。
      本文には `CHANGELOG.md` の該当節を貼る。
- [ ] リリースノートに **macOS版は未署名**であることと、初回は右クリック ▸
      「開く」で起動する必要があることを明記(README 7.1 と同じ案内)。
      配布している `.app` は Apple Silicon (arm64) 向け。

## PyPI 公開の初回準備(一度だけ、ユーザーの操作)

配布名は `graphica-plot`(`graphica` は PyPI で別人が使用中)。トークンは使わず
Trusted Publishing で公開するので、PyPI 側に「この GitHub のワークフローからの公開を許す」
登録が要る。まだ一度も上げていない名前は「Pending publisher」として先に登録できる。

- [ ] https://pypi.org と https://test.pypi.org にそれぞれアカウントを作り、2 段階認証を有効にする。
- [ ] 両方で Account settings ▸ Publishing ▸ Add a new pending publisher に次を登録する。
      PyPI Project Name `graphica-plot` / Owner `STsuruga` / Repository name `Graphica` /
      Workflow name `publish.yml` / Environment name は TestPyPI では `testpypi`、PyPI では `pypi`。
- [ ] GitHub の Settings ▸ Environments に `testpypi` と `pypi` を作る。`pypi` には
      Required reviewers に自分を入れておくと、本番に上げる前に承認を求められる(任意)。

## 4. リリース後

- [ ] ダウンロードして実際に起動できることを、可能なら Windows/macOS 両方で確認。
- [ ] `docs/dev/CURRENT_STATE.md` の「現在地」をリリース済みの状態に更新。

---

## 過去にハマった点(再発防止)

| 事象 | 原因と対処 |
|---|---|
| exe だけで `ModuleNotFoundError` | 単純な import でも PyInstaller が追えないことがある。`graphica.spec` の `hiddenimports` に明示する(SVGバックエンド、`scipy.sparse`/`integrate`/`special`/`stats` などで実際に発生) |
| CI が起動しない | GitHub の webhook 配信遅延。`workflow_dispatch` で切り分けるが、`concurrency` による相互キャンセルに注意 |
| macOS で `.app` が壊れる | `Frameworks` 配下のシンボリックリンクが `upload-artifact` で壊れる。`ditto` で固めてから単一ファイルとしてアップロードする(CI で対応済み) |
| macOS でタブが操作できない | `QMainWindow` を `QTabWidget` へ埋め込む順序。**reparent してからウィンドウフラグを変更する**(v1.3.5 で修正) |
| Narrow/Condensed 系フォントが反映されない | Windows の「Arial Narrow」は matplotlib 上では `family="Arial", stretch="condensed"`。文字列一致では解決できない(`_resolve_font_family_for_matplotlib` で対応済み) |
