# Fire HDで表示する

M1が取得した残量を、同じWi-Fi上のFire HDのSilkブラウザで表示します。USBは初回設定と確認に使い、表示中は外せます。FireにCodex・Claudeの認証情報を渡す必要はありません。

## M1側

Python 3.9以降を使います。取得処理とは別のLaunchAgentで、表示ページと残量JSONだけを配信します。AIモデルを呼び出す処理はありません。表示サーバーの稼働中は `caffeinate -i` でM1のアイドルスリープを抑えます。蓋を閉じたときのスリープは防げないため、電源につないで蓋を開けて使ってください。

```sh
python3 tools/install_firehd.py \
  --source "$HOME/Library/Mobile Documents/com~apple~CloudDocs/AI Usage/usage-m1-check.json" \
  --address M1のLANアドレス --device-ip FireのLANアドレス
```

`--address`と`--device-ip`は実際のIPアドレスに置き換えてください。共有ファイルへの移行確認が終わるまでは、確認用ファイルを指定します。既存の設定がある場合、installerは変更せずに終了します。

AppleのPythonを使う場合、LaunchAgentはPython.app本体を直接起動します。フルディスクアクセスを設定する場合も、そのPython.appを対象にしてください。Command Line ToolsのPython 3.9では次の場所です。

```text
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app
```

別の場所のPythonに許可を付けても、定期実行側には適用されないことがあります。権限の変更後は表示サーバーを再起動し、実際にJSONを受信できることを確認します。

FireのSilkで、表示された `http://M1のLANアドレス:8765` を開きます。ブックマークに登録すれば、次回も同じページを開けます。スリープ時はFireの電源ボタンで復帰します。画面を常時点灯する設定は自動で変更しません。

接続を許可するIPアドレスはFireとlocalhostだけです。指定したHost以外のアクセスも拒否し、任意のファイルやディレクトリを公開しません。HTTP通信には暗号化や本人認証がないため、信頼できる家庭内Wi-Fiで使ってください。IPアドレスの制限は端末を暗号学的に識別するものではありません。インターネットへのポート公開はしないでください。

M1またはFireのIPアドレスが変わった場合は接続できなくなります。ルーターのDHCP予約で固定するか、現在の設定を停止・削除して新しいIPで登録し直してください。Wi-Fiの接続先やルーター設定は自動で変更しません。

## 更新と取得失敗

ページは1分ごとにM1のファイルを確認します。Codex・Claudeの取得間隔は15分です。サービスごとの取得時刻を表示し、通信に失敗したときはブラウザに保存した前回値を表示します。リセット時刻を過ぎた枠は数値を「—」、状態を「更新待ち」にします。

ブラウザの保存データを削除すると、オフライン時の前回表示も消えます。ページ自体をオフラインで新しく開く機能はありません。M1へ接続できる状態でページを開いてください。

## 停止・設定し直す

```sh
launchctl bootout "gui/$(id -u)/com.ryo.AIUsageBoard.firehd"
rm "$HOME/Library/LaunchAgents/com.ryo.AIUsageBoard.firehd.plist"
```

その後、必要なsourceとIPを指定してinstallerを実行します。Fire側の確認用USB転送を設定した場合は、Wi-Fi確認前に `adb reverse --remove tcp:8765` で解除します。
