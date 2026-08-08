# リリース手順チェックリスト(ドラフト、未実行)

**このファイルは「publish(公開)したい」という意向を受けて、その手順・工程を
まとめたものであり、いずれの手順もまだ実行していない。** テスト結果(フル
スイート・バグ監査)を見てユーザーが判断してから、必要な手順だけを選んで
実行する。

作成時点(2026-08-09、`feature/gui-modernization`ブランチ、H-5完了直後)の
リポジトリ状態を前提に書いている。

---

## 0. 前提: 現在のブランチ構成

```
master
  └─ feature/format-version-and-foundations  (Track1: プラグインAPI拡張 A〜G, 13コミット, masterから0 diverge)
       └─ feature/gui-modernization           (Track2: GUIモダン化 H-0〜H-5, さらに13コミット)
```

`git rev-list`で確認済み: `feature/gui-modernization`は`master`から見て
**29コミット先行・0コミット後退**(masterはこの間更新されていないので
コンフリクトの心配は無い)。`feature/format-version-and-foundations`の
コミットは全て`feature/gui-modernization`に含まれている(スタック済み)。

## 1. リリース方式の選択

以前からの合意(`CLAUDE.md`/`docs/CURRENT_STATE.md`)は「プラグインAPI拡張と
GUIモダン化は別PRにする」だった。2通りの進め方がある。

### 選択肢A: 2本のPRに分ける(当初合意通り)

1. `feature/format-version-and-foundations` → `master` のPR(Track1: A〜G)を先にマージ
2. `master`が更新された後、`feature/gui-modernization` → `master` のPR(Track2: H-0〜H-5の差分のみ)を作成・マージ
   - 1のマージ後は`feature/gui-modernization`を`master`に対して`git rebase`するか、
     単純に2番目のPRとして開けば差分は自動的にTrack2分のみになる(Track1は
     既にmasterに含まれているため)

**長所**: レビュー・切り戻しの単位が小さく保てる、当初方針と一致。
**短所**: 手順が2段階。

### 選択肢B: 1本のPRにまとめる

`feature/gui-modernization` → `master` を1本のPRにする(29コミット、
Track1+Track2まとめて)。

**長所**: 手順がシンプル。
**短所**: 当初の「別PRにする」方針から外れる。何か問題が出た時の切り戻し単位が大きい。

→ **どちらにするかはユーザー判断待ち。** 特に指定が無ければ選択肢A(当初合意通り)を推奨。

## 2. マージ前の最終確認事項

- [ ] フルテストスイート(既存+H-5)が全件グリーン(現在バックグラウンドで実行中、結果待ち)
- [ ] 今回のバグ監査で見つかった「確定バグ」の修正が完了し、そのテストも含めて再度グリーン
- [ ] `git status`が、autosaveファイル(`autosave*.graphica`)以外はクリーンであること
      (autosaveファイルは`.gitignore`対象か確認 — 未対象なら追加を検討、
      少なくとも誤ってコミットしないこと)
- [ ] `docs/roadmap.html`のTrack1・Track2該当項目が全て`true`になっている
      (Artifactとしても再publish済み)
- [ ] `docs/CURRENT_STATE.md`が最新の状態に更新されている

## 3. バージョン番号の決定

`core/version.py`の`__version__`が現在 `"1.1.0"`。Track1(プラグインAPI拡張)+
Track2(GUIモダン化、H-0〜H-5)という2つの大きな機能追加をまとめてリリース
するなら、セマンティックバージョニング的には少なくとも **マイナーバージョン
アップ(例: 1.2.0)** が妥当(後方互換な機能追加のため)。破壊的変更
(例: プロジェクトファイル形式が旧バージョンで開けなくなる等)が無いか
`models/project.py`のフォーマットバージョン処理を確認した上で決定する。

- [ ] `core/version.py`の`__version__`を更新
- [ ] ウィンドウタイトル・「このソフトについて」ダイアログ等、`__version__`を
      参照している箇所が正しく反映されるか(通常は自動、`core/version.py`
      一元管理のため個別修正は不要なはず)

## 4. 変更履歴(CHANGELOG)

現状リポジトリに`CHANGELOG.md`は存在しない。作るかどうかも判断事項。
作る場合、Track1・Track2の各Phase完了ログ(`docs/PLUGIN_API_PROGRESS.md`・
`docs/GUI_MODERNIZATION_PROGRESS.md`)とロードマップ(`docs/roadmap.html`)の
`true`項目一覧が原材料になる。

- [ ] (任意)`CHANGELOG.md`を新規作成し、今回のリリースで完了した項目を
      ユーザー向けの言葉でまとめる(内部の実装メモそのままではなく、
      「何ができるようになったか」視点で書き直す)

## 5. README.md の確認

リポジトリルートの`README.md`(ユーザー向けマニュアル、日本語)が、
今回追加された機能(プラグイン管理UI、GUIモダン化後の見た目、新規追加の
ズームリセットボタン等)と矛盾していないか確認。スクリーンショットが
含まれている場合、モダン化後の見た目に更新が必要かも確認。

- [ ] README.mdの内容が現状と齟齬ないか確認(スクリーンショット含む)

## 6. exe ビルド(PyInstaller、配布する場合)

`graphica.spec`が現行レイアウト用の唯一のspecファイル(リポジトリルートの
`Graphica_ver1.spec`/`main_ver6.spec`は旧レイアウト用で無関係、現在
未コミットのまま削除保留状態になっている点に注意)。

```bash
cd Graphica_project
pip install -r requirements.txt
pyinstaller graphica.spec
# 生成物: dist/Graphica/Graphica.exe (onedir形式)
```

- [ ] クリーンな環境(できれば新規venv)でビルドし、`dist/Graphica/Graphica.exe`が
      正常起動することを確認
- [ ] ビルド後の実機動作確認: 新規プロジェクト作成、データ読み込み、
      グラフ描画、ダークモード切替、エクスポート、プラグイン管理UIの表示
- [ ] **既知の制約**: `graphica.spec`の`datas`に`plugins/`が含まれていないため、
      `plugins/example_plugin/`はビルド後のexeに同梱されない
      (`CLAUDE.md`に既知の課題として明記済み、Track1の別項目で対応予定)。
      今回のリリースでプラグイン機能を「使える状態」として案内するなら、
      この制約をリリースノートに明記するか、対応してから出すかを判断する必要がある
- [ ] ビルドしたexeを配布する場合、Windows Defender/SmartScreenの警告が
      出る可能性がある(コード署名なし)。署名するかどうかも判断事項

## 7. Git タグ

リリースを打つ場合、`master`マージ後に注釈付きタグを作成するのが一般的。

```bash
git tag -a v1.2.0 -m "Graphica v1.2.0: プラグインAPI拡張 + GUIモダン化"
git push origin v1.2.0
```

- [ ] タグ名・タグメッセージの内容を確認してから作成

## 8. GitHub Release(任意)

`gh release create`でGitHub Release化する場合、ビルド済みexe(zip化推奨)を
添付できる。

```bash
gh release create v1.2.0 --title "v1.2.0" --notes-file <CHANGELOGから抜粋>
```

- [ ] Release化するかどうか、exeを添付するかどうかを判断

## 9. 後片付け

- [ ] マージ後、不要になった作業用ブランチ(`worktree-agent-*`、今回のセッション中に
      Agentのworktree機能で作られたまま残っているものが複数ある)を整理するか判断
      (`git branch -a`で確認可能。実体のworktreeが既に無いものも含まれる可能性があるため、
      削除前に`git worktree list`で実体の有無を確認すること)
- [ ] 作業ディレクトリに残っている`autosave*.graphica`(実際のクラッシュ由来の
      可能性があるファイル)をユーザー自身が中身を確認の上、要否を判断

---

## 実行しないことの確認

上記のうち、**このドラフト作成時点でこちらから実行したものは一つも無い**。
PR作成・マージ・バージョン更新・タグ付け・ビルド・Release公開は、すべて
ユーザーがテスト結果とバグ監査結果を確認した上で、必要な項目を指示してから
着手する。
