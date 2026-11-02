import Foundation

struct UsageWindow: Codable, Identifiable {
    let id: String
    let label: String
    let remainingPercent: Double
    let resetsAt: Date?
    let resetLabel: String?

    func remaining(at date: Date) -> Double? {
        guard resetsAt.map({ $0 > date }) ?? true else { return nil }
        return remainingPercent
    }
}

struct ProviderUsage: Codable, Identifiable {
    let id: String
    let name: String
    let status: String
    let measuredAt: Date?
    let windows: [UsageWindow]
    let credits: String?
    let message: String?

    func window(_ id: String) -> UsageWindow? { windows.first { $0.id == id } }
    func isStale(at date: Date) -> Bool {
        status == "stale" || measuredAt.map { date.timeIntervalSince($0) > 1_800 } == true
    }

    static func disconnected(_ id: String, name: String) -> ProviderUsage {
        ProviderUsage(id: id, name: name, status: "disconnected", measuredAt: nil,
                      windows: [], credits: nil, message: "未接続")
    }
}

struct UsageSnapshot: Codable {
    let schemaVersion: Int
    let generatedAt: Date
    let providers: [ProviderUsage]

    var codex: ProviderUsage { providers.first { $0.id == "codex" } ?? .disconnected("codex", name: "Codex") }
    var claude: ProviderUsage { providers.first { $0.id == "claude" } ?? .disconnected("claude", name: "Claude") }

    static let empty = UsageSnapshot(schemaVersion: 1, generatedAt: .distantPast, providers: [])

    static func decode(_ data: Data) throws -> UsageSnapshot {
        guard data.count <= 131_072 else { throw UsageError.invalidFile }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let snapshot = try decoder.decode(Self.self, from: data)
        guard snapshot.schemaVersion == 1,
              snapshot.generatedAt <= Date().addingTimeInterval(300),
              snapshot.providers.count <= 2,
              Set(snapshot.providers.map(\.id)).count == snapshot.providers.count else {
            throw UsageError.invalidFile
        }
        for provider in snapshot.providers {
            guard ["codex", "claude"].contains(provider.id),
                  ["connected", "disconnected", "stale", "error"].contains(provider.status),
                  provider.windows.count <= 8,
                  provider.name.count <= 32,
                  provider.message.map({ $0.count <= 256 }) ?? true,
                  provider.measuredAt.map({ $0 <= Date().addingTimeInterval(300) }) ?? true,
                  provider.credits.map({ Decimal(string: $0, locale: Locale(identifier: "en_US_POSIX")) != nil }) ?? true,
                  Set(provider.windows.map(\.id)).count == provider.windows.count else {
                throw UsageError.invalidFile
            }
            for window in provider.windows {
                guard window.remainingPercent.isFinite,
                      (0...100).contains(window.remainingPercent),
                      window.label.count <= 48,
                      window.resetLabel.map({ $0.count <= 96 }) ?? true else { throw UsageError.invalidFile }
            }
        }
        return snapshot
    }
}

enum UsageError: LocalizedError {
    case invalidFile, sharedContainerUnavailable

    var errorDescription: String? {
        switch self {
        case .invalidFile: "残量データを読み込めませんでした。Macで同期をやり直してください。"
        case .sharedContainerUnavailable: "共有領域に接続できません。アプリとウィジェットのApp Groups設定を確認してください。"
        }
    }
}
