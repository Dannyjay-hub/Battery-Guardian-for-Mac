import Foundation

/// Result of a forensic scan — verdict, score, log entries, and metrics.
struct ScanResult {
    let log: [LogEntry]
    let score: Int
    let healthScore: Int
    let verdict: Verdict
    let metrics: Metrics
    let trends: Trends
    let policyVersion: String
    let gaugeProfile: String?
    let evidenceComplete: Bool
    let missingFields: [String]
}

/// Individual forensic check result
struct LogEntry: Identifiable {
    let id = UUID()
    let title: String
    let desc: String
    let status: CheckStatus
}

enum CheckStatus: String {
    case success
    case fail
    case warning
    case info
}

enum Verdict: String {
    case noAnomalies = "NO_ANOMALIES"
    case suspicious = "SUSPICIOUS"
    case spoofed = "SPOOFED"
    case insufficientEvidence = "INSUFFICIENT_EVIDENCE"
    case error = "ERROR"
    case analyzing = "ANALYZING..."

    var displayName: String {
        rawValue.replacingOccurrences(of: "_", with: " ")
    }
}

/// UI metric card values
struct Metrics {
    var cycleCount: String = "--"
    var health: String = "--"
    var qmaxVariance: String = "--"
    var ratio: String = "--"
    var temperature: String = "--"
    var manufactureDate: String = "--"
    var serial: String = "--"

    static let empty = Metrics()

    init() {}

    init(from data: BatteryData) {
        if let c = data.cycleCount { cycleCount = "\(c)" }
        if let h = data.healthPercent { health = "\(h)%" }
        if let q = data.qmax, q.count >= 3 {
            let variance = (q.max() ?? 0) - (q.min() ?? 0)
            qmaxVariance = "\(variance)"
        }
        if let dfw = data.dataFlashWriteCount, let c = data.cycleCount, c > 0 {
            let r = Double(dfw) / Double(c)
            ratio = String(format: "%.1f", r)
        }
        if let tc = data.temperatureCelsius {
            temperature = String(format: "%.0f°C", tc)
        }
        if let md = data.manufactureDate { manufactureDate = md }
        if let s = data.serial { serial = s }
    }
}

/// Trend directions for metric cards
struct Trends {
    var cycles: TrendDirection?
    var health: TrendDirection?
    var opTime: TrendDirection?

    static let empty = Trends()
}

enum TrendDirection: String {
    case up, down, stable, frozen
}

enum ScanStatus {
    case idle
    case running
    case complete
}
