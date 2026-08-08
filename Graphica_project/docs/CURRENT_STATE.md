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

トラック2 フェーズH-2-3(ロードマップ#42: ドック全般)・H-2-4(#43: ボタン・
入力フィールド・コンボボックス)完了。フルスイート574件グリーン確認済み。
`docs/roadmap.html`の#42/#43チェック更新・Artifact再publish・
`docs/gui_style_audit.md`/`docs/GUI_MODERNIZATION_PROGRESS.md`への記録は
実施済み。H-2-4完了後、実機フィードバックが4ラウンド続き(「追加分」
「追加分(続き)」「追加分(3回目)」「追加分(4回目)」)、いずれも対応・
テスト追加・フルスイートグリーン確認済み。**詳細はこのファイルではなく
`docs/GUI_MODERNIZATION_PROGRESS.md`の該当行(表形式)と
`docs/gui_style_audit.md`の対応する節(Before/After画像付き)を参照すること**
(このファイルは過去の完了履歴を積み上げる場所ではないため、詳細記述は
移した)。

**H-2-4追加分(4回目)もフルスイート636件グリーン確認済み**(2026-08-08)。

**教訓(4ラウンド通じて繰り返し得られた重要な知見、今後も踏まえること)**:
- QSS文字列の存在チェックだけのテストでは実際の描画色/レイアウトを検証
  できない(QDockWidgetへの`background`指定は正しかったが、その手前の層
  ―QScrollAreaの中身のwidget、あるいはpixmapサイズがsizeHintを押し広げる
  ―が実際の見た目を決めていた、という「対策した箇所より手前/奥に真因が
  あった」パターンが複数回発生した)。疑わしい箇所には`QWidget.grab()`での
  ピクセル色検証や実際のwidgetサイズ検証を伴う統合テストを追加すること。
- シグナルを`.pressed.emit()`のように手動発火するテストは「配線が正しいか」
  までしか検証できず、Qtの実際のフォーカス遷移タイミングに起因する不具合
  (今回はQPushButtonの既定フォーカスポリシーがマウス押下配送前にフォーカス
  を奪う問題)を見逃す。疑わしい箇所には`QTest.mouseClick()`による実クリック
  再現を伴うテストを追加すること。
- 「幅方向だけ対策して高さ方向を見落とす」「長い/複雑な入力でしか再現しない
  不具合が短い/単純な入力(プレースホルダ等)にも実は残っている」ケースが
  あるため、修正後は両極端な入力(最短/最長、装飾なし/複数装飾の組み合わせ)
  で個別に確認すること。

**H-2-4追加分で実施した変更(1回目)**:
- フォーカス/選択/チェック状態の色をすべて新設`selection_accent`
  (opaqueな青、`#2563EB`/`#3B82F6`)に統一: ボタン/入力欄の`:focus`枠線、
  `QDockWidget[dockActive="true"]`(H-2-3)の枠線、`QTabBar::tab:selected`の
  下線・文字色、`QRadioButton::indicator:checked`、チェックボックスの
  チェック時塗りつぶし。ブランドアクセントとしての`accent`(ボタン背景等)
  自体は変更していない。
- プロパティドックの余計な枠線は`QScrollArea`に一切QSSが無く、Qt既定の
  sunkenフレームがそのまま出ていたのが原因(`QScrollArea { border: none; }`
  で解消)。
- 背景色`bg`/`surface_2`を寒色寄りグレー(`bg=#F6F7F9`, `surface_2=
  #EEF0F3`)に変更(3案提示→ユーザー選択)。
- タイトル/軸ラベル編集を、旧QMenuベースのポップアップパネルから独立
  ポップアップダイアログ`LabelEditDialog`(`gui/dialogs.py`、レイアウト画像
  提示に沿った構成)に置き換え。ギリシャ文字/記号パレット
  (`LABEL_SYMBOL_PALETTE`)もギリシャ文字16種+算術・数学記号16種の計32種に
  拡張。`gui/mixins/settings_mixin.py`/`gui/mixins/ui_setup_mixin.py`の
  旧実装(`_capture_label_format_selection`等)は削除。
- タイトル/軸ラベルのmathtextライブプレビュー(`gui/mathtext_preview.py`、
  日本語グリフフォールバック、`FitWidthPixmapLabel`による幅/高さ自動フィット)、
  クリックで`LabelEditDialog`が開く`_ClickableMathPreviewLabel`、複数装飾の
  合成(`\boldsymbol`)、タブ上部の灰色線・プロットパネル枠線・ミニマップ配色
  等、以降の4ラウンドの詳細は`docs/GUI_MODERNIZATION_PROGRESS.md`の
  「H-2-4追加分」〜「H-2-4追加分(4回目)」行と`docs/gui_style_audit.md`の
  対応節(Before/After画像付き)を参照。

H-2-3で実施した変更:
- `QDockWidget`に枠線+角丸(8px)を追加(`plot_container`と同じ「1枚の
  カード」の考え方)。
- フォーカス時の強調は、QDockWidget自体に「アクティブ」を示すQt標準の状態が
  無いため、新設の`theme.install_dock_focus_highlight(window)`が
  `QApplication.focusChanged`を監視し、フォーカスされたウィジェットの祖先を
  たどってQDockWidgetを特定、動的プロパティ`dockActive`をQSSの属性セレクタ
  (`QDockWidget[dockActive="true"]`)経由で反映する自前実装。**複数タブ対応の
  注意点**: `focusChanged`はプロセス内全体で共有される単一のシグナルのため、
  見つかったドックが管轄する`window`のものでない場合は無視するガードが必須
  (各PlotterAppタブは完全に独立したウィンドウという設計方針)。
  `undo_history_dock`は`MainAppWindow`自身が持つドックのため、
  `gui/main_window.py`側とは別に`gui/main_app_window.py`側でも個別に
  組み込んだ。

H-2-4で実施した変更(実機フィードバックによる複数回の調整):
- スピンボックスの上下ボタンを、独立した角丸ボックス(参考イメージ提示を
  受けて全4隅を丸め、margin付き)に変更し、さらに背景・枠線を常時透明にして
  矢印だけが浮くミニマルな見た目にした。
- 矢印マーク自体の三角形サイズを拡大(`_spinbox_arrow_icon_url()`のキャンバス
  サイズごと見直し、キャッシュファイル名にサイズを含めて旧サイズの使い回しを
  防止)。コンボボックス側の矢印だけ旧サイズ(10px)のまま揃っていなかった
  不具合(実機フィードバックで発覚)も12pxに統一して解消。
- テキスト選択・メニュー/メニューバーの`::item:selected`・コンボボックスの
  ポップアップ・汎用リスト/テーブルの`::item:selected`を、いずれもティール系
  `accent`/`accent_soft`からH-2-2の`selection_highlight`(青)に統一
  (「選択時とかポップアップの色が緑っぽい」との指摘に対応)。ボタンの
  hover/pressedやフォーカス枠は`accent`のまま変更していない。
- `ui_main_window.py`(Designer生成物、手で編集しない方針)に焼き込まれた
  フォームラベルの末尾全角コロン「：」を、`PlotterApp.__init__`最後で
  `_strip_trailing_colon_from_labels()`により実行時に除去した。

H-0の調査で判明した重要な事実(H-2の残り項目でも必ず踏まえること):
- `gui/theme.py`が唯一のQt側QSS/パレット実装(別`.qss`ファイルは無い)。
- **matplotlib側(`gui/canvas.py`)とミニマップ(`gui/minimap_widget.py`)は、
  `gui/theme.py`のトークンとは完全に独立した、それぞれ個別にハードコードされた
  ダーク/ライト配色定数を持つ(値も一致していない)。統合するかは未判断のまま
  スコープ外としている**(docs/gui_style_audit.md 7節参照)。
- 「カスタムカラーパレット」機能(QSettings永続化)はデータセットの線色サイクル
  であり、UIテーマのアクセントカラーとは無関係。

## 次にやること

ユーザーから明示的に番号(例:「44実施」)で指示があるまで着手しない。
次に来る想定はトラック2 フェーズH-2-5(#44〜、H-2の残りコンポーネント磨き込み)。
H-2は8つのサブ項目(H-2-1〜H-2-8、ロードマップ#40〜47)を1つずつ順に進める
増分実装のため、複数まとめて指示された場合もコンポーネント単位で区切って
コミットすること。指示が来たらまず`docs/roadmap.html`の該当行と、
`docs/gui_style_audit.md`(H-0の調査結果+これまでのH-2 Before/After記録)、
必要なら`docs/Graphica_ROADMAP_PLUGIN_AND_GUI.md`のフェーズH節を読んでから
着手する。

**H-2-3/H-2-4本体 + 「H-2-4追加分」〜「H-2-4追加分(4回目)」まで、すべて
フルスイートグリーン確認済み**(2026-08-08、最終636件)。この後コミット・
pushする。H-2-4系の作業はこれで一区切り。

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
- **`ui_main_window.py`(pyside6-uic生成物)のテキストは`\uXXXX`エスケープ
  形式で埋め込まれている**ため、日本語の語句(例:「凡例名」)や記号
  (例: 全角コロン「：」)をこのファイル内でリテラル文字列として検索しても
  ヒットしない(H-2-4で発覚。`grep`はもちろん、Pythonの`"文字列" in content`
  でも同様に失敗する)。存在確認は`\uXXXX`のコードポイント、またはPySide6を
  実際にimportしてオブジェクトの`.text()`を読む方法で行うこと。
- **QPixmap/QPainterの生成は、QApplicationインスタンスが存在しない状態だと
  不安定(クラッシュしてPythonの例外機構すら通らず、exit code 127で
  トレースバック無しに落ちることがある)**(H-2-4で発覚。同じ`python -c`の
  ワンライナーが、セッション内の別の時点では成功していたにもかかわらず、
  後になって突然この形で落ちるようになった。原因は特定できていないが、
  再現条件は「QApplication未生成のままQPixmap/QPainterを触る」ことに
  一貫して関連している)。`gui/theme.py`の`build_qss()`(内部で矢印アイコンの
  QPixmap/QPainterを生成する)をスクリプトから単体で検証する際は、必ず先に
  `QApplication.instance() or QApplication(sys.argv)`を作ってから呼ぶこと。
  pytest経由(`conftest.py`の`qapp`フィクスチャ)では常にQApplicationが
  用意されているため、この問題は発生しない。
