// Run the deployed script with Scriptable API doubles; no account or network access.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../scriptable/AIUsage.js'), 'utf8');
const now = Date.parse('2030-01-02T00:00:00Z');
const sample = (age = 0) => ({schemaVersion: 1, generatedAt: new Date(now - age).toISOString(),
  providers: ['codex', 'claude'].map(id => ({id, status: 'connected', measuredAt: new Date(now - age).toISOString(),
    credits: null, windows: [{id: 'weekly', remainingPercent: 50, resetsAt: new Date(now + 86400000).toISOString()}]}))});
const old = sample(86400000), current = sample();

async function run({bookmarks = {}, files = {}, cached = old, app = true, directory = true, readError = false} = {}) {
  const texts = [], alerts = [], downloads = [], reads = [], writes = [];
  let cache = cached;
  const local = {joinPath: (a,b) => a+'/'+b, cacheDirectory: () => '/cache',
    readString: () => JSON.stringify(cache), writeString: (_,text) => {cache = JSON.parse(text); writes.push(text);}};
  const cloud = {joinPath: (a,b) => a+'/'+b, bookmarkExists: n => Object.hasOwn(bookmarks,n),
    bookmarkedPath: n => bookmarks[n], isDirectory: () => directory,
    downloadFileFromiCloud: async p => {downloads.push(p);}, fileSize: () => 1,
    readString: p => {reads.push(p); if (readError || !files[p]) throw Error('iCloud read failed'); return JSON.stringify(files[p]);}};
  class Stack {
    addText(text) {texts.push(text); return {};}
    addSpacer() {} addStack() {return new Stack();} layoutVertically() {} setPadding() {}
    async presentMedium() {}
  }
  class Alert {
    addAction() {} async presentAlert() {alerts.push(this.message);}
  }
  const context = vm.createContext({Date: class extends Date {static now() {return now;}},
    FileManager: {local: () => local, iCloud: () => cloud},
    ListWidget: Stack, Color: class {}, Font: {systemFont: () => ({})}, Alert,
    config: {runsInApp: app}, Script: {setWidget() {}, complete() {}}});
  await new vm.Script('(async () => {'+source+'})()').runInContext(context);
  return {texts, alerts, downloads, reads, writes, cache};
}

(async () => {
  let result = await run({bookmarks: {'AI Usage Folder': '/folder', 'AI Usage Live': '/old/usage.json', 'AI Usage': '/check.json'},
    files: {'/folder/usage.json': current, '/old/usage.json': old, '/check.json': old}});
  assert.deepEqual(result.reads, ['/folder/usage.json']);
  assert.equal(result.cache.generatedAt, current.generatedAt);
  assert.equal(result.texts[0], 'AI USAGE · 本番');
  const newer = sample(-60000);
  result = await run({bookmarks: {'AI Usage Folder': '/folder'}, files: {'/folder/usage.json': newer}, cached: current});
  assert.equal(result.cache.generatedAt, newer.generatedAt, 'Replacing the file at the same folder path is read next time');

  result = await run({bookmarks: {'AI Usage': '/usage-m1-check.json'}, files: {'/usage-m1-check.json': old}});
  assert.equal(result.reads.length, 0, 'Never fall back to the stopped check file');
  assert.deepEqual(result.cache, old);
  assert.match(result.alerts[0], /AI Usage Folder/);
  assert.match(result.texts[0], /本番未接続/);

  result = await run({bookmarks: {'AI Usage Live': '/usage-m1-check.json'}});
  assert.equal(result.downloads.length, 0);
  assert.match(result.alerts[0], /確認用ファイル/);

  result = await run({bookmarks: {'AI Usage Live': '/folder/usage.json'}, files: {'/folder/usage.json': current}});
  assert.equal(result.cache.generatedAt, current.generatedAt, 'Valid production file bookmarks remain compatible');

  result = await run({bookmarks: {'AI Usage Folder': '/folder'}, readError: true, app: false});
  assert.deepEqual(result.cache, old);
  assert.equal(result.writes.length, 0);
  assert.equal(result.alerts.length, 0, 'A widget must not try to present an alert');
  assert.match(result.texts[0], /本番未接続/);

  result = await run({bookmarks: {'AI Usage Folder': '/folder'}, files: {'/folder/usage.json': old}, cached: current});
  assert.deepEqual(result.cache, current, 'An older source must not replace the last successful sample');
  assert.match(result.alerts[0], /前回値より古い/);

  result = await run({bookmarks: {'AI Usage Folder': '/folder/usage.json'}, directory: false});
  assert.match(result.alerts[0], /フォルダを登録/);
  assert.equal(result.reads.length, 0);
  console.log('Scriptable reception: 8 scenarios passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
