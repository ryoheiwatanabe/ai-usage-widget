import AppKit
import Foundation

// A native folder picker gives this app access to the selected iCloud folder.
// Python and the Fire HD server only need the local snapshot.
@main
struct CollectorBridge {
    static let label = "com.ryo.AIUsageBoard.collector-check"
    static let folderKey = "collectorFolder"
    static let runtime = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/AIUsage")
    static let snapshot = runtime.appendingPathComponent("collector/usage-m1-check.json")
    static let defaults = UserDefaults.standard

    static func main() {
        do {
            if CommandLine.arguments.contains("--setup") {
                _ = NSApplication.shared
                NSApp.setActivationPolicy(.regular)
                NSApp.activate(ignoringOtherApps: true)
                let panel = NSOpenPanel()
                panel.canChooseDirectories = true
                panel.canChooseFiles = false
                panel.canCreateDirectories = true
                panel.directoryURL = URL(fileURLWithPath: Bundle.main.object(forInfoDictionaryKey: "CollectorSuggestedFolder") as? String
                    ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Mobile Documents/com~apple~CloudDocs/AI Usage").path)
                panel.message = "iCloud Driveの「AI Usage」フォルダを選んでください。確認用usage-m1-check.jsonだけを保存します。"
                panel.prompt = "このフォルダを使う"
                guard panel.runModal() == .OK, let folder = panel.url else { return }
                let access = folder.startAccessingSecurityScopedResource()
                defer { if access { folder.stopAccessingSecurityScopedResource() } }
                let bookmark = try folder.bookmarkData(options: [.withSecurityScope], includingResourceValuesForKeys: nil, relativeTo: nil)
                defaults.set(bookmark, forKey: folderKey)
                let allConnected = try synchronize()
                let job = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/LaunchAgents/\(label).plist")
                let registered = run("/bin/launchctl", ["print", "gui/\(getuid())/\(label)"], quiet: true) == 0
                if !registered && run("/bin/launchctl", ["bootstrap", "gui/\(getuid())", job.path]) != 0 {
                    throw BridgeError.message("定期実行を登録できませんでした。")
                }
                let alert = NSAlert()
                alert.messageText = "確認用の取得とiCloud保存が完了しました"
                alert.informativeText = allConnected ? "15分ごとに更新します。旧Macの同期と共有usage.jsonは変更していません。" : "一部の取得に失敗したため前回値を保持しました。15分ごとに再試行します。"
                alert.runModal()
            } else {
                if try !synchronize() { exit(1) }
            }
        } catch {
            fputs("\(error.localizedDescription)\n", stderr)
            if CommandLine.arguments.contains("--setup") {
                let alert = NSAlert()
                alert.messageText = "設定を完了できませんでした"
                alert.informativeText = error.localizedDescription
                alert.runModal()
            }
            exit(1)
        }
    }

    static func run(_ executable: String, _ arguments: [String], quiet: Bool = false) -> Int32 {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        if quiet { process.standardOutput = FileHandle.nullDevice; process.standardError = FileHandle.nullDevice }
        do { try process.run(); process.waitUntilExit(); return process.terminationStatus }
        catch { return -1 }
    }

    static func synchronize() throws -> Bool {
        guard let bookmark = defaults.data(forKey: folderKey) else { throw BridgeError.message("アプリを開き、保存するiCloudフォルダを選んでください。") }
        var stale = false
        let folder = try URL(resolvingBookmarkData: bookmark, options: [.withSecurityScope, .withoutUI], relativeTo: nil, bookmarkDataIsStale: &stale)
        let access = folder.startAccessingSecurityScopedResource()
        defer { if access { folder.stopAccessingSecurityScopedResource() } }
        let python = Bundle.main.object(forInfoDictionaryKey: "CollectorPython") as! String
        let output = folder.appendingPathComponent("usage-m1-check.json")
        if !FileManager.default.fileExists(atPath: snapshot.path), FileManager.default.fileExists(atPath: output.path) {
            var readError: Error?
            var coordinationError: NSError?
            NSFileCoordinator().coordinate(readingItemAt: output, options: [], error: &coordinationError) { url in
                do {
                    let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
                    guard size <= 131_072 else { throw BridgeError.message("前回のファイルが大きすぎます。上書きせず停止しました。") }
                    let previous = try Data(contentsOf: url)
                    _ = try UsageSnapshot.decode(previous)
                    try previous.write(to: snapshot, options: .atomic)
                } catch { readError = error }
            }
            if let error = coordinationError ?? readError { throw error }
        }
        let script = runtime.appendingPathComponent("sync_usage.py")
        let process = Process()
        process.executableURL = URL(fileURLWithPath: python)
        process.arguments = [script.path, "--output", snapshot.path]
        var environment = ProcessInfo.processInfo.environment
        environment["PATH"] = Bundle.main.object(forInfoDictionaryKey: "CollectorPath") as? String
        process.environment = environment
        let started = Date()
        try process.run()
        process.waitUntilExit()
        let data = try Data(contentsOf: snapshot)
        guard data.count <= 131_072,
              let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              json["schemaVersion"] as? Int == 1,
              let generated = json["generatedAt"] as? String,
              let date = ISO8601DateFormatter().date(from: generated),
              date >= started.addingTimeInterval(-2), date <= Date().addingTimeInterval(300) else {
            throw BridgeError.message("新しい取得結果を確認できませんでした。前回のファイルを維持します。")
        }
        var coordinationError: NSError?
        var writeError: Error?
        NSFileCoordinator().coordinate(writingItemAt: output, options: .forReplacing, error: &coordinationError) { url in
            do { try data.write(to: url, options: .atomic) } catch { writeError = error }
        }
        if let error = coordinationError ?? writeError { throw error }
        if stale {
            defaults.set(try folder.bookmarkData(options: [.withSecurityScope], includingResourceValuesForKeys: nil, relativeTo: nil), forKey: folderKey)
        }
        print("確認用iCloud保存完了: \(generated)")
        return process.terminationStatus == 0
    }
}

enum BridgeError: LocalizedError {
    case message(String)
    var errorDescription: String? { switch self { case .message(let text): return text } }
}
