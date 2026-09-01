import AppKit
import SwiftUI

@MainActor
class AppDelegate: NSObject, NSApplicationDelegate {
    nonisolated(unsafe) static var shared: AppDelegate?
    var menuBar: MenuBarController?
    var scanState: ScanState?

    func applicationDidFinishLaunching(_ notification: Notification) {
        Self.shared = self
        menuBar = MenuBarController()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ application: NSApplication) -> Bool {
        // Keep app alive in menu bar when window closes
        return false
    }

    @objc func showMainWindow() {
        NSApplication.shared.activate(ignoringOtherApps: true)
        if let window = NSApplication.shared.windows.first(where: { $0.canBecomeMain }) {
            window.makeKeyAndOrderFront(nil)
        }
    }

    @objc func runScanFromMenu() {
        showMainWindow()
        scanState?.startScan()
    }
}
