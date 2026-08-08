# 現在の作業状況(セッション間引き継ぎ用)

**新しいセッション(特にデスクトップアプリのクラッシュ後など、会話の続きが失われた状態)で
このプロジェクトの作業を再開する前に、まずこのファイルを読むこと。**
このファイルは常に「現在地」だけを保つよう、作業の区切りごとに上書きする運用にする
(過去の完了履歴を積み上げる場所ではない)。

- 完了履歴の詳細(いつ・何を・どう実装したか): トラック1(プラグインAPI拡張)は
  `docs/PLUGIN_API_PROGRESS.md`、トラック2(GUIモダン化)は
  `docs/GUI_MODERNIZATION_PROGRESS.md`(役割は同じ、対象トラックが異なるだけ)
- 全項目の通しナンバリング・チェックリスト: `docs/roadmap.html`
  (Artifactとしても公開: https://claude.ai/code/artifact/3305056d-6417-4056-8899-b5e2bca0c553 。
  URLが失われていてもファイル自体がリポジトリにあるので、`DATA`配列の`true`/`false`を見れば
  完了状況が分かる)

## 現在のブランチ

`feature/gui-modernization`(originにpush済み、upstream追跡設定済み。分岐元は
`feature/format-version-and-foundations`で、そちらも既にoriginにpush済み・
トラック1の全成果を含む)。ロードマップのフェーズH節が「このフェーズ単独で
新しいブランチを切ることを推奨する」と明記していたため、ユーザーに確認の上で
このブランチを新設した(トラック1とトラック2の変更を別PRに分離する狙い)。

## 直近の完了

トラック2 フェーズH-2-2(ロードマップ#41: データセットリスト・データテーブルの
磨き込み)完了。テスト追加・グリーン確認済み(`tests/test_theme.py`・
`tests/test_main_window.py`)、フルスイートはバックグラウンドで実行中
(このファイル更新時点ではまだ結果待ち。完了したら結果を確認してからコミット・
pushすること)。`docs/roadmap.html`の#41チェック更新・Artifact再publish・
`docs/gui_style_audit.md`/`docs/GUI_MODERNIZATION_PROGRESS.md`への記録は
実施済み。**コミット・pushはまだ**(このセッションの直後の作業として残っている)。

H-2-2で実施した変更(実機フィードバックによる複数回の調整を経て確定):
- `gui/theme.py`に`selection_highlight`トークンを新設(薄い青、透過あり)。
  従来の「濃いアクセント色の塗りつぶし」を置き換えた。
- 選択ハイライトの形状は、QSSの`::item:selected`だけでは実現できないことが
  判明した(Qt/FusionスタイルがCE_ItemViewItem描画時にアイコン列とテキスト列を
  別々の矩形として扱うため)。`_DatasetTreeSelectionDelegate`
  (`gui/main_window.py`)を新設し、`dataset_list_widget.setItemDelegate()`で
  登録。選択時の背景を自前のQPainterPathで1回だけ描画し、リスト自体の角丸
  (8px、`theme.DATASET_LIST_ITEM_RADIUS`)と揃えている。
- 分岐(展開矢印)用インデント列は`delegate.paint()`とは別経路
  (`QTreeView::drawBranches()`)で描画されるため、汎用の`::item:selected`
  スタイル(`accent_soft`)が滲み出る問題があり、`background: transparent`で
  このリストに限り打ち消した。デリゲートの矩形も左端をビューポート0まで
  伸ばし、インデント列分の隙間を埋めている。
- リストと検索ボックスは、それぞれの`border: none`で枠線だけを消したが、
  **統合(1つの箱にする)はしていない**(実機フィードバックで明確に区別された
  要件)。間の余白は独立を保ったまま4px→6px(約1.5倍)に拡大。
- `window.grab()`でBefore/Afterスクリーンショット(ライト/ダーク)を撮って
  確認し、`docs/gui_style_audit.md`のH-2-2節+`docs/screenshots/h2-2/`配下の
  PNGとして記録した。

H-0の調査で判明した重要な事実(H-2の残り項目でも必ず踏まえること):
- `gui/theme.py`が唯一のQt側QSS/パレット実装(別`.qss`ファイルは無い)。
- **matplotlib側(`gui/canvas.py`)とミニマップ(`gui/minimap_widget.py`)は、
  `gui/theme.py`のトークンとは完全に独立した、それぞれ個別にハードコードされた
  ダーク/ライト配色定数を持つ(値も一致していない)。統合するかは未判断のまま
  スコープ外としている**(docs/gui_style_audit.md 7節参照)。
- 「カスタムカラーパレット」機能(QSettings永続化)はデータセットの線色サイクル
  であり、UIテーマのアクセントカラーとは無関係。

## 次にやること

ユーザーから明示的に番号(例:「42実施」)で指示があるまで着手しない。
次に来る想定はトラック2 フェーズH-2-3(#42〜、H-2の残りコンポーネント磨き込み)。
H-2は8つのサブ項目(H-2-1〜H-2-8、ロードマップ#40〜47)を1つずつ順に進める
増分実装のため、複数まとめて指示された場合もコンポーネント単位で区切って
コミットすること。指示が来たらまず`docs/roadmap.html`の該当行と、
`docs/gui_style_audit.md`(H-0の調査結果+これまでのH-2 Before/After記録)、
必要なら`docs/Graphica_ROADMAP_PLUGIN_AND_GUI.md`のフェーズH節を読んでから
着手する。

**H-2-2完了直後の未実施タスク**: フルpytestスイートの結果確認 → 問題なければ
`git add`(`gui/theme.py`, `gui/main_window.py`, `tests/test_theme.py`,
`tests/test_main_window.py`, `docs/gui_style_audit.md`,
`docs/GUI_MODERNIZATION_PROGRESS.md`, `docs/roadmap.html`,
`docs/screenshots/h2-2/`, このファイル)→ コミット → push。

トラック4(プラグイン本体の開発、#163〜)もトラック1完了により並行して着手可能
(`docs/Graphica_PLUGIN_BACKLOG.md`の「着手推奨プラグイン Top 8」参照)。

## 開発の進め方(ユーザーとの合意事項・運用ルール)

- ユーザーは`docs/roadmap.html`(通しナンバリングされたチェックリスト)を見ながら
  「N-M実施」のように番号で作業範囲を指示してくる。指示された番号の項目**のみ**着手し、
  スコープ外への自主的な拡張はしない(CLAUDE.mdの「スコープ規律」節を参照)。
  Track 0の前提条件が終わっていないうちはTrack 1以降に着手しない、という
  ゲート条件もCLAUDE.mdに明記されている。
- **エージェント(Agentツール)は必要に応じて断りなく展開してよい**、
  **pytest実行とgit pushも都度確認を挟まず適宜行ってよい**、とユーザーから明示的に
  許可を得ている。これは通常のセーフティルールより緩和された、このプロジェクト固有の
  運用(セッションの開始時に口頭で合意済み。新セッションでも踏襲してよい)。
- 1項目〜1フェーズの作業がまとまるごとに、次の一連の流れを毎回徹底する:
  1. 実装 + そのテストを書く
  2. **テストの実行範囲は影響範囲に応じて判断する**(2026-08-07にユーザーと
     合意、CLAUDE.mdの「Regression bar」節にも反映済み)。
     - 影響範囲が小さい変更(1コンポーネントのQSS調整、1関数に閉じた変更等):
       変更したテストファイル + 関連する広めの`pytest -k <キーワード>`
       サブセットで十分。
     - 共有状態・グローバル状態・コア機構(`core/`配下、`gui/theme.py`、
       プラグインレジストリのシングルトン、`models/project.py`のシリアライズ等)
       に触れる変更: フルスイート必須(実際にフルスイートでしか再現しない
       不具合が過去2回あった。下記「既知の注意点」参照)。
     - 上記に関わらず、**pushする前には一定の頻度でフルスイートを挟む**
       (毎回である必要はないが、数項目ごと・フェーズの区切りごとには必ず)。
     - フルスイートを実行する場合は500件超・実行に約15〜25分かかるため
       `Bash`の`run_in_background: true`で流し、完了通知を待つ(ポーリングしない)。
  3. 失敗があれば原因を調査して修正する(テスト自体の実行順序依存など、
     実装バグでない場合もあるので切り分ける)
  4. 対象トラックの進捗ファイル(トラック1なら`docs/PLUGIN_API_PROGRESS.md`、
     トラック2なら`docs/GUI_MODERNIZATION_PROGRESS.md`)に完了項目の詳細
     (ID・状態・完了日・実装メモ)を追記
  5. 明確なコミットメッセージでコミット(関連ファイルのみ`git add`、
     autosaveファイルや無関係な変更は含めない)
  6. push
  7. `docs/roadmap.html`の該当番号を`true`に更新し、Artifactとして再publish
  8. **このファイル(`docs/CURRENT_STATE.md`)を最新の状態に上書き**
- クラッシュ耐性の生命線は「こまめにpushすること」。pushされていない変更は
  会話が失われると一緒に失われるリスクがあるので、大きな作業単位を1つにまとめず、
  区切りが来たらその都度上記フローを回す。
- 複数フェーズ/複数項目を1度に指示された場合、ファイルの重なりが少ない単位に
  分けて並行実装してよい。並行時は担当ファイルの境界を明示的に(自分にも
  Agentにも)言語化してから着手すること。土台となる項目(他の項目が依存する
  変更)は先に自分で片付けてから、独立性の高い残りを並行化するのが安全
  (フェーズFでの実例: F-1のplugin.json必須化を先に完了させてから、
  それに依存するF-2と、独立したF-3/F-4を並行に回した)。
- Agentをバックグラウンドで並行実行させる際、`isolation: "worktree"`は
  このセッションで一度信頼性問題を起こした(下記「既知の注意点」参照)。
  以降は素の(isolationオプション無しの)バックグラウンドAgentを、共有ツリーの
  ファイル境界を極めて具体的に指示した上で使う方針に切り替えており、
  F-3/F-4ではこれで問題なく完了した。

## 既知の注意点

- `docs/roadmap.html`は`<title>`+`<style>`+本体HTML+`<script>`のみを持つ
  (`<!DOCTYPE>`/`<html>`/`<head>`/`<body>`タグは書かない)。Artifactツールが
  自動でラップする前提の構造なので、編集時もこの形式を崩さないこと。
- テストスイート全体は実行順序次第でグローバル状態(例: `core/plugin_api.py`の
  `_singleton_api`)が他のテストの影響を受けることがある。新しいテストで
  プロセス全体の共有状態を前提にする場合は、`monkeypatch`で明示的に隔離すること。
  これまでに2回踏んだ実例: `tests/test_source_plugin_field.py`(フェーズC)、
  `tests/test_dialogs.py`の意図的に壊れたプラグインを読み込むテスト(フェーズF、
  「他のテストが先に`_singleton_api`をキャッシュ済みだと、そのテストの
  `load_plugins_once()`呼び出しが何もせず前のキャッシュを返してしまう」という
  同じパターン)。単体では通っても、フルスイートの中で実行順序が変わると
  落ちることがあるため、新しいプラグイン関連テストは必ずフルスイートでの
  再現(または少なくとも`-k plugin`等の広めのサブセットでの実行)まで確認すること。
- 関数のシグネチャを変更した(例: `load_plugins_once()`に`disabled_names`引数を
  追加)際は、その関数を`monkeypatch.setattr`で固定シグネチャの`lambda`に
  差し替えているテストヘルパーが無いか横断的に確認すること。フェーズFで
  `tests/test_quick_access_mixin.py`の`lambda plugins_dir: plugin_api`が
  新しいキーワード引数を受け付けずに壊れた実例がある(`lambda plugins_dir,
  disabled_names=None: plugin_api`に修正して解消)。
- **H-2の「ライト/ダーク両モードでのスクリーンショット記録」完了条件は、実際に
  Qtウィジェットを`QWidget.grab() -> QPixmap.save()`することで満たせる**
  (実機の画面表示やブラウザ系ツールは不要。デスクトップアプリなのでBrowser系
  ツールは使えないことに注意)。`run_startup_checks=False`で`PlotterApp`を作り、
  QSettingsを一時iniにリダイレクト(既存テストの`_make_isolated_plotter_app`と
  同じ手法)した上で、`window.show()`+`processEvents()`を数回回してからgrabすれば、
  実際のレンダリング結果を確認できる。ダークモードは`window.dark_mode_action.
  setChecked(True)`で切り替えてから再度grabする。スクリーンショットは
  `docs/screenshots/h2-N/`配下にPNGで保存し、`docs/gui_style_audit.md`から
  相対パスで埋め込む(実例: H-2-1、`docs/screenshots/h2-1/`)。
- **Agentツールの`isolation: "worktree"`は、このセッションで一度、割り当てられた
  worktreeが理由不明のまま消失する事象が起きた**(`git worktree list`に登録が
  無くなり、パスもENOENT。エージェント自身が削除した形跡は無い)。再現条件は
  不明。発生した場合、エージェントは自力でworktreeの再作成・再アタッチができない
  (pinned cwdのsubagentからの`EnterWorktree`は拒否される)ため、オーケストレーター
  側が「共有ツリーで直接作業してよい」と明示的に許可し、その時点のgit status
  (どのファイルが誰の担当か)を具体的に伝える形で復旧した。並行作業を頼んだ
  Agentから同様の報告(worktree消失・ENOENT)が来た場合は、同じ手順(共有ツリー
  作業の許可+ファイル境界の再提示)で対応すればよい。この間、共有ツリーには
  もう一方の担当者(自分)の未コミット変更が残っているため、`git checkout`/
  `git reset`/`git clean`等の破壊的操作は絶対に指示しないこと。フェーズF以降は
  そもそも`isolation: "worktree"`を使わず、共有ツリー+明示的なファイル境界
  指示のバックグラウンドAgentに統一しており、今のところこちらは安定している。
- **QTreeView/QTreeWidgetのQSSだけでは「アイコン列+テキスト列にまたがる単一の
  角丸選択ハイライト」を実現できない**(H-2-2で判明)。Qt(Fusionスタイル)は
  `CE_ItemViewItem`描画時にデコレーション(アイコン)列とテキスト(display)列を
  別々の矩形として扱い、`::item:selected`の`background`/`border-radius`も
  それぞれ独立に適用するため、2つの矩形の角丸がわずかにズレて隙間ができる。
  QSSの`show-decoration-selected`はPySide6のQTreeView/QTreeWidgetに対応する
  公開APIが無く、指定しても効果が無い。**解決策は`QStyledItemDelegate`を
  サブクラス化し、選択時の背景をQPainterPathで自前描画した上で、
  `option.state`から`State_Selected`を外してから基底実装(`super().paint()`)に
  委譲すること**(実装例: `gui/main_window.py`の`_DatasetTreeSelectionDelegate`)。
- **分岐(展開矢印)用インデント列は`delegate.paint()`とは別経路
  (`QTreeView::drawBranches()`)で描画される**ため、デリゲート側で
  `State_Selected`を外しても、そのフラグ解除の影響を受けない。汎用の
  `::item:selected`スタイルがモデル側の実際の選択状態を見てそのまま
  インデント列に滲み出るため、対象リストに限って`background: transparent`で
  打ち消す必要がある(単に`selection-background-color: transparent`を
  ウィジェットレベルで指定するだけでは不十分だった)。
- **QColor(rgba_css_string)はCSSのrgba()関数記法を解釈できず、不透明の黒に
  無効フォールバックする**(H-2-2で発覚。`"rgba(37, 99, 235, 0.12)"`のような
  QSS埋め込み用トークン文字列をPython側でQColorとして直接使いたい場合、
  `QColor(rgba_css_string)`は`isValid() == False`になり、代わりに不透明な
  黒(0,0,0,255)が返る)。正規表現でr,g,b,aを抽出し、`QColor(r,g,b)`+
  `setAlphaF(a)`で組み立てること(実装例:
  `gui/theme.py`の`current_selection_highlight_qcolor()`)。
- **実機フィードバックでUIの「見た目の意図」を早めに言語化してもらうと手戻りが
  減る**(H-2-2の実例): 「検索ボックスとリストの境界線を消して」という指示を
  「1つの箱に統合する」意味だと誤解して実装し、後から「統合することじゃない、
  それぞれ独立した箱のまま枠線だけ消して」と訂正された。見た目の変更指示が
  複数の解釈を許す場合(特に「境界線を消す」「くっつける」等)は、実装前に
  「独立した箱のまま枠線を消すのか、1つの箱に統合するのか」を確認するか、
  最初の実装を小さく留めて早い段階でスクリーンショットを見せるとよい。
