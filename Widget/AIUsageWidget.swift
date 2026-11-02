import SwiftUI
import WidgetKit

struct BoardEntry: TimelineEntry {
    let date: Date
    let snapshot: UsageSnapshot
    let syncFailed: Bool
}

struct BoardProvider: TimelineProvider {
    func placeholder(in context: Context) -> BoardEntry {
        BoardEntry(date: Date(), snapshot: .empty, syncFailed: false)
    }

    func getSnapshot(in context: Context, completion: @escaping (BoardEntry) -> Void) {
        completion(BoardEntry(date: Date(), snapshot: UsageStore.cached(), syncFailed: false))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<BoardEntry>) -> Void) {
        DispatchQueue.global(qos: .utility).async {
            let snapshot: UsageSnapshot
            let syncFailed: Bool
            do { snapshot = try UsageStore.refresh(); syncFailed = false }
            catch { snapshot = UsageStore.cached(); syncFailed = true }
            let now = Date()
            let nextRefresh = now.addingTimeInterval(900)
            var dates = [now]
            let boundaries = snapshot.providers.flatMap { $0.windows.compactMap(\.resetsAt) }
                + snapshot.providers.compactMap { $0.measuredAt?.addingTimeInterval(1_800) }
            dates.append(contentsOf: boundaries.filter { $0 > now && $0 < nextRefresh })
            let entries = Set(dates).sorted().map { BoardEntry(date: $0, snapshot: snapshot, syncFailed: syncFailed) }
            completion(Timeline(entries: entries, policy: .after(nextRefresh)))
        }
    }
}

@main
struct AIUsageWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "AIUsageBoard", provider: BoardProvider()) { entry in
            UsageCard(snapshot: entry.snapshot, date: entry.date, syncFailed: entry.syncFailed)
                .containerBackground(for: .widget) { BoardStyle.background }
        }
        .configurationDisplayName("Codex と Claude")
        .description("5時間・週間の残量とCodexクレジットをまとめて確認。")
        .supportedFamilies([.systemMedium])
        .contentMarginsDisabled()
    }
}
