import AppKit

/// Menu bar icon controller using NSStatusItem.
/// Owned by AppDelegate, not self-assigned.
@MainActor
class MenuBarController {
    private var statusItem: NSStatusItem
    private var lastScanItem: NSMenuItem
    private var healthItem: NSMenuItem

    init() {
        statusItem = NSStatusBar.system.statusItem(
            withLength: NSStatusItem.variableLength
        )
        statusItem.button?.title = "🔋"

        let menu = NSMenu()

        let title = NSMenuItem(title: "Battery Guardian", action: nil, keyEquivalent: "")
        title.isEnabled = false
        menu.addItem(title)
        menu.addItem(.separator())

        lastScanItem = NSMenuItem(title: "Last Scan: --", action: nil, keyEquivalent: "")
        lastScanItem.isEnabled = false
        menu.addItem(lastScanItem)

        healthItem = NSMenuItem(title: "Health: --", action: nil, keyEquivalent: "")
        healthItem.isEnabled = false
        menu.addItem(healthItem)

        menu.addItem(.separator())

        let showItem = NSMenuItem(title: "Show Window", action: #selector(AppDelegate.showMainWindow), keyEquivalent: "")
        showItem.target = AppDelegate.shared
        menu.addItem(showItem)

        let scanItem = NSMenuItem(title: "Run Scan", action: #selector(AppDelegate.runScanFromMenu), keyEquivalent: "")
        scanItem.target = AppDelegate.shared
        menu.addItem(scanItem)

        menu.addItem(.separator())

        let quitItem = NSMenuItem(title: "Quit", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        menu.addItem(quitItem)

        statusItem.menu = menu

        // Load last scan from history if available
        if let lastScan = HistoryManager.shared.lastScan() {
            lastScanItem.title = "Last Scan: \(lastScan.verdict)"
            healthItem.title = "Health: \(lastScan.healthScore)/100"
        }
    }

    func updateStatus(_ result: ScanResult) {
        lastScanItem.title = "Last Scan: \(result.verdict.displayName)"
        healthItem.title = "Health: \(result.healthScore)/100"
        statusItem.button?.title = result.verdict == .noAnomalies ? "🔋" : "⚠️"
    }
}
