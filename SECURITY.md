# セキュリティポリシー / Security Policy

[日本語](#日本語) | [English](#english)

## 日本語

### サポート対象のバージョン

セキュリティの修正は **最新のリリース** に対して行います。古いバージョンをお使いの場合は、
[最新版](https://github.com/STsuruga/Graphica/releases/latest) に更新してから、問題が再現するか確認してください。

### 脆弱性の報告方法

**脆弱性は公開の Issue に書かないでください。** 修正前に悪用される恐れがあります。

次のページから非公開で報告してください(GitHub アカウントが必要です)。

**https://github.com/STsuruga/Graphica/security/advisories/new**

報告には、できる範囲で次の内容を含めてください。

- 影響を受けるバージョンと OS
- 問題の内容と、想定される影響(例: 細工したファイルを開くとコードが実行される)
- 再現手順、または再現用のファイル
- 考えられる対処方法(あれば)

受け取った報告は確認次第返信し、修正の見通しをお知らせします。個人で開発しているため、
返信までに数日かかることがあります。修正版の公開後、希望があれば報告者として記載します。

### 対象になるもの

特に次のような問題の報告を歓迎します。

- 細工したプロジェクトファイル(`.graphica` / `.pkl`)や書式テンプレートを開いたときに、
  任意のコードが実行される、または意図しないファイルが読み書きされる
- 細工したデータファイル(CSV / テキスト / Excel)や、列の計算の式で任意のコードが実行される
- プラグインの zip をインストールするときに、プラグイン用フォルダの外へファイルが書き込まれる
- 配布している実行ファイル(Releases の zip)に関する問題

### 対象外のもの

- **プラグインが任意のコードを実行できること自体。** プラグインは Python のコードとして動く仕組みで、
  信頼できる配布元のものだけをインストールする前提です(Wiki の「プラグイン」ページを参照)。
- 実行ファイルに署名していないため、Windows の SmartScreen や macOS の Gatekeeper の警告が出ること。
- すでに PC を操作できる攻撃者を前提とした問題。

## English

### Supported versions

Security fixes are made against **the latest release** only. If you are on an older version, please update to
[the latest release](https://github.com/STsuruga/Graphica/releases/latest) and check whether the issue still reproduces.

### Reporting a vulnerability

**Please do not report vulnerabilities in public issues.**

Report them privately here (a GitHub account is required):

**https://github.com/STsuruga/Graphica/security/advisories/new**

Please include as much of the following as you can:

- Affected version and operating system
- A description of the issue and its likely impact (e.g. opening a crafted file executes code)
- Steps to reproduce, or a file that reproduces it
- A suggested fix, if you have one

Reports are acknowledged once reviewed, with an expected timeline for a fix. Graphica is maintained by an
individual, so a reply may take a few days. Reporters will be credited in the fix release if they wish.

### In scope

- Arbitrary code execution or unintended file access when opening a crafted project file
  (`.graphica` / `.pkl`) or format template
- Code execution through crafted data files (CSV / text / Excel) or column-calculation expressions
- Installing a plugin zip writing files outside the plugins folder
- Problems with the distributed executables (the zips on the Releases page)

### Out of scope

- **Plugins being able to run arbitrary code.** Plugins are Python code by design; install only plugins from
  sources you trust.
- Windows SmartScreen or macOS Gatekeeper warnings caused by the executables being unsigned.
- Issues that assume an attacker who already controls the machine.
