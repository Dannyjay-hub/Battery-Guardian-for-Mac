import Foundation

/// Raw battery data read from IOKit.
/// Mirrors the Python `parse_ioreg()` output — uses optional accessors
/// so checks branch on data availability, never on chip type.
struct BatteryData {
    /// Raw top-level properties from AppleSmartBattery
    let topLevel: [String: Any]
    /// Nested BatteryData dictionary (contains TI gauge registers)
    let batteryData: [String: Any]
    /// Nested LifetimeData dictionary (inside BatteryData)
    let lifetimeData: [String: Any]

    // ── Core metrics (top-level) ────────────────────────────────────────

    var cycleCount: Int? { topLevel["CycleCount"] as? Int }
    var appleRawMaxCapacity: Int? { topLevel["AppleRawMaxCapacity"] as? Int }
    var temperature: Int? { topLevel["Temperature"] as? Int }
    var voltage: Int? { topLevel["Voltage"] as? Int }
    var serial: String? { topLevel["Serial"] as? String }
    var deviceName: String? { topLevel["DeviceName"] as? String }
    var isCharging: Bool { (topLevel["IsCharging"] as? Int ?? 0) != 0 }
    var externalConnected: Bool { (topLevel["ExternalConnected"] as? Int ?? 0) != 0 }
    var fullyCharged: Bool { (topLevel["FullyCharged"] as? Int ?? 0) != 0 }
    var permanentFailureStatus: Int? { topLevel["PermanentFailureStatus"] as? Int }

    // ── TI gauge registers (inside BatteryData) ─────────────────────────

    var designCapacity: Int? {
        batteryData["DesignCapacity"] as? Int ?? topLevel["DesignCapacity"] as? Int
    }
    var maxCapacity: Int? {
        batteryData["MaxCapacity"] as? Int ?? topLevel["MaxCapacity"] as? Int
    }
    // IOKit returns these arrays as [NSNumber], not [Int] — must map explicitly
    var qmax: [Int]? {
        (batteryData["Qmax"] as? [NSNumber])?.map { $0.intValue }
    }
    var dod0: [Int]? {
        (batteryData["DOD0"] as? [NSNumber])?.map { $0.intValue }
    }
    var cellVoltage: [Int]? {
        (batteryData["CellVoltage"] as? [NSNumber])?.map { $0.intValue }
    }
    var dataFlashWriteCount: Int? { batteryData["DataFlashWriteCount"] as? Int }
    var chemID: Int? { batteryData["ChemID"] as? Int }
    var fccComp1: Int? { batteryData["FccComp1"] as? Int }
    var fccComp2: Int? { batteryData["FccComp2"] as? Int }

    // ── Lifetime data (inside BatteryData → LifetimeData) ───────────────

    var totalOperatingTime: Int? { lifetimeData["TotalOperatingTime"] as? Int }
    var temperatureSamples: Int? { lifetimeData["TemperatureSamples"] as? Int }
    var cycleCountLastQmax: Int? { lifetimeData["CycleCountLastQmax"] as? Int }
    var maximumPackVoltage: Int? { lifetimeData["MaximumPackVoltage"] as? Int }
    var maximumChargeCurrent: Int? { lifetimeData["MaximumChargeCurrent"] as? Int }
    var minimumPackVoltage: Int? { lifetimeData["MinimumPackVoltage"] as? Int }
    var averageTemperature: Int? { lifetimeData["AverageTemperature"] as? Int }

    // ── Computed helpers ────────────────────────────────────────────────

    /// Battery health percentage (AppleRawMaxCapacity / DesignCapacity)
    var healthPercent: Int? {
        guard let raw = appleRawMaxCapacity, let design = designCapacity, design > 0 else {
            return nil
        }
        return Int(round(Double(raw) / Double(design) * 100))
    }

    /// Temperature in Celsius.
    /// IOKit Temperature is in deciKelvin (units of 0.1K).
    /// Verified: 3164 / 10 - 273.15 = 43.25°C — matches CoconutBattery's 43.5°C.
    /// The Python and Swift implementations both use this conversion.
    var temperatureCelsius: Double? {
        guard let t = temperature else { return nil }
        return Double(t) / 10.0 - 273.15
    }

    /// Actual SBS manufacture date when it has been read and decoded.
    /// TotalOperatingTime is powered-on time and must not be presented as a
    /// calendar manufacture date.
    var manufactureDate: String? {
        batteryData["SBSManufactureDate"] as? String
    }
}

enum BatteryError: Error, LocalizedError {
    case noBattery
    case readFailed

    var errorDescription: String? {
        switch self {
        case .noBattery: return "No battery detected. This Mac may not have a built-in battery."
        case .readFailed: return "Failed to read battery data from IOKit."
        }
    }
}
