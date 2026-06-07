import Foundation
import Testing

@testable import MelixControlPlaneCore

@Suite("HTTP Gateway Request Parser")
struct HTTPGatewayRequestParserTests {
    @Test("parser accepts bounded content-length bodies")
    func parserAcceptsBoundedContentLengthBodies() throws {
        let raw = Data(
            """
            POST /v1/responses HTTP/1.1\r
            Host: 127.0.0.1\r
            Content-Length: 2\r
            X-Forwarded-Prefix: /melix/api\r
            \r
            {}
            """.utf8
        )

        let result = HTTPGatewayRequestParser.parseRequest(from: raw, maxBodyBytes: 2)
        let request = try #require(result.successValue)

        #expect(request.method == .post)
        #expect(request.path == "/v1/responses")
        #expect(request.headers["x-forwarded-prefix"] == "/melix/api")
        #expect(request.body == Data("{}".utf8))
    }

    @Test("parser accepts delete requests and ignores trailing body bytes")
    func parserAcceptsDeleteRequestsAndIgnoresTrailingBodyBytes() throws {
        let raw = Data(
            """
            DELETE /v1/melix/auth/session HTTP/1.1\r
            Host: 127.0.0.1\r
            Content-Length: 0\r
            \r
            trailing
            """.utf8
        )

        let result = HTTPGatewayRequestParser.parseRequest(from: raw, maxBodyBytes: 0)
        let request = try #require(result.successValue)

        #expect(request.method == .delete)
        #expect(request.path == "/v1/melix/auth/session")
        #expect(request.body.isEmpty)
    }

    @Test("parser accepts options preflight requests")
    func parserAcceptsOptionsPreflightRequests() throws {
        let raw = Data(
            (
                "OPTIONS /v1/responses HTTP/1.1\r\n"
                    + "Host: 127.0.0.1\r\n"
                    + "Origin: http://localhost:5173\r\n"
                    + "Access-Control-Request-Method: POST\r\n"
                    + "Content-Length: 0\r\n"
                    + "\r\n"
            ).utf8
        )

        let result = HTTPGatewayRequestParser.parseRequest(from: raw, maxBodyBytes: 0)
        let request = try #require(result.successValue)

        #expect(request.method == .options)
        #expect(request.path == "/v1/responses")
        #expect(request.headers["origin"] == "http://localhost:5173")
        #expect(request.headers["access-control-request-method"] == "POST")
        #expect(request.body.isEmpty)
    }

    @Test("parser rejects oversized declared bodies before waiting for payload bytes")
    func parserRejectsOversizedDeclaredBodies() throws {
        let raw = Data(
            """
            POST /v1/responses HTTP/1.1\r
            Host: 127.0.0.1\r
            Content-Length: 5\r
            \r
            {}
            """.utf8
        )

        let result = HTTPGatewayRequestParser.parseRequest(from: raw, maxBodyBytes: 2)
        let error = try #require(result.failureValue)
        let response = HTTPGatewayRequestParser.errorResponse(for: error)

        #expect(error == .bodyTooLarge(declaredBytes: 5, maxBytes: 2))
        #expect(response.statusCode == 413)
    }

    @Test("parser rejects chunked bodies with typed refusal")
    func parserRejectsChunkedBodiesWithTypedRefusal() throws {
        let raw = Data(
            """
            POST /v1/responses HTTP/1.1\r
            Host: 127.0.0.1\r
            Transfer-Encoding: chunked\r
            \r
            2\r
            {}\r
            0\r
            \r
            """.utf8
        )

        let result = HTTPGatewayRequestParser.parseRequest(from: raw)
        let error = try #require(result.failureValue)
        let response = HTTPGatewayRequestParser.errorResponse(for: error)

        #expect(error == .unsupportedChunkedBody)
        #expect(response.statusCode == 413)
    }

    @Test("parser rejects unsafe forwarded prefixes")
    func parserRejectsUnsafeForwardedPrefixes() throws {
        let raw = Data(
            """
            GET /health HTTP/1.1\r
            Host: 127.0.0.1\r
            X-Forwarded-Prefix: https://evil.example/melix\r
            \r

            """.utf8
        )

        let result = HTTPGatewayRequestParser.parseRequest(from: raw)
        let error = try #require(result.failureValue)
        let response = HTTPGatewayRequestParser.errorResponse(for: error)

        #expect(response.statusCode == 400)
        #expect(error.errorCode == "invalid_forwarded_prefix")
    }

    @Test("parser rejects malformed request framing and content length")
    func parserRejectsMalformedRequestFramingAndContentLength() throws {
        let cases: [(Data, HTTPGatewayRequestParseError)] = [
            (Data("GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\n".utf8), .incomplete),
            (Data("PATCH /health HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n".utf8), .invalidRequest),
            (Data("GET /health\r\nHost: 127.0.0.1\r\n\r\n".utf8), .invalidRequest),
            (Data("POST /v1/responses HTTP/1.1\r\nContent-Length: nope\r\n\r\n".utf8), .invalidRequest),
            (Data("POST /v1/responses HTTP/1.1\r\nContent-Length: 4\r\n\r\n{}".utf8), .incomplete),
        ]

        for (raw, expectedError) in cases {
            let result = HTTPGatewayRequestParser.parseRequest(from: raw)
            let error = try #require(result.failureValue)
            let response = HTTPGatewayRequestParser.errorResponse(for: error)

            #expect(error == expectedError)
            #expect(response.statusCode == expectedError.statusCode)
            #expect(error.errorCode == expectedError.errorCode)
            #expect(error.message == expectedError.message)
        }
    }

    @Test("parser rejects headers that exceed the configured header byte limit")
    func parserRejectsHeadersThatExceedTheConfiguredHeaderByteLimit() throws {
        let rawWithoutDelimiter = Data("GET /health HTTP/1.1\r\nX-Filler: abcdef".utf8)
        let missingDelimiterResult = HTTPGatewayRequestParser.parseRequest(
            from: rawWithoutDelimiter,
            maxHeaderBytes: 16
        )
        let missingDelimiterError = try #require(missingDelimiterResult.failureValue)

        #expect(missingDelimiterError == .headersTooLarge(maxBytes: 16))
        #expect(HTTPGatewayRequestParser.errorResponse(for: missingDelimiterError).statusCode == 431)

        let rawWithDelimiter = Data(
            """
            GET /health HTTP/1.1\r
            X-Filler: abcdefghijklmnopqrstuvwxyz\r
            \r

            """.utf8
        )
        let delimiterResult = HTTPGatewayRequestParser.parseRequest(
            from: rawWithDelimiter,
            maxHeaderBytes: 32
        )
        let delimiterError = try #require(delimiterResult.failureValue)

        #expect(delimiterError == .headersTooLarge(maxBytes: 32))
        #expect(delimiterError.errorCode == "request_headers_too_large")

        let delimiterJustBeyondLimit = Data("\(String(repeating: "H", count: 25))\r\n\r\n".utf8)
        let delimiterJustBeyondLimitResult = HTTPGatewayRequestParser.parseRequest(
            from: delimiterJustBeyondLimit,
            maxHeaderBytes: 24
        )
        let delimiterJustBeyondLimitError = try #require(delimiterJustBeyondLimitResult.failureValue)

        #expect(delimiterJustBeyondLimitError == .headersTooLarge(maxBytes: 24))
    }

    @Test("parser rejects duplicate headers before interpreting security-sensitive values")
    func parserRejectsDuplicateHeadersBeforeInterpretingSecuritySensitiveValues() throws {
        let duplicateHeaderCases: [(Data, String)] = [
            (
                Data(
                    """
                    POST /v1/responses HTTP/1.1\r
                    Content-Length: 2\r
                    content-length: 0\r
                    \r
                    {}
                    """.utf8
                ),
                "content-length"
            ),
            (
                Data(
                    """
                    POST /v1/responses HTTP/1.1\r
                    Transfer-Encoding: gzip\r
                    transfer-encoding: chunked\r
                    \r

                    """.utf8
                ),
                "transfer-encoding"
            ),
            (
                Data(
                    """
                    GET /health HTTP/1.1\r
                    X-Forwarded-Prefix: /melix\r
                    x-forwarded-prefix: https://evil.example\r
                    \r

                    """.utf8
                ),
                "x-forwarded-prefix"
            ),
        ]

        for (raw, headerName) in duplicateHeaderCases {
            let result = HTTPGatewayRequestParser.parseRequest(from: raw)
            let error = try #require(result.failureValue)

            #expect(error == .duplicateHeader(headerName))
            #expect(error.statusCode == 400)
            #expect(error.errorCode == "duplicate_header")
            #expect(error.message.contains(headerName))
        }
    }

    @Test("parser rejects forwarded prefixes with traversal or empty segments")
    func parserRejectsForwardedPrefixesWithTraversalOrEmptySegments() throws {
        let unsafePrefixes = ["/melix//api", "/melix/../api", "/melix?route=api", "/melix#api"]

        for prefix in unsafePrefixes {
            let raw = Data(
                """
                GET /health HTTP/1.1\r
                Host: 127.0.0.1\r
                X-Forwarded-Prefix: \(prefix)\r
                \r

                """.utf8
            )
            let result = HTTPGatewayRequestParser.parseRequest(from: raw)
            let error = try #require(result.failureValue)

            #expect(error == .invalidForwardedPrefix(prefix))
            #expect(error.message.contains("X-Forwarded-Prefix"))
        }
    }
}
private extension Result where Success == HTTPRequest, Failure == HTTPGatewayRequestParseError {
    var successValue: HTTPRequest? {
        switch self {
        case .success(let request):
            return request
        case .failure:
            return nil
        }
    }

    var failureValue: HTTPGatewayRequestParseError? {
        switch self {
        case .success:
            return nil
        case .failure(let error):
            return error
        }
    }
}
