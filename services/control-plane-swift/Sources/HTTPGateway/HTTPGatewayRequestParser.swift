import Foundation

public enum HTTPGatewayRequestParseError: Error, Equatable, Sendable {
    case incomplete
    case invalidRequest
    case bodyTooLarge(declaredBytes: Int, maxBytes: Int)
    case unsupportedChunkedBody
    case invalidForwardedPrefix(String)

    public var statusCode: Int {
        switch self {
        case .incomplete, .invalidRequest, .invalidForwardedPrefix:
            return 400
        case .bodyTooLarge, .unsupportedChunkedBody:
            return 413
        }
    }

    public var errorCode: String {
        switch self {
        case .incomplete, .invalidRequest:
            return "bad_request"
        case .bodyTooLarge:
            return "request_body_too_large"
        case .unsupportedChunkedBody:
            return "chunked_request_body_unsupported"
        case .invalidForwardedPrefix:
            return "invalid_forwarded_prefix"
        }
    }

    public var message: String {
        switch self {
        case .incomplete, .invalidRequest:
            return "Unable to parse HTTP request."
        case let .bodyTooLarge(declaredBytes, maxBytes):
            return "Request body is too large: \(declaredBytes) bytes exceeds the \(maxBytes) byte limit."
        case .unsupportedChunkedBody:
            return "Transfer-Encoding: chunked is not supported by the local gateway."
        case .invalidForwardedPrefix:
            return "X-Forwarded-Prefix must be a relative path prefix without scheme, query, fragment, traversal, or empty path segments."
        }
    }
}
public enum HTTPGatewayRequestParser {
    public static let defaultMaxBodyBytes = 16 * 1024 * 1024

    public static func parseRequest(
        from data: Data,
        maxBodyBytes: Int = defaultMaxBodyBytes
    ) -> Result<HTTPRequest, HTTPGatewayRequestParseError> {
        guard let headerRange = data.range(of: Data("\r\n\r\n".utf8)) else {
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
        default:
            return .failure(.invalidRequest)
        }

        var headers: [String: String] = [:]
        for line in lines.dropFirst() {
            let pair = line.split(separator: ":", maxSplits: 1)
            guard pair.count == 2 else { continue }
            headers[String(pair[0]).lowercased()] = String(pair[1]).trimmingCharacters(in: .whitespaces)
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
