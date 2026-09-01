import Foundation

let SCORE_CLOCK_INTEGRITY = 50
let SCORE_CALIBRATION_PARADOX = 50
let SCORE_THRESHOLD_SPOOFED = 40

private struct ForensicContract: Decodable {
    let policyVersion: String
    let spoofedScoreThreshold: Int
    let profiles: [String: GaugeProfile]
    let checks: [String: ContractCheck]

    enum CodingKeys: String, CodingKey {
        case policyVersion = "policy_version"
        case spoofedScoreThreshold = "spoofed_score_threshold"
        case profiles, checks
    }

    static func load() throws -> ForensicContract {
        let candidates = [
            Bundle.main.url(forResource: "contract", withExtension: "json"),
            Bundle(for: ContractBundleToken.self).url(forResource: "contract", withExtension: "json")
        ]
        guard let url = candidates.compactMap({ $0 }).first else {
            throw ContractError.missingResource
        }
        return try JSONDecoder().decode(ForensicContract.self, from: Data(contentsOf: url))
    }
}

private final class ContractBundleToken {}

private enum ContractError: LocalizedError {
    case missingResource

    var errorDescription: String? {
        "The versioned forensic contract is missing from the application bundle."
    }
}

private struct GaugeProfile: Decodable {
    let familyAnalogue: String
    let evidenceLevel: String
    let minimumFields: [String]
    let cellCount: Int
    let activeChecks: [String]

    enum CodingKeys: String, CodingKey {
        case familyAnalogue = "family_analogue"
        case evidenceLevel = "evidence_level"
        case minimumFields = "minimum_fields"
        case cellCount = "cell_count"
        case activeChecks = "active_checks"
    }
}

private struct ContractCheck: Decodable {
    let mode: String
    let score: Int?
    let evidenceLevel: String?
    let minimumCycles: Int?
    let dod0Value: Int?
    let dataflashWriteCount: Int?
    let minimumTemperatureSamples: Int?
    let passDifferencePercent: Double?
    let failDifferencePercent: Double?
    let secondsPerTemperatureSample: Double?

    enum CodingKeys: String, CodingKey {
        case mode, score
        case evidenceLevel = "evidence_level"
        case minimumCycles = "minimum_cycles"
        case dod0Value = "dod0_value"
        case dataflashWriteCount = "dataflash_write_count"
        case minimumTemperatureSamples = "minimum_temperature_samples"
        case passDifferencePercent = "pass_difference_percent"
        case failDifferencePercent = "fail_difference_percent"
        case secondsPerTemperatureSample = "seconds_per_temperature_sample"
    }
}

struct ForensicEngine {
    static func analyze(_ data: BatteryData, lastScan: HistoryEntry?) -> ScanResult {
        let contract: ForensicContract
        do {
            contract = try ForensicContract.load()
        } catch {
            return ScanResult(
                log: [LogEntry(title: "Forensic Contract Error", desc: error.localizedDescription, status: .fail)],
                score: 0,
                healthScore: 0,
                verdict: .error,
                metrics: Metrics(from: data),
                trends: computeTrends(data, lastScan: lastScan),
                policyVersion: "--",
                gaugeProfile: data.deviceName,
                evidenceComplete: false,
                missingFields: []
            )
        }

        guard let deviceName = data.deviceName,
              let profile = contract.profiles[deviceName]
        else {
            return result(
                data: data,
                lastScan: lastScan,
                log: [LogEntry(
                    title: "Unsupported or Unidentified Gauge",
                    desc: "Battery Guardian cannot select a validated gauge profile for this telemetry.",
                    status: .warning
                )],
                score: 0,
                verdict: .insufficientEvidence,
                contract: contract,
                profile: data.deviceName,
                complete: false,
                missing: data.deviceName == nil ? ["DeviceName"] : []
            )
        }

        let missing = profile.minimumFields.filter { !hasField($0, in: data) }
        var log: [LogEntry] = []
        var score = 0

        if !missing.isEmpty {
            log.append(LogEntry(
                title: "Insufficient Forensic Evidence",
                desc: "Required fields are missing: \(missing.joined(separator: ", ")). No authenticity conclusion was made.",
                status: .warning
            ))
        }

        let active = Set(profile.activeChecks)

        if active.contains("bq20z451_reset_signature"),
           let rule = contract.checks["bq20z451_reset_signature"],
           let cycles = data.cycleCount,
           let dod0 = data.dod0,
           let writes = data.dataFlashWriteCount,
           dod0.count == profile.cellCount,
           cycles > (rule.minimumCycles ?? Int.max),
           dod0.allSatisfy({ $0 == rule.dod0Value }),
           writes == rule.dataflashWriteCount {
            let points = rule.score ?? 0
            score += points
            log.append(LogEntry(
                title: "Model-Specific Reset Signature Detected",
                desc: "The bq20z451 reports \(cycles) cycles while all DOD0 cells remain at \(rule.dod0Value ?? 0) and DataFlashWriteCount is zero. This is a strong empirical reset/replacement signature, not a cryptographic provenance test.",
                status: .fail
            ))
        }

        if active.contains("calibration_timeline"),
           let lastQmax = data.cycleCountLastQmax,
           let cycles = data.cycleCount,
           let rule = contract.checks["calibration_timeline"] {
            if lastQmax > cycles {
                score += rule.score ?? 0
                log.append(LogEntry(
                    title: "Calibration Timeline Contradiction",
                    desc: "Last Qmax update cycle \(lastQmax) exceeds current cycle count \(cycles).",
                    status: .fail
                ))
            } else {
                log.append(LogEntry(
                    title: "Calibration Timeline Consistent",
                    desc: "Last Qmax update cycle \(lastQmax) does not exceed current cycle count \(cycles).",
                    status: .success
                ))
            }
        }

        if active.contains("clock_integrity"),
           let samples = data.temperatureSamples,
           let hours = data.totalOperatingTime,
           hours > 0,
           let rule = contract.checks["clock_integrity"],
           samples >= (rule.minimumTemperatureSamples ?? Int.max),
           let secondsPerSample = rule.secondsPerTemperatureSample {
            let impliedHours = Double(samples) * secondsPerSample / 3600
            let difference = abs(impliedHours - Double(hours)) / max(impliedHours, Double(hours)) * 100
            if difference >= (rule.failDifferencePercent ?? .infinity) {
                score += rule.score ?? 0
                log.append(LogEntry(
                    title: "Lifetime Counters Contradict Each Other",
                    desc: "The two counters differ by \(String(format: "%.1f", difference))%, above the model policy threshold.",
                    status: .fail
                ))
            } else if difference < (rule.passDifferencePercent ?? 0) {
                log.append(LogEntry(
                    title: "Lifetime Counters Agree",
                    desc: "The two counters agree within \(String(format: "%.2f", difference))%.",
                    status: .success
                ))
            } else {
                log.append(LogEntry(
                    title: "Lifetime Counters Need Review",
                    desc: "The two counters differ by \(String(format: "%.1f", difference))%, within the policy review band.",
                    status: .warning
                ))
            }
        }

        let verdict: Verdict
        if score >= contract.spoofedScoreThreshold {
            verdict = .spoofed
        } else if score > 0 {
            verdict = .suspicious
        } else if !missing.isEmpty {
            verdict = .insufficientEvidence
        } else {
            verdict = .noAnomalies
            log.append(LogEntry(
                title: "No Supported Anomaly Detected",
                desc: "The available supported checks found no contradiction. This does not prove Apple originality.",
                status: .info
            ))
        }

        return result(
            data: data,
            lastScan: lastScan,
            log: log,
            score: score,
            verdict: verdict,
            contract: contract,
            profile: deviceName,
            complete: missing.isEmpty,
            missing: missing
        )
    }

    private static func result(
        data: BatteryData,
        lastScan: HistoryEntry?,
        log: [LogEntry],
        score: Int,
        verdict: Verdict,
        contract: ForensicContract,
        profile: String?,
        complete: Bool,
        missing: [String]
    ) -> ScanResult {
        ScanResult(
            log: log,
            score: score,
            healthScore: computeHealthScore(data, scanScore: score),
            verdict: verdict,
            metrics: Metrics(from: data),
            trends: computeTrends(data, lastScan: lastScan),
            policyVersion: contract.policyVersion,
            gaugeProfile: profile,
            evidenceComplete: complete,
            missingFields: missing
        )
    }

    private static func hasField(_ name: String, in data: BatteryData) -> Bool {
        switch name {
        case "DeviceName": return !(data.deviceName ?? "").isEmpty
        case "CycleCount": return data.cycleCount != nil
        case "DesignCapacity": return data.designCapacity != nil
        case "Qmax": return !(data.qmax ?? []).isEmpty
        case "DOD0": return !(data.dod0 ?? []).isEmpty
        case "DataFlashWriteCount": return data.dataFlashWriteCount != nil
        case "TotalOperatingTime": return data.totalOperatingTime != nil
        case "TemperatureSamples": return data.temperatureSamples != nil
        case "CycleCountLastQmax": return data.cycleCountLastQmax != nil
        case "MaximumPackVoltage": return data.maximumPackVoltage != nil
        default: return false
        }
    }

    static func computeHealthScore(_ data: BatteryData, scanScore: Int) -> Int {
        var score = 100 - min(scanScore, 80)
        if let capacity = data.appleRawMaxCapacity, let design = data.designCapacity, design > 0 {
            let health = Double(capacity) / Double(design) * 100
            if health < 80 { score -= Int((80 - health) * 0.5) }
        }
        let cycles = data.cycleCount ?? 0
        if cycles > 1000 {
            score -= min((cycles - 1000) / 50, 15)
        } else if cycles > 500 {
            score -= min((cycles - 500) / 100, 5)
        }
        return max(0, min(100, score))
    }

    static func computeTrends(_ data: BatteryData, lastScan: HistoryEntry?) -> Trends {
        var trends = Trends()
        guard let previous = lastScan else { return trends }

        if let cycles = data.cycleCount {
            trends.cycles = cycles > previous.cycleCount ? .up : cycles == previous.cycleCount ? .stable : nil
        }
        if let capacity = data.appleRawMaxCapacity, let previousCapacity = previous.appleRawMaxCapacity {
            trends.health = capacity > previousCapacity ? .up : capacity < previousCapacity ? .down : .stable
        }
        if let hours = data.totalOperatingTime, let previousHours = previous.totalOperatingTime {
            trends.opTime = hours > previousHours ? .up : .stable
        }
        return trends
    }
}
