import SwiftUI
import Combine

/// Observable scan state — drives the UI reactively.
/// Replaces bg_state.py + bg_server.py (no HTTP server needed).
@MainActor
final class ScanState: ObservableObject {
    @Published var status: ScanStatus = .idle
    @Published var progress: Double = 0
    @Published var result: ScanResult?
    @Published var macModel: String = "--"
    @Published var deviceName: String?

    init() {
        macModel = PlatformService.macModel()
    }

    func startScan() {
        guard status != .running else { return }
        status = .running
        progress = 10

        // Read battery data off the main thread, then process
        let lastScan = HistoryManager.shared.lastScan()

        Task {
            progress = 30

            let scanResult: ScanResult
            let chipName: String?

            do {
                let data = try BatteryService.read()
                chipName = data.deviceName

                progress = 60

                let result = ForensicEngine.analyze(data, lastScan: lastScan)

                progress = 90

                HistoryManager.shared.save(data: data, result: result)
                scanResult = result
            } catch {
                scanResult = ScanResult(
                    log: [LogEntry(title: "System Error", desc: error.localizedDescription, status: .fail)],
                    score: 0,
                    healthScore: 0,
                    verdict: .error,
                    metrics: .empty,
                    trends: .empty,
                    policyVersion: "--",
                    gaugeProfile: nil,
                    evidenceComplete: false,
                    missingFields: []
                )
                chipName = nil
            }

            result = scanResult
            deviceName = chipName
            status = .complete
            progress = 100

            AppDelegate.shared?.menuBar?.updateStatus(scanResult)
        }
    }
}
