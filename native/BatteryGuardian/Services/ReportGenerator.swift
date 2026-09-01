import SwiftUI

/// PDF report generator — uses SwiftUI ImageRenderer to render a report view to PDF.
struct ReportGenerator {
    @MainActor
    static func generate(result: ScanResult, macModel: String) throws -> URL {
        let reportView = ReportView(result: result, macModel: macModel)
            .frame(width: 595)  // A4 width in points

        let renderer = ImageRenderer(content: reportView)
        renderer.scale = 2.0  // Retina quality

        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd_HHmm"
        let dateStr = dateFormatter.string(from: Date())

        let url = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Desktop")
            .appendingPathComponent("BatteryGuardian_Report_\(dateStr).pdf")

        var pdfError: Error?

        renderer.render { size, context in
            var box = CGRect(origin: .zero, size: size)
            guard let pdf = CGContext(url as CFURL, mediaBox: &box, nil) else {
                pdfError = NSError(domain: "ReportGenerator", code: 1,
                    userInfo: [NSLocalizedDescriptionKey: "Failed to create PDF context"])
                return
            }
            pdf.beginPDFPage(nil)
            context(pdf)
            pdf.endPDFPage()
            pdf.closePDF()
        }

        if let error = pdfError { throw error }
        return url
    }
}

/// Light-themed report view designed for PDF output
struct ReportView: View {
    let result: ScanResult
    let macModel: String

    var body: some View {
        VStack(spacing: 0) {
            // Header
            reportHeader

            Divider()

            // Score section
            scoreSection

            Divider()

            // Metrics
            metricsSection

            Divider()

            // Forensic checks
            checksSection

            // Footer
            reportFooter
        }
        .padding(40)
        .background(Color.white)
    }

    private var reportHeader: some View {
        VStack(spacing: 8) {
            Text("🔋 BATTERY GUARDIAN SCAN REPORT")
                .font(.system(size: 20, weight: .bold))
                .foregroundColor(.black)

            HStack(spacing: 20) {
                Text("Date: \(formattedDate)")
                Text("Model: \(macModel)")
                if result.metrics.serial != "--" {
                    Text("S/N: \(result.metrics.serial)")
                }
            }
            .font(.system(size: 11))
            .foregroundColor(.gray)
        }
        .padding(.bottom, 20)
    }

    private var scoreSection: some View {
        VStack(spacing: 12) {
            Text("\(result.healthScore)")
                .font(.system(size: 60, weight: .heavy, design: .rounded))
                .foregroundColor(verdictTextColor)

            Text(result.verdict.displayName)
                .font(.system(size: 16, weight: .bold))
                .foregroundColor(.white)
                .padding(.horizontal, 24)
                .padding(.vertical, 8)
                .background(
                    Capsule().fill(verdictBgColor)
                )
        }
        .padding(.vertical, 24)
    }

    private var metricsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("METRICS")
                .font(.system(size: 12, weight: .bold))
                .foregroundColor(.gray)

            HStack(spacing: 20) {
                metricItem("Cycles", result.metrics.cycleCount)
                metricItem("Health", result.metrics.health)
                metricItem("Entropy", result.metrics.qmaxVariance)
                metricItem("Ratio", result.metrics.ratio)
                metricItem("Temp", result.metrics.temperature)
            }
        }
        .padding(.vertical, 16)
    }

    private func metricItem(_ title: String, _ value: String) -> some View {
        VStack(spacing: 4) {
            Text(title)
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(.gray)
            Text(value)
                .font(.system(size: 16, weight: .bold))
                .foregroundColor(.black)
        }
        .frame(maxWidth: .infinity)
    }

    private var checksSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("FORENSIC CHECKS")
                .font(.system(size: 12, weight: .bold))
                .foregroundColor(.gray)
                .padding(.top, 16)

            ForEach(result.log) { entry in
                HStack(spacing: 10) {
                    Circle()
                        .fill(checkColor(entry.status))
                        .frame(width: 8, height: 8)

                    Text(entry.title)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.black)

                    Spacer()

                    Text(entry.status.rawValue.uppercased())
                        .font(.system(size: 10, weight: .bold))
                        .foregroundColor(checkColor(entry.status))
                }
                .padding(.vertical, 4)
            }
        }
    }

    private var reportFooter: some View {
        VStack(spacing: 4) {
            Divider().padding(.vertical, 16)
            Text("Generated by Battery Guardian v\(APP_VERSION)")
                .font(.system(size: 10))
                .foregroundColor(.gray)
            Text("batteryguardian.tech")
                .font(.system(size: 10))
                .foregroundColor(.gray)
        }
    }

    private var verdictBgColor: Color {
        switch result.verdict {
        case .noAnomalies: return .green
        case .suspicious: return .orange
        case .spoofed: return .red
        case .insufficientEvidence: return .orange
        case .error: return .red
        case .analyzing: return .blue
        }
    }

    private var verdictTextColor: Color {
        switch result.verdict {
        case .noAnomalies: return .green
        case .suspicious: return .orange
        case .spoofed: return .red
        case .insufficientEvidence: return .orange
        case .error: return .red
        case .analyzing: return .blue
        }
    }

    private func checkColor(_ status: CheckStatus) -> Color {
        switch status {
        case .success: return .green
        case .fail: return .red
        case .warning: return .orange
        case .info: return .blue
        }
    }

    private var formattedDate: String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd HH:mm"
        return f.string(from: Date())
    }
}
