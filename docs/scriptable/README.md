# iPhoneのScriptableで表示する

専用アプリの署名をせず、Scriptableの中サイズウィジェットで表示します。iPhoneでの導入とiCloudの受信確認は本人による操作が必要です。

1. iPhoneへ[Scriptable](https://apps.apple.com/jp/app/scriptable/id1405459188)をインストールし、1回開きます。
2. `scriptable/AIUsage.js` を `iCloud Drive/Scriptable` へコピーします。M1から `iCloud~dk~simonbs~Scriptable/Documents/AIUsage.js` へ配置できた場合、iPhoneの一覧に `AIUsage` が表示され、貼り付けは不要です。
3. Scriptableの「設定 → File Bookmarks → ＋」で、iCloud Driveの **AI Usageフォルダ** を `AI Usage Folder` という名前で追加します。`usage.json`単体ではなく、その親フォルダを選びます。スクリプトはその中の本番用`usage.json`を読みます。
4. Scriptableで`AIUsage`を実行し、値と「取得」時刻がM1の本番ファイルと一致することを確認します。
5. ホーム画面へScriptableの中サイズウィジェットを追加し、「ウィジェットを編集」でこのスクリプトを指定します。ホーム画面側でも本番の取得時刻が表示されるか確認します。

以前の`AI Usage Live`が本番の`usage.json`を指していれば、その設定も利用できます。フォルダ方式を優先するため、両方あっても構いません。以前の確認用`AI Usage`へ自動で戻る処理は廃止しました。

M1はファイルを置換して保存するため、フォルダを参照してから、その中の最新ファイルをパスで読みます。本番に接続できなかった場合は前回値・取得時刻を残し、「本番未接続」と表示します。Scriptable内で実行すると失敗理由を表示します。

更新間隔はiOSが決めます。15分後の再確認を要求しますが、厳密な15分間隔を保証するものではありません。リセット時刻を過ぎた枠には「—」を表示します。

iPhoneでCodexやClaudeへのログインは不要です。スクリプトはiCloudのJSONを読むだけで、モデルAPIを呼び出しません。

## 古い取得時刻のまま止まる場合

- Scriptableで`AIUsage`を開き、「本番未接続」やエラーが出る場合は`AI Usage Folder`の参照先を確認します。確認用ファイルは本番切り替え後に更新されないため、本番データの更新時刻と区別してください。
- アプリ内では新しい時刻になり、ホーム画面だけ古い場合は、ウィジェットの「Script」が`AIUsage`になっていることを確認します。iOSが次の実行を許可するまで反映に時間がかかる場合があります。

ファイルブックマークの仕様は [Scriptable FileManager](https://docs.scriptable.app/filemanager/#-bookmarkedpath) を参照してください。アプリ内のプレビュー成功とホーム画面でのiCloud受信成功は別々に確認してください。

参照先・ファイル置換・キャッシュ保持の回帰テストは `node tools/test_scriptable.cjs` で実行します。Scriptable APIを模したテストで、iPhone実機の確認は別途必要です。
