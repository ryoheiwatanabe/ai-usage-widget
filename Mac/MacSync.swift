#if os(macOS)
import AppKit
import Foundation
import SwiftUI
import WidgetKit
import UniformTypeIdentifiers

enum MacSync {
    static let label = "com.ryo.AIUsageBoard.sync"
    private static let destinationKey = "macSyncDirectory"
    static let exportURL = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Mobile Documents/com~apple~CloudDocs/AI Usage/usage.json")
    private static var jobURL: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/LaunchAgents/\(label).plist")
    }
    private static var domain: String { "gui/\(getuid())" }
    static var hasDestination: Bool {
        UserDefaults(suiteName: UsageStore.groupID)?.data(forKey: destinationKey) != nil
    }

    @MainActor
    static func chooseDestination() throws -> Bool {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.canCreateDirectories = true
        panel.allowsMultipleSelection = false
        panel.directoryURL = exportURL.deletingLastPathComponent()
        panel.message = "iPhoneと共有する「AI Usage」フォルダを選んでください。"
        panel.prompt = "このフォルダに同期"
        guard panel.runModal() == .OK, let url = panel.url else { return false }
        let accessing = url.startAccessingSecurityScopedResource()
        defer { if accessing { url.stopAccessingSecurityScopedResource() } }
        let bookmark = try url.bookmarkData(options: [.withSecurityScope], includingResourceValuesForKeys: nil, relativeTo: nil)
        UserDefaults(suiteName: UsageStore.groupID)?.set(bookmark, forKey: destinationKey)
        return true
    }

    static func synchronize() throws -> UsageSnapshot {
        guard let bookmark = UserDefaults(suiteName: UsageStore.groupID)?.data(forKey: destinationKey) else {
            throw CocoaError(.fileReadNoPermission)
        }
        var stale = false
        let directory = try URL(resolvingBookmarkData: bookmark, options: [.withSecurityScope, .withoutUI],
                                relativeTo: nil, bookmarkDataIsStale: &stale)
        let accessing = directory.startAccessingSecurityScopedResource()
        defer { if accessing { directory.stopAccessingSecurityScopedResource() } }
        let output = directory.appendingPathComponent("usage.json")
        guard let script = Bundle.main.url(forResource: "sync_usage", withExtension: "py") else {
            throw CocoaError(.fileNoSuchFile)
        }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = [script.path, "--output", output.path]
        var environment = ProcessInfo.processInfo.environment
        environment["PATH"] = FileManager.default.homeDirectoryForCurrentUser.path
            + "/.npm-global/bin:" + FileManager.default.homeDirectoryForCurrentUser.path + "/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
        process.environment = environment
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        try process.run()
        _ = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        // Partial failures still produce a snapshot carrying the last successful sample.
        guard FileManager.default.fileExists(atPath: output.path) else {
            throw CocoaError(.fileReadNoSuchFile)
        }
        let snapshot = try UsageStore.store(Data(contentsOf: output))
        if process.terminationStatus != 0 && snapshot.generatedAt < Date().addingTimeInterval(-120) {
            throw CocoaError(.fileReadUnknown)
        }
        return snapshot
    }

    static func automaticSyncEnabled() -> Bool {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        process.arguments = ["print", "\(domain)/\(label)"]
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        guard (try? process.run()) != nil else { return false }
        process.waitUntilExit()
        return process.terminationStatus == 0
    }

    static func setAutomaticSync(_ enabled: Bool) throws {
        if !enabled {
            if automaticSyncEnabled() { try launchctl(["bootout", "\(domain)/\(label)"]) }
            if FileManager.default.fileExists(atPath: jobURL.path) { try FileManager.default.removeItem(at: jobURL) }
            return
        }
        guard !automaticSyncEnabled(), let executable = Bundle.main.executableURL else { return }
        try FileManager.default.createDirectory(at: jobURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        let job: [String: Any] = ["Label": label, "ProgramArguments": [executable.path, "--sync"],
                                  "StartInterval": 900, "RunAtLoad": true, "ProcessType": "Background"]
        let data = try PropertyListSerialization.data(fromPropertyList: job, format: .xml, options: 0)
        try data.write(to: jobURL, options: .atomic)
        try launchctl(["bootstrap", domain, jobURL.path])
    }

    private static func launchctl(_ arguments: [String]) throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        process.arguments = arguments
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        try process.run()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else { throw CocoaError(.executableRuntimeMismatch) }
    }
}

struct MacBoardScreen: View {
    @State private var snapshot = UsageStore.cached()
    @State private var updating = false
    @State private var automatic = MacSync.automaticSyncEnabled()
    @State private var hasDestination = MacSync.hasDestination
    @State private var receiving = UsageStore.hasSource
    @State private var message: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("AI USAGE").font(.system(size: 10, weight: .semibold, design: .monospaced))
                        .tracking(3).foregroundStyle(BoardStyle.muted)
                    Text("Codex と Claude").font(.system(size: 29, weight: .bold))
                }
                Spacer()
                Image(systemName: "square.grid.2x2.fill").font(.system(size: 22)).foregroundStyle(BoardStyle.blue)
            }

            UsageCard(snapshot: snapshot, syncFailed: message != nil).frame(height: 170)
                .shadow(color: .black.opacity(0.3), radius: 15, y: 8)

            VStack(alignment: .leading, spacing: 10) {
                Button(receiving ? "受信ファイルを変更" : "iCloudから受け取る") {
                    chooseSource()
                }.buttonStyle(.bordered).disabled(updating || automatic)
                if receiving {
                    Button("このMacで取得する") {
                        UsageStore.clearSource()
                        receiving = false
                    }.buttonStyle(.bordered).disabled(updating)
                }
                if !receiving && !hasDestination {
                    Button("iCloudの同期先を選ぶ") {
                        do {
                            if try MacSync.chooseDestination() { hasDestination = true; refresh() }
                        } catch { message = "同期先を設定できませんでした。" }
                    }.buttonStyle(.borderedProminent).tint(BoardStyle.blue)
                }
                Button { refresh() } label: {
                    HStack {
                        if updating { ProgressView().controlSize(.small) }
                        Label(receiving ? "今すぐ確認" : "今すぐ同期", systemImage: "arrow.clockwise")
                    }.frame(minWidth: 110)
                }.buttonStyle(.borderedProminent).tint(BoardStyle.blue).disabled(updating || (!receiving && !hasDestination))
                if !receiving {
                Button(automatic ? "自動同期を停止" : "自動同期を開始") {
                    do {
                        try MacSync.setAutomaticSync(!automatic)
                        automatic = MacSync.automaticSyncEnabled()
                        message = nil
                    } catch { message = "自動同期を変更できませんでした。" }
                }.buttonStyle(.bordered).disabled(!hasDestination)
                }
                Spacer()
            }

            VStack(alignment: .leading, spacing: 11) {
                Label(receiving ? "iCloudの共有データを表示中" : (automatic ? "15分ごとに同期中" : "自動同期は停止中"), systemImage: automatic ? "checkmark.circle" : "clock")
                    .foregroundStyle(automatic ? BoardStyle.blue : BoardStyle.muted)
                Text("デスクトップを右クリック → ウィジェットを編集 →「AI Usage」を追加。")
                    .fixedSize(horizontal: false, vertical: true)
                Text("iPhoneでは、iCloud Drive → AI Usage → usage.json を選んでください。")
                    .fixedSize(horizontal: false, vertical: true)
                Button("iCloudの同期ファイルを表示") {
                    NSWorkspace.shared.activateFileViewerSelecting([MacSync.exportURL])
                }.buttonStyle(.link)
            }
            .font(.system(size: 12)).foregroundStyle(BoardStyle.muted)

            if let message {
                Label(message, systemImage: "exclamationmark.circle").font(.system(size: 12)).foregroundStyle(.orange)
            } else if snapshot.claude.status == "disconnected" {
                Text("Claudeは未接続です。Claude Codeでログインしてから同期してください。")
                    .font(.system(size: 11)).foregroundStyle(BoardStyle.muted)
            }
        }
        .padding(26).frame(width: 430)
        .background(Color(red: 0.055, green: 0.065, blue: 0.065))
        .task { if receiving { refresh() } }
    }

    private func chooseSource() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.allowedContentTypes = [.json]
        panel.directoryURL = MacSync.exportURL.deletingLastPathComponent()
        panel.message = "取得するMacが保存したJSONファイルを選んでください。"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            snapshot = try UsageStore.select(url)
            receiving = true
            message = nil
            WidgetCenter.shared.reloadAllTimelines()
        } catch { message = "受信ファイルを設定できませんでした。" }
    }

    private func refresh() {
        guard !updating else { return }
        updating = true
        Task {
            do {
                let receive = receiving
                snapshot = try await Task.detached {
                    try receive ? UsageStore.refresh() : MacSync.synchronize()
                }.value
                message = nil
                WidgetCenter.shared.reloadAllTimelines()
            } catch { message = "同期できませんでした。iCloud DriveとCodexのログインを確認してください。" }
            updating = false
        }
    }
}
#endif
