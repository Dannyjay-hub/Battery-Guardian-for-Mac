import Foundation

/// Manages scan history — same file path as Python version for compatibility.
final class HistoryManager: Sendable {
    static let shared = HistoryManager()

    private let filePath: URL

    private init() {
        filePath = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".battery_guardian_log.json")
    }

    /// Save a scan result to history
    func save(data: BatteryData, result: ScanResult) {
        let entry = HistoryEntry(data: data, result: result)
        var entries = loadAll()
        entries.append(entry)

        do {
            try backupLegacyHistoryIfNeeded()
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            let jsonData = try encoder.encode(entries)
            try jsonData.write(to: filePath, options: .atomic)
        } catch {
            print("Failed to save history: \(error)")
        }
    }

    /// Get the most recent scan entry
    func lastScan() -> HistoryEntry? {
        return loadAll().last
    }

    /// Load all scan history
    func loadAll() -> [HistoryEntry] {
        guard FileManager.default.fileExists(atPath: filePath.path) else {
            return []
        }
        do {
            let data = try Data(contentsOf: filePath)
            if let objects = try JSONSerialization.jsonObject(with: data) as? [[String: Any]],
               objects.contains(where: { $0["parsed"] != nil }) {
                return objects.compactMap(HistoryEntry.init(legacyObject:))
            }
            guard let current = try? JSONDecoder().decode([HistoryEntry].self, from: data) else {
                return []
            }
            return current
        } catch {
            print("Failed to load history: \(error)")
            return []
        }
    }

    /// Preserve the complete Python file before its first normalized v2 write.
    /// The backup retains fields that the native trend schema does not consume.
    private func backupLegacyHistoryIfNeeded() throws {
        guard FileManager.default.fileExists(atPath: filePath.path) else { return }
        let existing = try Data(contentsOf: filePath)
        guard let objects = try JSONSerialization.jsonObject(with: existing) as? [[String: Any]],
              objects.contains(where: { $0["parsed"] != nil }) else { return }

        let backup = filePath.deletingLastPathComponent()
            .appendingPathComponent(".battery_guardian_log.python-v1.backup.json")
        if !FileManager.default.fileExists(atPath: backup.path) {
            try existing.write(to: backup, options: [.atomic])
        }
    }

    /// Export history to Desktop
    func exportToDesktop() -> (success: Bool, message: String) {
        let dateStr = DateFormatter.localizedString(from: Date(), dateStyle: .short, timeStyle: .none)
            .replacingOccurrences(of: "/", with: "-")
        let exportPath = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Desktop")
            .appendingPathComponent("BatteryGuardian_History_\(dateStr).json")

        do {
            let entries = loadAll()
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted]
            let data = try encoder.encode(entries)
            try data.write(to: exportPath, options: .atomic)
            return (true, exportPath.path)
        } catch {
            return (false, error.localizedDescription)
        }
    }
}
