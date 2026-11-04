# iPhoneのScriptableで表示する

専用アプリの署名をせず、Scriptableの中サイズウィジェットで表示します。iPhoneでの導入とiCloudの受信確認は本人による操作が必要です。

1. iPhoneへScriptableをインストールします。
2. このリポジトリの `scriptable/AIUsage.js` の内容で、Scriptableに `AI Usage` というスクリプトを作ります。M1側でiCloudへコピー済みなら「ファイル」アプリの `iCloud Drive/AI Usage/AIUsage.js` から内容を受け取れます。
3. Scriptableの設定にある「File Bookmarks」で、名前を `AI Usage` としてJSONファイルへのブックマークを作ります。移行確認中は `iCloud Drive/AI Usage/usage-m1-check.json`、切り替え後は `usage.json` を選びます。フォルダではなくJSONファイル自体を選択します。
4. Scriptable内でスクリプトを実行し、Codex・Claudeの値と「取得」時刻をM1のJSONと比較します。
5. ホーム画面へScriptableの中サイズウィジェットを追加し、「ウィジェットを編集」でこのスクリプトを指定します。ホーム画面側でも受信できたか確認してください。

更新間隔はiOSが決めます。15分後の再確認を要求しますが、厳密な15分間隔を保証するものではありません。新しいJSONを読めなかった場合は、端末内に保存した前回値・取得時刻と「更新待ち」を表示します。リセット時刻を過ぎた枠には「—」を表示します。

iPhoneでCodexやClaudeへのログインは不要です。スクリプトはiCloudのJSONを読むだけで、モデルAPIを呼び出しません。

ファイルブックマークの仕様は [Scriptable FileManager](https://docs.scriptable.app/filemanager/#-bookmarkedpath) を参照してください。アプリ内のプレビュー成功とホーム画面でのiCloud受信成功は別々に確認してください。
