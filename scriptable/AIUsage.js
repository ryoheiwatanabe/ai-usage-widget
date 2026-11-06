// 「AI Usage Folder」でiCloudのAI Usageフォルダを指定してください。
const fm = FileManager.local(), cloud = FileManager.iCloud();
const cache = fm.joinPath(fm.cacheDirectory(), 'ai-usage-last-snapshot.json');
let snapshot = null, failed = false, failureMessage = '';
function valid(s) {
  return s && s.schemaVersion === 1 && Number.isFinite(Date.parse(s.generatedAt)) &&
    Date.parse(s.generatedAt) <= Date.now() + 300000 && Array.isArray(s.providers) &&
    s.providers.length <= 2 && s.providers.every(p => ['codex','claude'].includes(p.id) &&
      Array.isArray(p.windows) && p.windows.every(w => Number.isFinite(w.remainingPercent) &&
        w.remainingPercent >= 0 && w.remainingPercent <= 100));
}
try { const old = JSON.parse(fm.readString(cache)); if (valid(old)) snapshot = old; } catch (_) {}
try {
  let path;
  if (cloud.bookmarkExists('AI Usage Folder')) {
    const folder = cloud.bookmarkedPath('AI Usage Folder');
    if (!cloud.isDirectory(folder)) throw Error('AI Usage FolderにはJSONファイルではなく、AI Usageフォルダを登録してください。');
    path = cloud.joinPath(folder, 'usage.json');
  } else {
    if (!cloud.bookmarkExists('AI Usage Live')) throw Error('設定のFile Bookmarksで、iCloud DriveのAI Usageフォルダを「AI Usage Folder」として登録してください。');
    path = cloud.bookmarkedPath('AI Usage Live');
    if (path.split('/').pop() !== 'usage.json') throw Error('AI Usage Liveが確認用ファイルを参照しています。AI Usageフォルダを「AI Usage Folder」として登録してください。');
  }
  await cloud.downloadFileFromiCloud(path);
  if (cloud.fileSize(path) > 128) throw Error('ファイルが大きすぎます。');
  const current = JSON.parse(cloud.readString(path));
  if (!valid(current)) throw Error('形式が不正です。');
  if (snapshot && Date.parse(current.generatedAt) < Date.parse(snapshot.generatedAt))
    throw Error('iCloudの本番データが端末内の前回値より古いため、前回値を保持しています。');
  snapshot = current; fm.writeString(cache, JSON.stringify(snapshot));
} catch (error) {
  failed = true;
  failureMessage = String(error.message || error).slice(0, 512);
}
const widget = new ListWidget();
widget.backgroundColor = new Color('101a17'); widget.setPadding(14,16,12,16);
function label(stack, value, size, color) {
  const t = stack.addText(value); t.font = Font.systemFont(size);
  t.textColor = new Color(color || 'ecfff5'); t.lineLimit = 1; t.minimumScaleFactor = 0.65;
}
function resetLine(w, now) {
  const reset = Date.parse(w.resetsAt);
  if (!Number.isFinite(reset)) return w.resetLabel || '';
  const minutes = Math.floor((reset - now) / 60000);
  const hours = Math.floor(minutes / 60);
  const value = hours >= 24 ? Math.floor(hours / 24)+'日'+hours%24+'時間' :
    hours > 0 ? hours+'時間'+minutes%60+'分' : minutes > 0 ? minutes+'分' : '1分未満';
  const d = new Date(reset);
  const hhmm = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  return (d.getMonth()+1)+'/'+d.getDate()+' '+hhmm+'（あと'+value+'）';
}
const now = Date.now();
label(widget, failed ? 'AI USAGE · 本番未接続' : 'AI USAGE · 本番', 10, failed ? 'ffcc88' : '8adfba'); widget.addSpacer(4);
const columns = widget.addStack();
for (const [index,id] of ['codex','claude'].entries()) {
  if (index) columns.addSpacer(18);
  const col = columns.addStack(); col.layoutVertically();
  const p = snapshot && snapshot.providers.find(p => p.id === id);
  label(col, id === 'codex' ? 'Codex' : 'Claude', 17); col.addSpacer(4);
  for (const [key,name] of [['session','5時間'],['weekly','週間']]) {
    const w = p && p.windows.find(w => w.id === key);
    const expired = w && w.resetsAt && Date.parse(w.resetsAt) <= now;
    label(col, `${name}  ${w && !expired ? Math.round(w.remainingPercent)+'%' : '—'}`, 15);
    if (!w || expired) label(col, '更新待ち', 9, 'ffcc88');
    else { const reset = resetLine(w, now); if (reset) label(col, reset, 9, 'a6bcaf'); }
  }
  if (id === 'codex') label(col, 'クレジット '+(p && p.credits != null ? p.credits : '—'), 10, 'a6bcaf');
  if (failed || !p || !p.measuredAt || p.status === 'stale' || Date.now()-Date.parse(p.measuredAt)>1800000)
    label(col, '更新待ち', 9, 'ffcc88');
  if (p && p.measuredAt) {
    const d = new Date(p.measuredAt);
    label(col, `取得 ${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`, 9, 'a6bcaf');
  } else label(col, '未取得', 9, 'a6bcaf');
}
widget.refreshAfterDate = new Date(Date.now()+900000);
Script.setWidget(widget);
if (config.runsInApp) {
  if (failed) {
    const alert = new Alert();
    alert.title = '本番データを更新できません';
    alert.message = failureMessage + '\n前回の値と取得時刻を表示しています。';
    alert.addAction('確認');
    await alert.presentAlert();
  }
  await widget.presentMedium();
}
Script.complete();
