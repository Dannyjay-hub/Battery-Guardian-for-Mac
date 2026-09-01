import SwiftUI

@main
struct BatteryGuardianApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var scanState = ScanState()

    var body: some Scene {
        WindowGroup {
            ContentView(state: scanState)
                .frame(minWidth: 600, minHeight: 700)
                .onAppear {
                    appDelegate.scanState = scanState
                }
        }
        .windowStyle(.titleBar)
        .defaultSize(width: 800, height: 920)
    }
}
