import SwiftUI

struct HealthRingView: View {
    let score: Int
    let verdict: Verdict

    @State private var animatedProgress: Double = 0

    private var color: Color {
        Color.verdictColor(for: verdict)
    }

    var body: some View {
        ZStack {
            // Background ring
            Circle()
                .stroke(Color.panel, lineWidth: 10)

            // Progress ring
            Circle()
                .trim(from: 0, to: animatedProgress)
                .stroke(
                    color,
                    style: StrokeStyle(lineWidth: 10, lineCap: .round)
                )
                .rotationEffect(.degrees(-90))
                .animation(.easeInOut(duration: 1.5), value: animatedProgress)

            // Score text
            VStack(spacing: 2) {
                Text("\(score)")
                    .font(.system(size: 48, weight: .heavy, design: .rounded))
                    .foregroundColor(.textPrimary)

                Text("HEALTH SCORE")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.textSecondary)
                    .tracking(1)
            }
        }
        .frame(width: 180, height: 180)
        .onAppear {
            animatedProgress = Double(score) / 100.0
        }
        .onChange(of: score) { _, newValue in
            animatedProgress = Double(newValue) / 100.0
        }
    }
}

struct VerdictBadgeView: View {
    let verdict: Verdict

    private var color: Color {
        Color.verdictColor(for: verdict)
    }

    var body: some View {
        Text(verdict.displayName)
            .font(.system(size: 14, weight: .bold, design: .rounded))
            .foregroundColor(.white)
            .padding(.horizontal, 20)
            .padding(.vertical, 8)
            .background(
                Capsule()
                    .fill(color)
            )
    }
}

struct MetricCardView: View {
    let title: String
    let value: String
    let icon: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Text(icon)
                    .font(.system(size: 12))
                Text(title)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.textSecondary)
                    .textCase(.uppercase)
                    .tracking(0.5)
            }

            Text(value)
                .font(.system(size: 22, weight: .bold, design: .rounded))
                .foregroundColor(.textPrimary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.panel)
        )
    }
}
