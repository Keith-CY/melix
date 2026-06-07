import Foundation
import Testing

@testable import MelixControlPlaneCore

@Suite("Local Server Security Policy")
struct LocalServerSecurityPolicyTests {
    @Test("default policy admits loopback hosts and server-to-server requests without origin")
    func defaultPolicyAdmitsLoopbackHostsAndServerToServerRequestsWithoutOrigin() {
        let policy = LocalServerSecurityPolicy(
            bindHost: "127.0.0.1",
            environment: [:]
        )

        let receipt = policy.receipt
        let admission = policy.admit(headers: ["host": "localhost:12436"])

        #expect(admission == .accepted(cors: nil))
        #expect(receipt.schemaVersion == "melix.local_server_security.v1")
        #expect(receipt.bindHost == "127.0.0.1")
        #expect(receipt.loopbackOnlyHostPolicy == true)
        #expect(receipt.browserCorsPolicy == "default_denied")
        #expect(receipt.allowedHosts == ["127.0.0.1", "[::1]", "::1", "localhost"])
        #expect(receipt.allowedOrigins.isEmpty)
    }

    @Test("default policy rejects non-loopback host and browser origin")
    func defaultPolicyRejectsNonLoopbackHostAndBrowserOrigin() {
        let policy = LocalServerSecurityPolicy(
            bindHost: "127.0.0.1",
            environment: [:]
        )

        let hostRejected = policy.admit(headers: ["host": "attacker.test:12436"])
        let originRejected = policy.admit(headers: [
            "host": "127.0.0.1:12436",
            "origin": "https://attacker.test",
        ])

        #expect(hostRejected == .rejected(reason: .hostNotAllowed, headerValue: "attacker.test:12436"))
        #expect(originRejected == .rejected(reason: .originNotAllowed, headerValue: "https://attacker.test"))
    }

    @Test("present empty host is rejected")
    func presentEmptyHostIsRejected() {
        let policy = LocalServerSecurityPolicy(
            bindHost: "127.0.0.1",
            environment: [:]
        )

        let admission = policy.admit(headers: ["host": ""])

        #expect(admission == .rejected(reason: .hostNotAllowed, headerValue: ""))
    }

    @Test("in-process requests without host remain admissible")
    func inProcessRequestsWithoutHostRemainAdmissible() {
        let policy = LocalServerSecurityPolicy(
            bindHost: "127.0.0.1",
            environment: [:]
        )

        let admission = policy.admit(headers: [:])

        #expect(admission == .accepted(cors: nil))
    }

    @Test("bind-all listeners still default to loopback host allowlists")
    func bindAllListenersStillDefaultToLoopbackHostAllowlists() {
        let policy = LocalServerSecurityPolicy(
            bindHost: "0.0.0.0",
            environment: [:]
        )

        let loopbackAccepted = policy.admit(headers: ["host": "127.0.0.1:12436"])
        let lanRejected = policy.admit(headers: ["host": "192.168.1.44:12436"])

        #expect(loopbackAccepted == .accepted(cors: nil))
        #expect(lanRejected == .rejected(reason: .hostNotAllowed, headerValue: "192.168.1.44:12436"))
        #expect(policy.receipt.allowedHosts == ["127.0.0.1", "[::1]", "::1", "localhost"])
        #expect(policy.receipt.loopbackOnlyHostPolicy == true)
    }

    @Test("explicit allowlists are normalized deduplicated and exact matched")
    func explicitAllowlistsAreNormalizedDeduplicatedAndExactMatched() {
        let policy = LocalServerSecurityPolicy(
            bindHost: "0.0.0.0",
            environment: [
                "MELIX_ALLOWED_HOSTS": "operator.lan:12436, operator.lan:12436, 192.168.1.44",
                "MELIX_ALLOWED_ORIGINS": "http://localhost:5173, http://localhost:5173/, https://app.example.test",
            ]
        )

        let receipt = policy.receipt
        let accepted = policy.admit(headers: [
            "host": "operator.lan:12436",
            "origin": "http://localhost:5173",
        ])
        let rejected = policy.admit(headers: [
            "host": "operator.lan:12436",
            "origin": "http://localhost:5173/path",
        ])

        #expect(accepted == .accepted(cors: .init(origin: "http://localhost:5173")))
        #expect(rejected == .rejected(reason: .originNotAllowed, headerValue: "http://localhost:5173/path"))
        #expect(receipt.allowedHosts.contains("operator.lan"))
        #expect(receipt.allowedHosts.contains("192.168.1.44"))
        #expect(receipt.allowedOrigins == ["http://localhost:5173", "https://app.example.test"])
        #expect(receipt.browserCorsPolicy == "explicit_allowlist")
    }

    @Test("explicit origins discard paths queries and fragments")
    func explicitOriginsDiscardPathsQueriesAndFragments() {
        let policy = LocalServerSecurityPolicy(
            bindHost: "127.0.0.1",
            environment: [
                "MELIX_ALLOWED_ORIGINS": "http://localhost:5173/app?debug=1#section, https://APP.example.test/path",
            ]
        )

        let localAccepted = policy.admit(headers: [
            "host": "127.0.0.1:12436",
            "origin": "http://localhost:5173",
        ])
        let appAccepted = policy.admit(headers: [
            "host": "127.0.0.1:12436",
            "origin": "https://app.example.test",
        ])

        #expect(localAccepted == .accepted(cors: .init(origin: "http://localhost:5173")))
        #expect(appAccepted == .accepted(cors: .init(origin: "https://app.example.test")))
        #expect(policy.receipt.allowedOrigins == ["http://localhost:5173", "https://app.example.test"])
    }

    @Test("receipt builds JSON object from codable keys")
    func receiptBuildsJSONObjectFromCodableKeys() throws {
        let policy = LocalServerSecurityPolicy(
            bindHost: "127.0.0.1",
            environment: [
                "MELIX_ALLOWED_ORIGINS": "http://localhost:5173",
            ]
        )

        let payload = try policy.receipt.jsonObject(encoder: JSONEncoder())

        #expect(payload["schema_version"] as? String == "melix.local_server_security.v1")
        #expect(payload["bind_host"] as? String == "127.0.0.1")
        #expect(payload["allowed_hosts"] as? [String] == ["127.0.0.1", "[::1]", "::1", "localhost"])
        #expect(payload["allowed_origins"] as? [String] == ["http://localhost:5173"])
        #expect(payload["loopback_only_host_policy"] as? Bool == true)
        #expect(payload["browser_cors_policy"] as? String == "explicit_allowlist")
    }

    @Test("vary helper appends origin without duplicating existing origin entries")
    func varyHelperAppendsOriginWithoutDuplicatingExistingOriginEntries() {
        #expect(LocalServerSecurityPolicy.varyHeader(includingOriginFrom: nil) == "Origin")
        #expect(LocalServerSecurityPolicy.varyHeader(includingOriginFrom: "Cache-Control") == "Cache-Control, Origin")
        #expect(LocalServerSecurityPolicy.varyHeader(includingOriginFrom: "Cache-Control, Origin") == "Cache-Control, Origin")
        #expect(LocalServerSecurityPolicy.varyHeader(includingOriginFrom: "origin") == "origin")
    }
}
