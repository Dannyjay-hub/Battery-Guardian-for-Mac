import XCTest
@testable import BatteryGuardian

final class ForensicEngineTests: XCTestCase {
    func testBq20z451ResetSignatureMatchesPythonFixture() {
        let data = makeBatteryData(
            deviceName: "bq20z451",
            cycles: 29,
            designCap: 4790,
            qmax: [4770, 4790, 4780],
            dod0: [16384, 16384, 16384],
            dataFlashWriteCount: 0,
            totalOpTime: 27309
        )
        let result = ForensicEngine.analyze(data, lastScan: nil)
        XCTAssertEqual(result.verdict, .spoofed)
        XCTAssertEqual(result.score, 55)
        XCTAssertTrue(result.evidenceComplete)
    }

    func testIdenticalNonResetDOD0IsNotFailure() {
        let data = makeBatteryData(
            deviceName: "bq20z451",
            cycles: 919,
            designCap: 7336,
            rawMaxCap: 5923,
            qmax: [7019, 7006, 6998],
            dod0: [2208, 2208, 2208],
            dataFlashWriteCount: 6820,
            totalOpTime: 48647
        )
        let result = ForensicEngine.analyze(data, lastScan: nil)
        XCTAssertEqual(result.verdict, .noAnomalies)
        XCTAssertEqual(result.score, 0)
    }

    func testCompleteBq40z651ControlHasNoSupportedAnomaly() {
        let data = makeBatteryData(
            deviceName: "bq40z651",
            cycles: 127,
            designCap: 8579,
            qmax: [8895, 8901, 8859],
            dod0: [648, 648, 656],
            dataFlashWriteCount: 10160,
            totalOpTime: 19929,
            tempSamples: 318880,
            cycleCountLastQmax: 127,
            maximumPackVoltage: 13161
        )
        let result = ForensicEngine.analyze(data, lastScan: nil)
        XCTAssertEqual(result.verdict, .noAnomalies)
        XCTAssertEqual(result.score, 0)
        XCTAssertTrue(result.evidenceComplete)
    }

    func testPartialKnownGaugeIsInsufficientEvidence() {
        let data = makeBatteryData(
            deviceName: "bq20z451",
            cycles: 1,
            designCap: 8980,
            rawMaxCap: 9062,
            qmax: [8960, 8980, 8970]
        )
        let result = ForensicEngine.analyze(data, lastScan: nil)
        XCTAssertEqual(result.verdict, .insufficientEvidence)
        XCTAssertEqual(Set(result.missingFields), Set(["DOD0", "DataFlashWriteCount"]))
    }

    func testUnknownGaugeIsInsufficientEvidence() {
        let data = makeBatteryData(deviceName: "unknown", cycles: 100)
        let result = ForensicEngine.analyze(data, lastScan: nil)
        XCTAssertEqual(result.verdict, .insufficientEvidence)
        XCTAssertFalse(result.evidenceComplete)
    }

    func testCalibrationTimelineContradictionIsScored() {
        let data = makeBatteryData(
            deviceName: "bq40z651",
            cycles: 50,
            designCap: 8579,
            qmax: [8500, 8490, 8510],
            dod0: [640, 650, 645],
            dataFlashWriteCount: 9000,
            totalOpTime: 1000,
            tempSamples: 16000,
            cycleCountLastQmax: 100,
            maximumPackVoltage: 13000
        )
        let result = ForensicEngine.analyze(data, lastScan: nil)
        XCTAssertEqual(result.verdict, .spoofed)
        XCTAssertEqual(result.score, 50)
    }

    func testTemperatureUsesDeciKelvin() {
        let data = makeBatteryData(deviceName: "bq20z451", cycles: 1, temperature: 3164)
        XCTAssertEqual(data.temperatureCelsius ?? 0, 43.25, accuracy: 0.001)
    }

    func testPythonHistoryMigrationRetainsTrendFields() {
        let legacy: [String: Any] = [
            "timestamp": "2026-08-30T10:00:00",
            "cycle_count": 88,
            "health_score": 91,
            "parsed": [
                "CycleCount": 88,
                "AppleRawMaxCapacity": 4123,
                "TotalOperatingTime": 2222,
            ],
        ]
        let entry = HistoryEntry(legacyObject: legacy)
        XCTAssertEqual(entry?.cycleCount, 88)
        XCTAssertEqual(entry?.appleRawMaxCapacity, 4123)
        XCTAssertEqual(entry?.totalOperatingTime, 2222)
    }

    func testEverySharedFixtureMatchesTheCrossLanguageContract() throws {
        let testFile = URL(fileURLWithPath: #filePath)
        let fixtureDirectory = testFile
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("forensics/fixtures")
        let files = try FileManager.default.contentsOfDirectory(
            at: fixtureDirectory,
            includingPropertiesForKeys: nil
        ).filter { $0.pathExtension == "json" }.sorted { $0.lastPathComponent < $1.lastPathComponent }

        XCTAssertFalse(files.isEmpty)
        for file in files {
            let fixture = try XCTUnwrap(
                JSONSerialization.jsonObject(with: Data(contentsOf: file)) as? [String: Any]
            )
            let flat = try XCTUnwrap(fixture["data"] as? [String: Any])
            let expected = try XCTUnwrap(fixture["expected"] as? [String: Any])
            let result = ForensicEngine.analyze(batteryData(from: flat), lastScan: nil)

            XCTAssertEqual(result.gaugeProfile, expected["profile"] as? String, file.lastPathComponent)
            XCTAssertEqual(result.verdict.rawValue, expected["verdict"] as? String, file.lastPathComponent)
            XCTAssertEqual(result.score, expected["score"] as? Int, file.lastPathComponent)
            XCTAssertEqual(result.evidenceComplete, expected["complete"] as? Bool, file.lastPathComponent)
        }
    }

    private func makeBatteryData(
        deviceName: String,
        cycles: Int,
        designCap: Int = 4382,
        rawMaxCap: Int = 4100,
        qmax: [Int]? = nil,
        dod0: [Int]? = nil,
        dataFlashWriteCount: Int? = nil,
        totalOpTime: Int? = nil,
        tempSamples: Int? = nil,
        cycleCountLastQmax: Int? = nil,
        maximumPackVoltage: Int? = nil,
        temperature: Int = 3100
    ) -> BatteryData {
        let top: [String: Any] = [
            "CycleCount": cycles,
            "AppleRawMaxCapacity": rawMaxCap,
            "Temperature": temperature,
            "Voltage": 12000,
            "Serial": "TEST123",
            "DeviceName": deviceName,
        ]
        var battery: [String: Any] = ["DesignCapacity": designCap]
        if let qmax { battery["Qmax"] = qmax }
        if let dod0 { battery["DOD0"] = dod0 }
        if let dataFlashWriteCount { battery["DataFlashWriteCount"] = dataFlashWriteCount }

        var lifetime: [String: Any] = [:]
        if let totalOpTime { lifetime["TotalOperatingTime"] = totalOpTime }
        if let tempSamples { lifetime["TemperatureSamples"] = tempSamples }
        if let cycleCountLastQmax { lifetime["CycleCountLastQmax"] = cycleCountLastQmax }
        if let maximumPackVoltage { lifetime["MaximumPackVoltage"] = maximumPackVoltage }

        return BatteryData(topLevel: top, batteryData: battery, lifetimeData: lifetime)
    }

    private func batteryData(from flat: [String: Any]) -> BatteryData {
        let topKeys = ["DeviceName", "CycleCount", "AppleRawMaxCapacity", "Temperature", "Voltage", "Serial"]
        let batteryKeys = ["DesignCapacity", "Qmax", "DOD0", "DataFlashWriteCount"]
        let lifetimeKeys = ["TotalOperatingTime", "TemperatureSamples", "CycleCountLastQmax", "MaximumPackVoltage"]

        return BatteryData(
            topLevel: Dictionary(uniqueKeysWithValues: topKeys.compactMap { key in flat[key].map { (key, $0) } }),
            batteryData: Dictionary(uniqueKeysWithValues: batteryKeys.compactMap { key in flat[key].map { (key, $0) } }),
            lifetimeData: Dictionary(uniqueKeysWithValues: lifetimeKeys.compactMap { key in flat[key].map { (key, $0) } })
        )
    }
}
