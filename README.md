# AI Usage

CodexとClaudeの5時間枠・週間枠の残量と、Codexのクレジットをまとめて表示する、Mac・iPhone用のWidgetKitアプリです。

Macが取得した残量データをiCloud Driveへ保存し、iPhoneと共有します。Codexの画面や、このアプリのウィンドウを開き続ける必要はありません。取得するMacはログイン中で、スリープしておらず、ネットにつながっている必要があります。

## 必要な環境

- macOS 14以降、またはiOS 17以降。開発時はXcode 26.3を使用しています。
- ビルドするMacにXcode、取得するMacにPython 3.9以降とCodex CLI。
- 取得したいアカウントでCodex CLIへログイン済みであること。Claudeも表示する場合はClaude Codeへのログインが必要です。
- iPhoneと共有する場合は、両端末で同じAppleアカウントのiCloud Driveを有効にしてください。

APIキーの追加設定は不要です。認証情報は各CLIが管理するものを使い、端末間では残量・クレジット・取得時刻・取得状態だけを同期します。

Macアプリからの同期は `/usr/bin/python3` を使います。この開発環境ではXcodeが提供するPythonです。別の場所にPythonだけを導入した端末では、後述の手動コマンドをそのPythonで実行するか、`Mac/MacSync.swift` のPythonパスを調整してください。

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

## iPhoneで表示する

アプリの「iCloudのファイルを選ぶ」から、Macが出力した `AI Usage/usage.json` を選択します。ホーム画面を長押しし、「編集 → ウィジェットを追加 → AI Usage」から中サイズを追加してください。

更新のタイミングはiOSとiCloudの状態に左右されます。ウィジェットには取得時刻を表示し、取得に失敗した場合は前回の結果を残します。リセット時刻を過ぎた枠は、残量を「—」、リセットまでの時間を「更新待ち」と表示します。

## 実装と確認の状況

- Codexは公式CLIの `account/rateLimits/read` を使用し、実際の残量取得を確認済みです。取得される枠はアカウントによって異なります。提供されない枠は「—」と表示します。
- Claude Codeのログイン確認と `/usage` の読取り処理は実装済みですが、ログイン後の実データ取得は未確認です。
- Mac・iPhone実機用・iPhoneシミュレータのビルド、Macアプリの実値表示、自動同期の正常終了を確認しています。
- Macデスクトップへのウィジェット配置と、iPhone実機でのiCloud同期は未確認です。
- 取得するMacを常駐端末へ移す場合、普段使うMacのウィジェットもiCloudから受け取る処理へ変更する必要があります。現在のMacウィジェットは端末内の共有キャッシュを読みます。
- Scriptable版は未実装です。iPhoneの専用アプリ方式とScriptable方式の選択は未確定です。

続きの開発・常駐Macへの移行は、[引き継ぎメモ](docs/migration_handoff/README.md)を参照してください。

## テスト

```sh
cd tools
python3 -m unittest -v test_sync_usage.py
```

期間による枠の割当て、0クレジットの保持、取得失敗時の時刻保持、不正な割合の拒否を確認します。

## ライセンス・参照先

[MIT License](LICENSE)。著作権表示とライセンス文を保持してください。

取得方法は[OpenAI App Server](https://learn.chatgpt.com/docs/app-server)、ウィジェットは[Apple WidgetKit](https://developer.apple.com/documentation/widgetkit/creating-a-widget-extension)を参照しています。
