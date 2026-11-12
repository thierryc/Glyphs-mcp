import Foundation

/// Native presentation uses the application's tables, not the Core framework bundle.
/// Bundle/locale injection keeps tests independent of the machine's language settings.
public enum AppLocalization {
    public static func text(_ key: String, bundle: Bundle = .main) -> String {
        bundle.localizedString(forKey: key, value: key, table: "Localizable")
    }

    public static func format(_ key: String, _ arguments: CVarArg...,
                              bundle: Bundle = .main, locale: Locale = .current) -> String {
        String(format: text(key, bundle: bundle), locale: locale, arguments: arguments)
    }

    public static func message(_ message: AppMessage, bundle: Bundle = .main, locale: Locale = .current) -> String {
        message.localized(bundle: bundle, locale: locale)
    }

    public static func count(_ key: String, _ count: Int, bundle: Bundle = .main,
                             locale: Locale = .current) -> String {
        format(key, Int64(count), bundle: bundle, locale: locale)
    }
}

/// Retains an English diagnostic plus a localizable template and its arguments.
/// Interpolated paths, external errors and identifiers are never treated as keys.
public struct AppMessage: ExpressibleByStringLiteral, ExpressibleByStringInterpolation, Sendable {
    public let key: String
    public let arguments: [String]
    public let diagnostic: String

    public init(stringLiteral value: String) {
        key = value; arguments = []; diagnostic = value
    }

    public init(stringInterpolation value: StringInterpolation) {
        key = value.key; arguments = value.arguments; diagnostic = value.diagnostic
    }

    public func localized(bundle: Bundle = .main, locale: Locale = .current) -> String {
        let template = AppLocalization.text(key, bundle: bundle)
        return arguments.isEmpty ? template : String(format: template, locale: locale, arguments: arguments)
    }

    public struct StringInterpolation: StringInterpolationProtocol {
        var key = ""
        var diagnostic = ""
        var arguments: [String] = []

        public init(literalCapacity: Int, interpolationCount: Int) {
            arguments.reserveCapacity(interpolationCount)
        }

        public mutating func appendLiteral(_ value: String) {
            key += value.replacingOccurrences(of: "%", with: "%%")
            diagnostic += value
        }

        public mutating func appendInterpolation<T>(_ value: T) {
            let text = String(describing: value)
            key += "%@"; arguments.append(text); diagnostic += text
        }
    }
}

public extension Error {
    /// Only application-owned errors are translated. External diagnostics stay intact.
    func presentationDescription(bundle: Bundle = .main, locale: Locale = .current) -> String {
        if let error = self as? InstallerError {
            switch error {
            case .userFacing(let text): return AppLocalization.text(text, bundle: bundle)
            case .localized(let message): return message.localized(bundle: bundle, locale: locale)
            }
        }
        if let error = self as? ProjectError {
            return error.presentation?.localized(bundle: bundle, locale: locale)
                ?? AppLocalization.text(error.message, bundle: bundle)
        }
        if let error = self as? RuntimeProbeFailure {
            return error.presentationDescription(bundle: bundle, locale: locale)
        }
        if let error = self as? ProcessCommandError {
            switch error {
            case .noResult(let executable):
                return AppLocalization.format("Command did not return a result: %@", executable, bundle: bundle, locale: locale)
            case .failed(let status, let executable, let arguments):
                return AppLocalization.format("Command failed (%@): %@ %@", String(status), executable, arguments, bundle: bundle, locale: locale)
            }
        }
        if let error = self as? ProcessOutputLimitError {
            return AppLocalization.format("Command output exceeded the %lld-byte capture limit.",
                                          Int64(error.limit), bundle: bundle, locale: locale)
        }
        if let error = self as? ProcessTimeoutError {
            let formatter = MeasurementFormatter()
            formatter.locale = locale
            formatter.unitStyle = .long
            formatter.unitOptions = .providedUnit
            formatter.numberFormatter.maximumFractionDigits = 1
            let duration = formatter.string(from: Measurement(value: error.duration, unit: UnitDuration.seconds))
            return AppLocalization.format("Command timed out after %@: %@.", duration, error.executable, bundle: bundle, locale: locale)
        }
        if let error = self as? UpdateStagingError {
            return AppLocalization.format("The update could not be completed. %@", error.message, bundle: bundle, locale: locale)
        }
        return localizedDescription
    }
}
