import SwiftUI

struct AboutView: View {
    @Environment(\.dismiss) var dismiss

    var body: some View {
        VStack(spacing: 20) {
            Text("🔋")
                .font(.system(size: 48))

            Text("Battery Guardian")
                .font(.system(size: 20, weight: .bold))
                .foregroundColor(.textPrimary)

            Text("v\(APP_VERSION)")
                .font(.system(size: 14))
                .foregroundColor(.textSecondary)

            Divider()

            VStack(spacing: 8) {
                Text("A forensic tool that looks for evidence of reprogramming and contradictory battery records in supported TI battery-gauge chips.")
                    .font(.system(size: 13))
                    .foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center)

                Link("batteryguardian.tech", destination: URL(string: "https://batteryguardian.tech")!)
                    .font(.system(size: 13, weight: .medium))

                Link("GitHub", destination: URL(string: "https://github.com/Dannyjay-hub/Battery-Guardian-for-Mac")!)
                    .font(.system(size: 13, weight: .medium))
            }

            Divider()

            Text("Made by Daniel Jesusegun")
                .font(.system(size: 12))
                .foregroundColor(.textSecondary)

            Button("Close") { dismiss() }
                .buttonStyle(.borderedProminent)
        }
        .padding(30)
        .frame(width: 380)
        .background(Color.bgDark)
    }
}

struct GuideView: View {
    @Environment(\.dismiss) var dismiss

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("Battery Guardian Guide")
                    .font(.system(size: 20, weight: .bold))
                    .foregroundColor(.textPrimary)

                guideSection(
                    title: "What This Tool Does",
                    content: "Battery Guardian reads battery-gauge data exposed by macOS and evaluates up to 9 forensic signals. The applicable checks and minimum evidence depend on the detected gauge profile. A clean scan means no supported anomaly was found; it does not prove that a battery is Apple-original."
                )

                guideSection(
                    title: "How Spoofing Works",
                    content: "Third-party repair shops can reprogram the battery gauge chip to report fake data: zero cycles, 100% health, and a recent manufacture date. Standard tools like CoconutBattery and System Information only read what the chip reports. If the chip lies, the tools show the lie."
                )

                guideSection(
                    title: "The 9 Forensic Signals",
                    content: """
                    1. Reset Signature: Combines cycle count, DOD0 sentinel values, and data-flash writes where supported
                    2. Qmax Consistency: Observes unusual relationships between learned and design capacity
                    3. Capacity Relationship: Compares chemical and usable capacity records
                    4. DOD0 Records: Reviews per-cell depth-of-discharge calibration values
                    5. Clock Integrity: Compares supported operating-time counters
                    6. Calibration Timeline: Checks whether calibration counters contradict the cycle counter
                    7. Pack Voltage: Reviews the reported maximum pack voltage
                    8. Historical Continuity: Compares compatible scans over time
                    9. Data-Flash Writes: Uses the gauge's write counter when the detected profile exposes it

                    Some signals are observation-only until the project has enough labelled evidence to validate a classification threshold.
                    """
                )

                guideSection(
                    title: "Verdicts",
                    content: """
                    NO ANOMALIES: No supported anomaly was found in the available evidence.
                    SUSPICIOUS: The active policy found a lower-confidence contradiction that needs review.
                    SPOOFED: The active policy found strong, profile-supported evidence of counter reset or reprogramming.
                    INSUFFICIENT EVIDENCE: The gauge is unsupported or required fields were unavailable.
                    ERROR: The scan could not be completed; no authenticity conclusion was made.
                    """
                )

                Button("Close") { dismiss() }
                    .buttonStyle(.borderedProminent)
                    .frame(maxWidth: .infinity, alignment: .center)
            }
            .padding(30)
        }
        .frame(width: 500, height: 600)
        .background(Color.bgDark)
    }

    private func guideSection(title: String, content: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 15, weight: .semibold))
                .foregroundColor(.textPrimary)

            Text(content)
                .font(.system(size: 13))
                .foregroundColor(.textSecondary)
                .lineSpacing(4)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(Color.panel)
        )
    }
}
