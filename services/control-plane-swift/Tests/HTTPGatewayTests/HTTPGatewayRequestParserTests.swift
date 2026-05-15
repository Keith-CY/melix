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
