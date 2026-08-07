# GUIモダン化(トラック2、フェーズH) 進捗管理

`Graphica_MASTER_SCHEDULE.md` のトラック2(GUIモダン化)の進捗を記録する。
トラック1(プラグインAPI拡張)の進捗は`docs/PLUGIN_API_PROGRESS.md`を参照
(役割は同じ、対象トラックが異なるだけ)。「今どこまで進んでいて次に何を
やるか」の短い要約は`CURRENT_STATE.md`を先に見ること。このファイルは項目が
完了するたびに追記していく(上書きしない)。

**着手条件**: フェーズA〜G(トラック1)が全て完了していること。**達成
(2026-08-07、トラック1完了)**。H-0のみ先行着手可という例外規定だったが、
今回は既にトラック1完了後の着手のため関係なし。

**ブランチ**: `feature/gui-modernization`(`feature/format-version-and-foundations`
から分岐。ロードマップ側の推奨に従い、プラグインAPI拡張とは別PRにする)。

## フェーズH: GUIモダン化(QSSカスタマイズ)

| ID | 項目 | 状態 | 完了日 | 備考 |
|---|---|---|---|---|
| H-0 | 現状把握 | ✅ 完了 | 2026-08-07 | `docs/gui_style_audit.md`新設。QSS/パレット実装は`gui/theme.py`1ファイルに集約(別`.qss`ファイルは無し)、ダーク/ライト切替はQSS+QPalette併用。**重要な発見**: matplotlib側の配色(`gui/canvas.py`)とミニマップ(`gui/minimap_widget.py`)は、`gui/theme.py`のトークンとは完全に独立した、それぞれ個別にハードコードされた`DARK_*`/`LIGHT_*`定数を持つ(値も不一致、統合するかは今後要判断)。レイアウトエディタのドラッグハンドル(#85)はQtウィジェットでもmatplotlib artistでもない、マウスイベント駆動の`ax.set_position()`直接操作(可視インジケータ自体が存在しない)。「カスタムカラーパレット機能」(QSettings)はデータセット線色サイクルであり、UIテーマのアクセントカラーとは無関係と判明(H-1の完了条件にある「関係整理」は「現状は上書き元が無いので対応不要」という結論) |
| H-1 | デザイントークンの整理 | ✅ 完了 | 2026-08-07 | `gui/theme.py`の`_LIGHT_TOKENS`/`_DARK_TOKENS`(既に存在していた)を公開名`LIGHT_TOKENS`/`DARK_TOKENS`にリネームし、`_build_flat_qss(dark: bool)`を`build_qss(tokens: dict)`という公開関数に変更(ロードマップのシグネチャ通り)。`apply_theme()`はこの2つを経由するようリファクタ。**全面書き直しはせず、既存のトークン的構造を公開API化する最小限の整理に留めた**(diff はリネームのみ、値・ロジックは無変更につき視覚的な回帰は原理的に発生しない)。`gui/canvas.py`・`gui/minimap_widget.py`の独自定数は今回統合しない(H-0の所見の通り、意図的な差か単なるズレか切り分けが必要なため、明示的にスコープ外とした) |

**フェーズH-0/H-1完了条件**: 上記2項目が✅。**達成(2026-08-07)**。H-2(コンポーネント単位の磨き込み)に着手可能。

## フェーズH-2: コンポーネント単位の磨き込み(推奨着手順1〜8のうち順に実施)

| ID | 項目 | 状態 | 完了日 | 備考 |
|---|---|---|---|---|
| H-2-1 | メインツールバー・メニューバー | ✅ 完了 | 2026-08-07 | `gui/mixins/quick_access_mixin.py`の`_create_quick_access_toolbar()`に`toolbar.setMovable(False)`を追加。Qt標準ツールバーの移動グリップ(ドラッグ用ハンドル)が、上部固定・移動機能未提供のこのアプリのフラット/ミニマルテーマと視覚的に馴染んでいなかったため除去。実際に`window.grab()`でBefore/Afterスクリーンショット(ライト/ダーク)を撮って確認し、`docs/gui_style_audit.md`のH-2-1節に記録(`docs/screenshots/h2-1/`配下にPNG)。メニューバー自体(QMenuBar/QMenu)はH-1完了時点で既に十分なQSSカバレッジがあり、追加変更なし。`tests/test_quick_access_mixin.py::test_quick_access_toolbar_is_not_movable`を追加 |

### H-2-2〜H-2-8、H-3〜H-5

未着手。詳細は`Graphica_ROADMAP_PLUGIN_AND_GUI.md`のH-2節以降(推奨着手順2〜8)を参照。

---

## 更新履歴

- 2026-08-07: 新規作成。H-0・H-1完了を反映。
- 2026-08-07: H-2-1(メインツールバー・メニューバー)完了を反映。
