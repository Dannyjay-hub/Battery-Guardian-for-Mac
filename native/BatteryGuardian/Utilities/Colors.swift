import SwiftUI

/// Design system — exact same color palette as bg_template.html
extension Color {
    static let bgDark = Color(red: 0.051, green: 0.051, blue: 0.059)       // #0D0D0F
    static let panel = Color(red: 0.102, green: 0.102, blue: 0.118)        // #1A1A1E
    static let panelHover = Color(red: 0.133, green: 0.133, blue: 0.157)   // #222228
    static let accent = Color(red: 0.039, green: 0.518, blue: 1.0)         // #0A84FF
    static let success = Color(red: 0.188, green: 0.820, blue: 0.345)      // #30D158
    static let danger = Color(red: 1.0, green: 0.271, blue: 0.227)         // #FF453A
    static let warning = Color(red: 1.0, green: 0.839, blue: 0.039)        // #FFD60A
    static let textPrimary = Color(red: 0.961, green: 0.961, blue: 0.969)  // #F5F5F7
    static let textSecondary = Color(red: 0.525, green: 0.525, blue: 0.545)// #86868B
    static let border = Color(red: 0.2, green: 0.2, blue: 0.22)           // #333338

    /// Get verdict color
    static func verdictColor(for verdict: Verdict) -> Color {
        switch verdict {
        case .noAnomalies: return .success
        case .suspicious: return .warning
        case .spoofed: return .danger
        case .insufficientEvidence: return .warning
        case .error: return .danger
        case .analyzing: return .accent
        }
    }

    /// Get check status color
    static func statusColor(for status: CheckStatus) -> Color {
        switch status {
        case .success: return .success
        case .fail: return .danger
        case .warning: return .warning
        case .info: return .accent
        }
    }
}

/// Single source of truth: Xcode's MARKETING_VERSION in the built Info.plist.
let APP_VERSION = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "Development"
