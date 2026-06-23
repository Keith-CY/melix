import Foundation

public enum UISinkEscaper {
    private static let allowedURLComponentCharacters: CharacterSet = {
        var allowed = CharacterSet.urlPathAllowed
        allowed.remove(charactersIn: "/?#[]@!$&'()*+,;=\"")
        return allowed
    }()

    public static func htmlText(_ value: String) -> String {
        htmlEscaped(value)
    }

    public static func htmlAttribute(_ value: String) -> String {
        htmlEscaped(value)
    }

    public static func cssString(_ value: String) -> String {
        guard value.isEmpty == false else {
            return value
        }

        var output = ""
        output.reserveCapacity(value.count)
        for scalar in value.unicodeScalars {
            switch scalar {
            case "\"":
                output += #"\22 "#
            case "\\":
                output += #"\5c "#
            case "<":
                output += #"\3c "#
            case ">":
                output += #"\3e "#
            default:
                if scalar.value < 0x20 || scalar.value == 0x7f {
                    output += "\\\(String(scalar.value, radix: 16)) "
                } else {
                    output.unicodeScalars.append(scalar)
                }
            }
        }
        return output
    }

    public static func cssURLToken(_ value: String) -> String {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard isAllowedCSSURL(trimmed) else {
            return #"url("about:blank")"#
        }
        return #"url("\#(cssString(trimmed))")"#
    }

    public static func urlComponent(_ value: String) -> String {
        value.addingPercentEncoding(withAllowedCharacters: allowedURLComponentCharacters) ?? ""
    }

    private static func htmlEscaped(_ value: String) -> String {
        guard value.isEmpty == false else {
            return value
        }

        var output = ""
        output.reserveCapacity(value.count)
        for scalar in value.unicodeScalars {
            switch scalar {
            case "&":
                output += "&amp;"
            case "<":
                output += "&lt;"
            case ">":
                output += "&gt;"
            case "\"":
                output += "&quot;"
            case "'":
                output += "&#39;"
            default:
                if scalar.value < 0x20 || scalar.value == 0x7f {
                    output += "&#\(scalar.value);"
                } else {
                    output.unicodeScalars.append(scalar)
                }
            }
        }
        return output
    }

    private static func isAllowedCSSURL(_ value: String) -> Bool {
        guard value.isEmpty == false else {
            return false
        }

        if value.hasPrefix("/") || value.hasPrefix("./") || value.hasPrefix("../") {
            return true
        }

        guard let colonIndex = value.firstIndex(of: ":") else {
            return true
        }

        if let firstRelativeDelimiter = value.firstIndex(where: { character in
            character == "/" || character == "?" || character == "#"
        }), firstRelativeDelimiter < colonIndex {
            return true
        }

        let schemeCandidate = value[..<colonIndex]
        guard isURISchemeCandidate(schemeCandidate) else {
            return true
        }

        let scheme = schemeCandidate.lowercased()
        return scheme == "http" || scheme == "https"
    }

    private static func isURISchemeCandidate(_ value: Substring) -> Bool {
        guard let first = value.unicodeScalars.first, isASCIIAlpha(first) else {
            return false
        }

        return value.unicodeScalars.dropFirst().allSatisfy { scalar in
            isASCIIAlpha(scalar)
                || isASCIIDigit(scalar)
                || scalar == "+"
                || scalar == "-"
                || scalar == "."
        }
    }

    private static func isASCIIAlpha(_ scalar: Unicode.Scalar) -> Bool {
        (0x41...0x5a).contains(scalar.value) || (0x61...0x7a).contains(scalar.value)
    }

    private static func isASCIIDigit(_ scalar: Unicode.Scalar) -> Bool {
        (0x30...0x39).contains(scalar.value)
    }
}
