import Foundation
import IOKit

/// Reads battery data directly from IOKit — replaces subprocess ioreg call.
/// Properties are nested: top-level → BatteryData → LifetimeData.
class BatteryService {

    /// Read all battery registers from IOKit
    static func read() throws -> BatteryData {
        let service = IOServiceGetMatchingService(
            kIOMainPortDefault,
            IOServiceMatching("AppleSmartBattery")
        )
        guard service != IO_OBJECT_NULL else {
            throw BatteryError.noBattery
        }
        defer { IOObjectRelease(service) }

        var props: Unmanaged<CFMutableDictionary>?
        let result = IORegistryEntryCreateCFProperties(
            service, &props, kCFAllocatorDefault, 0
        )
        guard result == KERN_SUCCESS,
              let cfDict = props?.takeRetainedValue()
        else {
            throw BatteryError.readFailed
        }

        let topLevel = cfDict as NSDictionary as! [String: Any]
        let batteryData = topLevel["BatteryData"] as? [String: Any] ?? [:]
        let lifetimeData = batteryData["LifetimeData"] as? [String: Any] ?? [:]

        return BatteryData(
            topLevel: topLevel,
            batteryData: batteryData,
            lifetimeData: lifetimeData
        )
    }

    /// Check if this Mac has a battery
    static func hasBattery() -> Bool {
        let service = IOServiceGetMatchingService(
            kIOMainPortDefault,
            IOServiceMatching("AppleSmartBattery")
        )
        if service == IO_OBJECT_NULL { return false }
        IOObjectRelease(service)
        return true
    }
}
