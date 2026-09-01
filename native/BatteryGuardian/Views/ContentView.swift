import SwiftUI

struct ContentView: View {
    @ObservedObject var state: ScanState
    @State private var showAbout = false
    @State private var showGuide = false
    @State private var reportMessage: String?

    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                headerView

                if state.status == .running {
                    progressView
                }

                if let result = state.result {
                    resultView(result)
                } else if state.status == .idle {
                    idleView
                }
            }
            .padding(24)
        }
        .background(Color.bgDark)
        .onAppear {
            // Auto-scan on launch, same as Python version
            if state.status == .idle {
                state.startScan()
            }
        }
        .sheet(isPresented: $showAbout) { AboutView() }
        .sheet(isPresented: $showGuide) { GuideView() }
        .alert("Report", isPresented: .init(
            get: { reportMessage != nil },
            set: { if !$0 { reportMessage = nil } }
        )) {
            Button("OK") { reportMessage = nil }
        } message: {
            Text(reportMessage ?? "")
        }
    }

    // ── Header ──────────────────────────────────────────────────────────

    private var headerView: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    Text("🔋")
                        .font(.system(size: 24))
                    Text("Battery Guardian")
                        .font(.system(size: 22, weight: .bold))
                        .foregroundColor(.textPrimary)
                }

                let serialStr = state.result?.metrics.serial ?? ""
                let serialSuffix = serialStr.isEmpty || serialStr == "--" ? "" : " | Battery S/N: \(serialStr)"
                Text("v\(APP_VERSION) | \(state.macModel)\(serialSuffix)")
                    .font(.system(size: 12))
                    .foregroundColor(.textSecondary)
            }

            Spacer()

            HStack(spacing: 8) {
                if state.result != nil {
                    headerButton("📄 Report") { generateReport() }
                }
                headerButton("Export Logs") { exportLogs() }
                headerButton("Guide") { showGuide = true }
                headerButton("About") { showAbout = true }
            }
        }
    }

    private func headerButton(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(.textSecondary)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(
                    RoundedRectangle(cornerRadius: 6)
                        .fill(Color.panel)
                )
        }
        .buttonStyle(.plain)
    }

    // ── Idle State ──────────────────────────────────────────────────────

    private var idleView: some View {
        VStack(spacing: 24) {
            Spacer().frame(height: 40)

            HealthRingView(score: 0, verdict: .analyzing)
                .opacity(0.3)

            Text("Ready to scan your battery")
                .font(.system(size: 16, weight: .medium))
                .foregroundColor(.textSecondary)

            scanButton

            Spacer().frame(height: 40)
        }
    }

    // ── Progress ────────────────────────────────────────────────────────

    private var progressView: some View {
        VStack(spacing: 16) {
            ProgressView(value: state.progress, total: 100)
                .progressViewStyle(.linear)
                .tint(.accent)

            Text("Analyzing battery registers...")
                .font(.system(size: 13))
                .foregroundColor(.textSecondary)
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.panel)
        )
    }

    // ── Results ─────────────────────────────────────────────────────────

    private func resultView(_ result: ScanResult) -> some View {
        VStack(spacing: 24) {
            // Ring + Verdict
            VStack(spacing: 16) {
                HealthRingView(score: result.healthScore, verdict: result.verdict)
                VerdictBadgeView(verdict: result.verdict)
            }

            // Metric cards
            metricsGrid(result.metrics)

            // Rescan button
            scanButton

            // Forensic checks
            ForensicLogView(log: result.log)
        }
    }

    // ── Metrics Grid ────────────────────────────────────────────────────

    private func metricsGrid(_ metrics: Metrics) -> some View {
        LazyVGrid(columns: [
            GridItem(.flexible(), spacing: 12),
            GridItem(.flexible(), spacing: 12),
            GridItem(.flexible(), spacing: 12)
        ], spacing: 12) {
            MetricCardView(title: "Cycles", value: metrics.cycleCount, icon: "🔄")
            MetricCardView(title: "Health", value: metrics.health, icon: "❤️")
            MetricCardView(title: "Entropy", value: metrics.qmaxVariance, icon: "📊")
            MetricCardView(title: "Made", value: metrics.manufactureDate, icon: "📅")
            MetricCardView(title: "Ratio", value: metrics.ratio, icon: "⚡")
            MetricCardView(title: "Temp", value: metrics.temperature, icon: "🌡️")
        }
    }

    // ── Scan Button ─────────────────────────────────────────────────────

    private var scanButton: some View {
        Button(action: { state.startScan() }) {
            HStack(spacing: 8) {
                if state.status == .running {
                    ProgressView()
                        .controlSize(.small)
                        .tint(.white)
                }
                Text(state.status == .running ? "Scanning..." : "↻ Re-scan")
                    .font(.system(size: 14, weight: .semibold))
            }
            .foregroundColor(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(state.status == .running ? Color.accent.opacity(0.5) : Color.accent)
            )
        }
        .buttonStyle(.plain)
        .disabled(state.status == .running)
    }

    // ── Actions ─────────────────────────────────────────────────────────

    private func exportLogs() {
        let result = HistoryManager.shared.exportToDesktop()
        reportMessage = result.success
            ? "Logs exported to:\n\(result.message)"
            : "Export failed: \(result.message)"
    }

    private func generateReport() {
        guard let result = state.result else { return }
        Task { @MainActor in
            do {
                let url = try ReportGenerator.generate(result: result, macModel: state.macModel)
                reportMessage = "Report saved to:\n\(url.path)"
            } catch {
                reportMessage = "Report failed: \(error.localizedDescription)"
            }
        }
    }
}
