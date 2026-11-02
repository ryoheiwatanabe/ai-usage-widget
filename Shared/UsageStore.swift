import Foundation

enum UsageStore {
    static let groupID: String = {
        guard let identifier = Bundle.main.object(forInfoDictionaryKey: "AIUsageAppGroupIdentifier") as? String,
              !identifier.isEmpty else {
            preconditionFailure("AIUsageAppGroupIdentifier is missing from the app's Info.plist.")
        }
        return identifier
    }()
    private static let bookmarkKey = "usageSourceBookmark"

    private static func cacheURL() throws -> URL {
        guard let directory = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: groupID) else {
            throw UsageError.sharedContainerUnavailable
        }
        return directory.appendingPathComponent("usage.json")
    }

    static var hasSource: Bool { UserDefaults(suiteName: groupID)?.data(forKey: bookmarkKey) != nil }

    static func cached() -> UsageSnapshot {
        guard let url = try? cacheURL(), let data = try? Data(contentsOf: url),
              let snapshot = try? UsageSnapshot.decode(data) else { return .empty }
        return snapshot
    }

    static func select(_ url: URL) throws -> UsageSnapshot {
        let accessing = url.startAccessingSecurityScopedResource()
        defer { if accessing { url.stopAccessingSecurityScopedResource() } }
        let snapshot = try readAndCache(url)
        let bookmark = try url.bookmarkData(options: [], includingResourceValuesForKeys: nil, relativeTo: nil)
        UserDefaults(suiteName: groupID)?.set(bookmark, forKey: bookmarkKey)
        return snapshot
    }

    static func refresh() throws -> UsageSnapshot {
        #if os(macOS)
        return cached()
        #else
        guard let bookmark = UserDefaults(suiteName: groupID)?.data(forKey: bookmarkKey) else { return cached() }
        var stale = false
        let url = try URL(resolvingBookmarkData: bookmark, options: [.withoutUI], relativeTo: nil, bookmarkDataIsStale: &stale)
        let accessing = url.startAccessingSecurityScopedResource()
        defer { if accessing { url.stopAccessingSecurityScopedResource() } }
        if (try? url.resourceValues(forKeys: [.isUbiquitousItemKey]).isUbiquitousItem) == true {
            try FileManager.default.startDownloadingUbiquitousItem(at: url)
        }
        let snapshot = try readAndCache(url)
        if stale {
            let renewed = try url.bookmarkData(options: [], includingResourceValuesForKeys: nil, relativeTo: nil)
            UserDefaults(suiteName: groupID)?.set(renewed, forKey: bookmarkKey)
        }
        return snapshot
        #endif
    }

    private static func readAndCache(_ url: URL) throws -> UsageSnapshot {
        var coordinationError: NSError?
        var readResult: Result<Data, Error>?
        NSFileCoordinator().coordinate(readingItemAt: url, options: [], error: &coordinationError) { source in
            readResult = Result {
                let fileSize = try source.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
                guard fileSize <= 131_072 else { throw UsageError.invalidFile }
                return try Data(contentsOf: source)
            }
        }
        if let coordinationError { throw coordinationError }
        guard let readResult else { throw UsageError.invalidFile }
        let data = try readResult.get()
        return try store(data)
    }

    static func store(_ data: Data) throws -> UsageSnapshot {
        let snapshot = try UsageSnapshot.decode(data)
        #if os(macOS)
        try data.write(to: cacheURL(), options: [.atomic])
        #else
        try data.write(to: cacheURL(), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        #endif
        return snapshot
    }
}
