import Foundation

/// A single saved scan entry — compatible with the Python version's JSON format.
/// Uses custom CodingKeys to match the Python field names exactly.
struct HistoryEntry: Codable {
    let timestamp: String
    let cycleCount: Int
    let healthScore: Int
    let verdict: String
    let appleRawMaxCapacity: Int?
    let totalOperatingTime: Int?

    enum CodingKeys: String, CodingKey {
        case timestamp
        case cycleCount = "cycle_count"
        case healthScore = "health_score"
        case verdict
        case appleRawMaxCapacity = "apple_raw_max_capacity"
        case totalOperatingTime = "total_operating_time"
    }

    /// Create from current scan data
    init(data: BatteryData, result: ScanResult) {
        self.timestamp = ISO8601DateFormatter().string(from: Date())
        self.cycleCount = data.cycleCount ?? 0
        self.healthScore = result.healthScore
        self.verdict = result.verdict.rawValue
        self.appleRawMaxCapacity = data.appleRawMaxCapacity
        self.totalOperatingTime = data.totalOperatingTime
    }

    /// Migrate the Python v1 history object. Python stored capacity and
    /// operating-time values inside a nested `parsed` dictionary.
    init?(legacyObject: [String: Any]) {
        guard let timestamp = legacyObject["timestamp"] as? String else { return nil }
        let parsed = legacyObject["parsed"] as? [String: Any] ?? [:]
        self.timestamp = timestamp
        self.cycleCount = Self.int(legacyObject["cycle_count"]) ?? Self.int(parsed["CycleCount"]) ?? 0
        self.healthScore = Self.int(legacyObject["health_score"]) ?? 0
        self.verdict = legacyObject["verdict"] as? String ?? "UNKNOWN"
        self.appleRawMaxCapacity = Self.int(parsed["AppleRawMaxCapacity"])
        self.totalOperatingTime = Self.int(parsed["TotalOperatingTime"])
    }

    /// Decode from JSON
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        timestamp = try c.decode(String.self, forKey: .timestamp)
        cycleCount = try c.decodeIfPresent(Int.self, forKey: .cycleCount) ?? 0
        healthScore = try c.decodeIfPresent(Int.self, forKey: .healthScore) ?? 0
        verdict = try c.decodeIfPresent(String.self, forKey: .verdict) ?? "UNKNOWN"
        appleRawMaxCapacity = try c.decodeIfPresent(Int.self, forKey: .appleRawMaxCapacity)
        totalOperatingTime = try c.decodeIfPresent(Int.self, forKey: .totalOperatingTime)
    }

    private static func int(_ value: Any?) -> Int? {
        if let value = value as? Int { return value }
        if let value = value as? NSNumber { return value.intValue }
        return nil
    }
}
