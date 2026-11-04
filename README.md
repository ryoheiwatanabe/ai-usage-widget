# AI Usage

CodexとClaudeの5時間枠・週間枠の残量と、Codexのクレジットをまとめて表示する、Mac・iPhone用のWidgetKitアプリと、iPhoneのScriptable版・Fire HDのブラウザ表示です。

Macが取得した残量データをiCloud Driveへ保存し、iPhoneと共有します。Codexの画面や、このアプリのウィンドウを開き続ける必要はありません。取得するMacはログイン中で、スリープしておらず、ネットにつながっている必要があります。

## 必要な環境

- macOS 14以降、またはiOS 17以降。開発時はXcode 26.3を使用しています。
- WidgetKit版のビルドにはXcodeが必要です。M1の保存用アプリにはCommand Line ToolsのSwiftコンパイラ、Python 3.9以降、Codex CLIを使います。
- 取得したいアカウントでCodex CLIへログイン済みであること。Claudeも表示する場合はClaude Codeへのログインが必要です。
- iPhoneと共有する場合は、両端末で同じAppleアカウントのiCloud Driveを有効にしてください。

APIキーの追加設定は不要です。認証情報は各CLIが管理するものを使い、端末間では残量・クレジット・取得時刻・取得状態だけを同期します。

WidgetKit版Macアプリからの同期は `/usr/bin/python3` を使います。Appleの開発ツールが提供するPythonです。別の場所にPythonだけを導入した端末では、後述の手動コマンドをそのPythonで実行するか、`Mac/MacSync.swift` のPythonパスを調整してください。

## ビルド

プロジェクトのBuild Settingsにある `AI_USAGE_BUNDLE_ID` を、自分が使えるBundle IDへ変更してください。この値からアプリ・ウィジェットのBundle IDとApp Group名が決まります。同じ所有者の端末間で引き継ぐ場合は、既存の値を維持できます。

AppleのTeam IDはソースに固定していません。コマンドでビルドする場合は、以下の `YOUR_TEAM_ID` を自分のTeam IDに置き換えてください。

```sh
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage \
  -configuration Release -destination 'platform=macOS' \
  -derivedDataPath build/mac DEVELOPMENT_TEAM=YOUR_TEAM_ID build
```

Mac用のアプリは `build/mac/Build/Products/Release/AI Usage.app` に生成されます。自分のApplicationsフォルダへ配置して開いてください。Xcodeの画面で設定する場合は、アプリとウィジェットの両ターゲットでSigning Teamを選びます。署名やApp Groupの設定が未作成の場合は、Xcodeで設定を完了してください。

iPhoneは、Xcodeで `AIUsage.xcodeproj` を開き、実行先にiPhoneを指定してRunします。署名の有効期限は使用するプロビジョニングプロファイルで確認してください。

## Macで取得・同期する

1. iCloud Driveに `AI Usage` フォルダを作成します。
2. アプリの「iCloudの同期先を選ぶ」で、そのフォルダを選びます。
3. 「今すぐ同期」で残量と取得時刻を確認し、「自動同期を開始」を押します。
4. デスクトップを右クリックし、「ウィジェットを編集」から「AI Usage」の中サイズを追加します。

自動同期はユーザーのLaunchAgentで15分ごとに実行します。アプリを開き「自動同期を停止」を押すと停止できます。スリープ中やログアウト中は新しい残量を取得しません。

アプリを使わず、取得処理だけを手動で試すこともできます。

```sh
python3 tools/sync_usage.py
```

このコマンドは `iCloud Drive/AI Usage/usage.json` へ出力します。`--output` で別のファイルを指定できます。手動コマンドだけではMacウィジェットの端末内キャッシュは更新されません。

## 別のMacが取得したデータをMacで表示する

取得していたMacでは先に「自動同期を停止」を押してください。アプリの「iCloudから受け取る」で、取得するMacが保存したJSONファイルを選びます。ウィジェットも同じファイルを読み、受信に失敗した場合は前回値を表示します。取得側へ戻す場合は「このMacで取得する」を選びます。

## M1で確認用の定期取得を始める

旧Macの同期を継続したまま、別名ファイルへ保存します。

```sh
python3 tools/install_collector.py --output \
  "$HOME/Library/Mobile Documents/com~apple~CloudDocs/AI Usage/usage-m1-check.json"
```

このinstallerは、既存のSwiftコンパイラで小さな保存用アプリを作ります。開いた画面でiCloud Driveの「AI Usage」フォルダを選ぶと、取得・保存を確認してから900秒間隔のLaunchAgentを登録します。`--output` の親フォルダは選択画面の初期表示に使い、実際の保存先は本人が選びます。ファイル名は確認用に固定しています。既存ジョブがある場合は変更せず終了します。

Pythonは端末内の `~/Library/Application Support/AIUsage/collector/usage-m1-check.json` へ取得します。保存用アプリが同じJSONを選択済みiCloudフォルダへコピーするため、PythonやFire表示サーバーへiCloudの権限を付ける必要はありません。最初のローカルファイルがない場合は、iCloudにある確認用の前回値を検証して引き継ぎます。

## iPhoneで表示する

WidgetKit版はアプリの「iCloudのファイルを選ぶ」から、Macが出力した `AI Usage/usage.json` を選択します。ホーム画面を長押しし、「編集 → ウィジェットを追加 → AI Usage」から中サイズを追加してください。

更新のタイミングはiOSとiCloudの状態に左右されます。ウィジェットには取得時刻を表示し、取得に失敗した場合は前回の結果を残します。リセット時刻を過ぎた枠は、残量を「—」、リセットまでの時間を「更新待ち」と表示します。

Scriptable方式は [導入手順](docs/scriptable/README.md) を参照してください。

## Fire HDで表示する

M1と同じWi-Fiへ接続し、Silkで残量ページを開きます。[設定・確認手順](docs/fire_hd/README.md) を参照してください。実際の利用データはインターネットへ公開しません。M1の表示サーバー起動、FireからのWi-Fi受信と実値・取得時刻の表示を確認しました。

## 実装と確認の状況

- Codexは公式CLIの `account/rateLimits/read` を使用し、実際の残量取得を確認済みです。取得される枠はアカウントによって異なります。提供されない枠は「—」と表示します。
- M1でClaude Codeの正規ログインと `/usage` からの実値取得を確認しました。初回確認は専用の空ディレクトリで行い、ANSIの画面差分を復元して読み取ります。safe-modeを使い、ユーザーのhooks・MCP・ツールを無効にします。
- 引き継ぎ時点でMac・iPhone実機用・シミュレータのビルドを確認済みです。今回のM1では保存用アプリのビルド、LaunchAgentからの実値取得・iCloud保存、次の15分タイマーによる自動更新を確認しました。表示用Macアプリの変更後ビルドは未確認です。
- Macデスクトップへのウィジェット配置と、iPhoneのWidgetKit専用アプリでのiCloud同期は未確認です。選択したScriptable版の確認結果は以下のとおりです。
- MacのiCloud受信処理を実装し、Swiftの型検査を確認しました。変更後のアプリのビルド・署名・普段使うMacへの導入は未確認です。
- iPhoneはScriptable方式を選択済みです。確認用JSONとJSのiCloud経由の到達、Scriptable内での実値・取得時刻表示は本人確認済みです。ホーム画面ウィジェットの実値・取得時刻表示も本人確認済みです。

続きの開発・常駐Macへの移行は、[引き継ぎメモ](docs/migration_handoff/README.md)を参照してください。

## テスト

```sh
cd tools
python3 -m unittest -v test_sync_usage.py
```

期間による枠の割当て、0クレジット、取得失敗時の時刻保持、Claude画面の差分更新とリセット日時、Fire HD配信の制限を確認します。全件実行は `python3 -m unittest discover -s tools -v` です。

一部の枠やクレジットが取得できなくなった場合は、そのサービス全体を前回値と時刻のまま保持します。現行のJSONでは取得時刻がサービス単位のため、古い値に新しい時刻を付けないことを優先しています。

## ライセンス・参照先

[MIT License](LICENSE)。著作権表示とライセンス文を保持してください。

取得方法は[OpenAI App Server](https://learn.chatgpt.com/docs/app-server)、ウィジェットは[Apple WidgetKit](https://developer.apple.com/documentation/widgetkit/creating-a-widget-extension)を参照しています。
