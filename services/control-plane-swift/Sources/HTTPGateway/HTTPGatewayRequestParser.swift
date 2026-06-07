import Foundation

public enum HTTPGatewayRequestParseError: Error, Equatable, Sendable {
    case incomplete
    case invalidRequest
    case headersTooLarge(maxBytes: Int)
    case duplicateHeader(String)
    case bodyTooLarge(declaredBytes: Int, maxBytes: Int)
    case unsupportedChunkedBody
    case invalidForwardedPrefix(String)
    case missingHostHeader

    public var statusCode: Int {
        switch self {
        case .incomplete, .invalidRequest, .duplicateHeader, .invalidForwardedPrefix, .missingHostHeader:
            return 400
        case .headersTooLarge:
            return 431
        case .bodyTooLarge, .unsupportedChunkedBody:
            return 413
        }
    }

    public var errorCode: String {
        switch self {
        case .incomplete, .invalidRequest:
            return "bad_request"
        case .headersTooLarge:
            return "request_headers_too_large"
        case .duplicateHeader:
            return "duplicate_header"
        case .bodyTooLarge:
            return "request_body_too_large"
        case .unsupportedChunkedBody:
            return "chunked_request_body_unsupported"
        case .invalidForwardedPrefix:
            return "invalid_forwarded_prefix"
        case .missingHostHeader:
            return "missing_host_header"
        }
    }

    public var message: String {
        switch self {
        case .incomplete, .invalidRequest:
            return "Unable to parse HTTP request."
        case let .headersTooLarge(maxBytes):
            return "Request headers exceed the \(maxBytes) byte limit."
        case let .duplicateHeader(name):
            return "Duplicate HTTP header is not accepted: \(name)."
        case let .bodyTooLarge(declaredBytes, maxBytes):
            return "Request body is too large: \(declaredBytes) bytes exceeds the \(maxBytes) byte limit."
        case .unsupportedChunkedBody:
            return "Transfer-Encoding: chunked is not supported by the local gateway."
        case .invalidForwardedPrefix:
            return "X-Forwarded-Prefix must be a relative path prefix without scheme, query, fragment, traversal, or empty path segments."
        case .missingHostHeader:
            return "HTTP/1.1 requests to the local gateway must include a Host header."
        }
    }
}
public enum HTTPGatewayRequestParser {
    public static let defaultMaxBodyBytes = 16 * 1024 * 1024
    public static let defaultMaxHeaderBytes = 64 * 1024

    public static func parseRequest(
        from data: Data,
        maxBodyBytes: Int = defaultMaxBodyBytes,
        maxHeaderBytes: Int = defaultMaxHeaderBytes
    ) -> Result<HTTPRequest, HTTPGatewayRequestParseError> {
        let resolvedMaxHeaderBytes = max(0, maxHeaderBytes)
        let headerDelimiter = Data("\r\n\r\n".utf8)
        let headerSearchLimit = min(data.count, resolvedMaxHeaderBytes + headerDelimiter.count)
        let headerSearchData = Data(data.prefix(headerSearchLimit))
        guard let headerRange = headerSearchData.range(of: headerDelimiter) else {
            guard data.count <= resolvedMaxHeaderBytes else {
                return .failure(.headersTooLarge(maxBytes: resolvedMaxHeaderBytes))
            }
            return .failure(.incomplete)
        }

        let headerData = data[..<headerRange.lowerBound]
        guard let headerText = String(data: headerData, encoding: .utf8) else {
            return .failure(.invalidRequest)
        }

        let lines = headerText.components(separatedBy: "\r\n")
        guard let requestLine = lines.first else {
            return .failure(.invalidRequest)
        }

        let requestParts = requestLine.split(separator: " ")
        guard requestParts.count == 3 else {
            return .failure(.invalidRequest)
        }

        let method: HTTPMethod
        switch String(requestParts[0]).uppercased() {
        case "GET":
            method = .get
        case "POST":
            method = .post
        case "DELETE":
            method = .delete
        case "OPTIONS":
            method = .options
        default:
            return .failure(.invalidRequest)
        }

        var headers: [String: String] = [:]
        for line in lines.dropFirst() {
            let pair = line.split(separator: ":", maxSplits: 1)
            guard pair.count == 2 else { continue }
            let key = String(pair[0]).lowercased()
            guard headers[key] == nil else {
                return .failure(.duplicateHeader(key))
            }
            headers[key] = String(pair[1]).trimmingCharacters(in: .whitespaces)
        }

        guard headers["host"]?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false else {
            return .failure(.missingHostHeader)
        }

        if let transferEncoding = headers["transfer-encoding"],
           transferEncoding
            .split(separator: ",")
            .map({ $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() })
            .contains("chunked") {
            return .failure(.unsupportedChunkedBody)
        }

        if let forwardedPrefix = headers["x-forwarded-prefix"],
           !isSafeForwardedPrefix(forwardedPrefix) {
            return .failure(.invalidForwardedPrefix(forwardedPrefix))
        }

        let bodyStart = headerRange.upperBound
        let rawContentLength = headers["content-length"] ?? "0"
        guard let contentLength = Int(rawContentLength), contentLength >= 0 else {
            return .failure(.invalidRequest)
        }
        let resolvedMaxBodyBytes = max(0, maxBodyBytes)
        guard contentLength <= resolvedMaxBodyBytes else {
            return .failure(.bodyTooLarge(declaredBytes: contentLength, maxBytes: resolvedMaxBodyBytes))
        }
        let expectedBodyEnd = bodyStart + contentLength
        guard data.count >= expectedBodyEnd else {
            return .failure(.incomplete)
        }

        let body = data[bodyStart..<expectedBodyEnd]
        return .success(
            HTTPRequest(
                method: method,
                path: String(requestParts[1]),
                headers: headers,
                body: Data(body)
            )
        )
    }

    public static func errorResponse(for error: HTTPGatewayRequestParseError) -> HTTPResponse {
        let payload = [
            "error": [
                "code": error.errorCode,
                "message": error.message,
            ],
        ]
        let data = (try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]))
            ?? Data("{}".utf8)
        return HTTPResponse(
            statusCode: error.statusCode,
            headers: ["content-type": "application/json"],
            body: .data(data)
        )
    }

    private static func isSafeForwardedPrefix(_ rawValue: String) -> Bool {
        let prefix = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard prefix.isEmpty || prefix.hasPrefix("/") else {
            return false
        }
        guard
            !prefix.contains("://"),
            !prefix.contains("?"),
            !prefix.contains("#"),
            !prefix.contains("\\"),
            !prefix.contains("//"),
            !prefix.contains("..")
        else {
            return false
        }
        return prefix.unicodeScalars.allSatisfy { scalar in
            CharacterSet.alphanumerics.contains(scalar)
                || scalar == "/"
                || scalar == "_"
                || scalar == "-"
                || scalar == "."
        }
    }
}
