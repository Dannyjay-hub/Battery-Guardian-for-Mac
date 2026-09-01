import SwiftUI

struct ForensicLogView: View {
    let log: [LogEntry]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("FORENSIC CHECKS")
                .font(.system(size: 11, weight: .bold))
                .foregroundColor(.textSecondary)
                .tracking(1)
                .padding(.bottom, 12)

            ForEach(log) { entry in
                LogItemView(entry: entry)
            }
        }
    }
}

struct LogItemView: View {
    let entry: LogEntry
    @State private var isExpanded = false

    private var statusIcon: String {
        switch entry.status {
        case .success: return "✓"
        case .fail: return "✗"
        case .warning: return "!"
        case .info: return "i"
        }
    }

    private var statusColor: Color {
        Color.statusColor(for: entry.status)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header row
            Button(action: { withAnimation(.easeInOut(duration: 0.2)) { isExpanded.toggle() } }) {
                HStack(spacing: 12) {
                    // Status indicator
                    ZStack {
                        Circle()
                            .fill(statusColor.opacity(0.15))
                            .frame(width: 28, height: 28)
                        Text(statusIcon)
                            .font(.system(size: 13, weight: .bold))
                            .foregroundColor(statusColor)
                    }

                    Text(entry.title)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.textPrimary)
                        .lineLimit(1)

                    Spacer()

                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundColor(.textSecondary)
                }
                .padding(.vertical, 10)
                .padding(.horizontal, 12)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            // Expanded description
            if isExpanded {
                Text(entry.desc)
                    .font(.system(size: 12))
                    .foregroundColor(.textSecondary)
                    .lineSpacing(4)
                    .padding(.horizontal, 52)
                    .padding(.bottom, 12)
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }

            Divider()
                .background(Color.border)
        }
        .background(Color.panel.opacity(0.5))
    }
}
