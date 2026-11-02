import SwiftUI
import UniformTypeIdentifiers
import WidgetKit

@main
struct AIUsageApp: App {
    init() {
        #if os(macOS)
        if ProcessInfo.processInfo.arguments.contains("--sync") {
            do {
                _ = try MacSync.synchronize()
                WidgetCenter.shared.reloadAllTimelines()
                exit(0)
            } catch {
                fputs("残量の同期に失敗しました。アプリを開いて確認してください。\n", stderr)
                exit(1)
            }
        }
        #endif
    }

    var body: some Scene {
        #if os(macOS)
        WindowGroup("AI Usage") { MacBoardScreen().preferredColorScheme(.dark) }
            .windowResizability(.contentSize)
        #else
        WindowGroup { BoardScreen().preferredColorScheme(.dark) }
        #endif
    }
}

#if !os(macOS)
struct BoardScreen: View {
    @Environment(\.scenePhase) private var scenePhase
    @State private var snapshot = UsageStore.cached()
    @State private var choosingFile = false
    @State private var updating = false
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 28) {
                    VStack(alignment: .leading, spacing: 9) {
                        Text("AI USAGE").font(.system(size: 11, weight: .semibold, design: .monospaced))
                            .tracking(3).foregroundStyle(BoardStyle.muted)
                        Text("Codex と Claude").font(.system(size: 31, weight: .bold))
                        Text("5時間・週間の残量とクレジット。")
                            .font(.system(size: 14)).foregroundStyle(BoardStyle.muted)
                    }
                    .padding(.top, 24)

                    UsageCard(snapshot: snapshot, syncFailed: errorMessage != nil)
                        .frame(height: 184)
                        .shadow(color: .black.opacity(0.3), radius: 20, y: 12)

                    VStack(alignment: .leading, spacing: 18) {
                        Label("Macの残量をiCloudで受け取る", systemImage: "icloud")
                            .font(.system(size: 16, weight: .semibold))
                        Text("Macで作成した usage.json を1回選ぶと、ウィジェットが更新を確認します。")
                            .font(.system(size: 14)).foregroundStyle(BoardStyle.muted)
                            .fixedSize(horizontal: false, vertical: true)

                        Button { choosingFile = true } label: {
                            Label(UsageStore.hasSource ? "同期ファイルを変更" : "iCloudのファイルを選ぶ", systemImage: "folder")
                                .frame(maxWidth: .infinity).padding(.vertical, 8)
                        }
                        .buttonStyle(.borderedProminent).tint(BoardStyle.blue)
                        .foregroundStyle(.black)

                        if UsageStore.hasSource {
                            Button { refresh() } label: {
                                HStack {
                                    if updating { ProgressView().controlSize(.small) }
                                    Label("今すぐ確認", systemImage: "arrow.clockwise")
                                }.frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.bordered).disabled(updating)
                        }
                    }
                    .padding(20)
                    .background(.white.opacity(0.04), in: RoundedRectangle(cornerRadius: 22))

                    VStack(alignment: .leading, spacing: 12) {
                        Label("ホーム画面に追加", systemImage: "plus.square.on.square")
                            .font(.system(size: 16, weight: .semibold))
                        Text("ホーム画面を長押し → 編集 → ウィジェットを追加 →「AI Usage」→ 中サイズを追加。")
                            .font(.system(size: 14)).foregroundStyle(BoardStyle.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }.padding(.horizontal, 4)

                    if let errorMessage {
                        Label(errorMessage, systemImage: "exclamationmark.circle")
                            .font(.system(size: 13)).foregroundStyle(.orange)
                    }
                    if snapshot.claude.status == "disconnected" {
                        Text("Claudeは未接続です。MacでClaude Codeにログインしてから同期してください。")
                            .font(.system(size: 12)).foregroundStyle(BoardStyle.muted)
                    }
                    Text("更新時刻は取得できた時点のものです。ウィジェットの更新間隔はiOSが調整します。")
                        .font(.system(size: 12)).foregroundStyle(BoardStyle.muted)
                }
                .padding(.horizontal, 22).padding(.bottom, 32)
            }
            .background(Color(red: 0.055, green: 0.065, blue: 0.065))
            .toolbar { ToolbarItem(placement: .topBarTrailing) {
                Image(systemName: "square.grid.2x2.fill").foregroundStyle(BoardStyle.blue)
            } }
        }
        .fileImporter(isPresented: $choosingFile, allowedContentTypes: [.json]) { result in
            switch result {
            case .success(let url):
                updating = true
                Task {
                    do {
                        snapshot = try await Task.detached { try UsageStore.select(url) }.value
                        errorMessage = nil
                        WidgetCenter.shared.reloadAllTimelines()
                    } catch { errorMessage = error.localizedDescription }
                    updating = false
                }
            case .failure(let error): errorMessage = error.localizedDescription
            }
        }
        .onChange(of: scenePhase) { _, phase in if phase == .active { refresh() } }
        .task { refresh() }
    }

    private func refresh() {
        guard !updating else { return }
        updating = true
        Task {
            do {
                snapshot = try await Task.detached { try UsageStore.refresh() }.value
                errorMessage = nil
                WidgetCenter.shared.reloadAllTimelines()
            } catch { errorMessage = "同期を確認できませんでした。前回の残量を表示しています。" }
            updating = false
        }
    }
}
#endif
