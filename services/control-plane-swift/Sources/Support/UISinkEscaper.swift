import Foundation

public enum UISinkEscaper {
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
            case "\n":
                output += #"\a "#
            case "\r":
                output += #"\d "#
            case "\u{000C}":
                output += #"\c "#
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
        var allowed = CharacterSet.urlPathAllowed
        allowed.remove(charactersIn: "/?#[]@!$&'()*+,;=\"")
        return value.addingPercentEncoding(withAllowedCharacters: allowed) ?? ""
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
            case "\n":
                output += "&#10;"
            case "\r":
                output += "&#13;"
            case "\u{0009}":
                output += "&#9;"
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
        let scheme = value[..<colonIndex].lowercased()
        return scheme == "http" || scheme == "https"
    }
}
