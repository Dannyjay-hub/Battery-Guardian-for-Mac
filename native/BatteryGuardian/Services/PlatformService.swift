import Foundation

/// Platform detection — Mac model name and battery availability.
struct PlatformService {

    /// Get the Mac model marketing name
    static func macModel() -> String {
        // Read hardware model identifier via sysctl
        var size = 0
        sysctlbyname("hw.model", nil, &size, nil, 0)
        var model = [CChar](repeating: 0, count: size)
        sysctlbyname("hw.model", &model, &size, nil, 0)
        let identifierBytes = model.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }
        let identifier = String(decoding: identifierBytes, as: UTF8.self)

        // Try to get marketing name from IORegistry
        if let name = marketingName() {
            return name
        }

        return identifier
    }

    /// Read marketing name from IORegistry product-name
    private static func marketingName() -> String? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/sbin/system_profiler")
        process.arguments = ["SPHardwareDataType", "-detailLevel", "mini"]

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice

        do {
            try process.run()
            process.waitUntilExit()

            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            let output = String(data: data, encoding: .utf8) ?? ""

            // Parse "Model Name: MacBook Pro"
            for line in output.components(separatedBy: "\n") {
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                if trimmed.hasPrefix("Model Name:") {
                    let name = trimmed.replacingOccurrences(of: "Model Name:", with: "").trimmingCharacters(in: .whitespaces)
                    if !name.isEmpty { return name }
                }
                if trimmed.hasPrefix("Chip:") {
                    let chip = trimmed.replacingOccurrences(of: "Chip:", with: "").trimmingCharacters(in: .whitespaces)
                    if !chip.isEmpty {
                        return macModelWithChip(chip)
                    }
                }
            }
        } catch {
            // Fallback silently
        }

        return nil
    }

    /// Combine model name with chip for display
    private static func macModelWithChip(_ chip: String) -> String? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/sbin/system_profiler")
        process.arguments = ["SPHardwareDataType", "-detailLevel", "mini"]

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice

        do {
            try process.run()
            process.waitUntilExit()

            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            let output = String(data: data, encoding: .utf8) ?? ""

            var modelName: String?
            for line in output.components(separatedBy: "\n") {
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                if trimmed.hasPrefix("Model Name:") {
                    modelName = trimmed.replacingOccurrences(of: "Model Name:", with: "").trimmingCharacters(in: .whitespaces)
                }
            }

            if let name = modelName {
                return "\(name) (\(chip))"
            }
        } catch {}

        return nil
    }
}
