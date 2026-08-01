import Foundation
import Sparkle
import Testing

@testable import AppMain

@Suite("Software Update Controller", .serialized)
struct SoftwareUpdateControllerTests {
  @Test("configuration requires the exact HTTPS Melix feed and a 32-byte EdDSA public key")
  func configurationRequiresTrustedFeedAndKey() {
    let publicKey = Data(repeating: 7, count: 32).base64EncodedString()
    let enabled = SoftwareUpdateConfiguration(infoDictionary: [
      "SUFeedURL": SoftwareUpdateConfiguration.feedURLString,
      "SUPublicEDKey": publicKey,
    ])
    let missingFeed = SoftwareUpdateConfiguration(infoDictionary: [
      "SUPublicEDKey": publicKey
    ])
    let invalidFeed = SoftwareUpdateConfiguration(infoDictionary: [
      "SUFeedURL": "https://example.com/appcast.xml",
      "SUPublicEDKey": publicKey,
    ])
    let missingKey = SoftwareUpdateConfiguration(infoDictionary: [
      "SUFeedURL": SoftwareUpdateConfiguration.feedURLString
    ])
    let invalidKey = SoftwareUpdateConfiguration(infoDictionary: [
      "SUFeedURL": SoftwareUpdateConfiguration.feedURLString,
      "SUPublicEDKey": "not-an-ed25519-key",
    ])

    #expect(enabled.isEnabled)
    #expect(enabled.feedURL?.absoluteString == SoftwareUpdateConfiguration.feedURLString)
    #expect(enabled.publicEDKey == publicKey)
    #expect(enabled.issue == nil)
    #expect(missingFeed.issue == .missingFeedURL)
    #expect(invalidFeed.issue == .invalidFeedURL)
    #expect(missingKey.issue == .missingPublicKey)
    #expect(invalidKey.issue == .invalidPublicKey)
  }

  @Test(
    "feed validation rejects query fragments credentials ports and cleartext transport",
    arguments: [
      "http://github.com/Keith-CY/melix/releases/latest/download/appcast.xml",
      "https://github.com:443/Keith-CY/melix/releases/latest/download/appcast.xml",
      "https://user@github.com/Keith-CY/melix/releases/latest/download/appcast.xml",
      "https://github.com/Keith-CY/melix/releases/latest/download/appcast.xml?channel=other",
      "https://github.com/Keith-CY/melix/releases/latest/download/appcast.xml#unsigned",
      "https://github.com/Keith-CY/other/releases/latest/download/appcast.xml",
    ])
  func feedValidationRejectsAlteredURLs(feedURL: String) {
    let configuration = SoftwareUpdateConfiguration(infoDictionary: [
      "SUFeedURL": feedURL,
      "SUPublicEDKey": Data(repeating: 3, count: 32).base64EncodedString(),
    ])

    #expect(configuration.issue == .invalidFeedURL)
    #expect(configuration.isEnabled == false)
  }

  @Test("version display avoids duplicate package version")
  func versionDisplayAvoidsDuplicates() {
    #expect(
      MelixAppVersion(marketingVersion: "1.2.0", buildNumber: "42").displayName
        == "1.2.0 (42)"
    )
    #expect(
      MelixAppVersion(marketingVersion: "1.2.0", buildNumber: "1.2.0").displayName
        == "1.2.0"
    )
    #expect(
      MelixAppVersion(infoDictionary: nil).displayName == "Development"
    )
    #expect(
      MelixAppVersion(infoDictionary: [
        "CFBundleShortVersionString": "   ",
        "CFBundleVersion": " 17 ",
      ]).displayName == "Development (17)"
    )
  }

  @Test("configuration issues lifecycle stages and redacted failures have stable copy")
  func publicStatusCopyIsComplete() {
    #expect(SoftwareUpdateConfigurationIssue.missingFeedURL.displayMessage.contains("preview"))
    #expect(SoftwareUpdateConfigurationIssue.missingPublicKey.displayMessage.contains("preview"))
    #expect(SoftwareUpdateConfigurationIssue.invalidFeedURL.displayMessage.contains("misconfigured"))
    #expect(SoftwareUpdateConfigurationIssue.invalidPublicKey.displayMessage.contains("misconfigured"))

    let stages: [SoftwareUpdateStage] = [
      .unavailable,
      .idle,
      .checking,
      .upToDate,
      .updateAvailable(version: "2.0"),
      .downloading(version: "2.0"),
      .verifying(version: "2.0"),
      .installing(version: "2.0"),
      .relaunching(version: "2.0"),
    ]
    #expect(stages.map(\.displayTitle) == [
      "Unavailable",
      "Ready",
      "Checking for updates...",
      "Melix is up to date",
      "Version 2.0 is available",
      "Downloading version 2.0...",
      "Verifying version 2.0...",
      "Installing version 2.0...",
      "Relaunching version 2.0...",
    ])

    let failureKinds: [SoftwareUpdateFailureKind] = [
      .configuration,
      .metadata,
      .download,
      .authenticity,
      .extraction,
      .replacement,
      .relaunch,
      .unknown,
    ]
    #expect(failureKinds.allSatisfy { kind in
      let message = kind.displayMessage
      return message.isEmpty == false && message.contains("http") == false && message.contains("/") == false
    })
  }

  @Test("live configuration resolves only an explicit App bundle override")
  @MainActor
  func liveConfigurationResolvesBundleOverride() throws {
    let fileManager = FileManager.default
    let temporaryRoot = fileManager.temporaryDirectory
      .appendingPathComponent("melix-update-bundle-\(UUID().uuidString)", isDirectory: true)
    let appURL = temporaryRoot.appendingPathComponent("Melix.app", isDirectory: true)
    let contentsURL = appURL.appendingPathComponent("Contents", isDirectory: true)
    try fileManager.createDirectory(at: contentsURL, withIntermediateDirectories: true)
    defer { try? fileManager.removeItem(at: temporaryRoot) }

    let publicKey = Data(repeating: 5, count: 32).base64EncodedString()
    let info: NSDictionary = [
      "CFBundleIdentifier": "ai.melix.app",
      "CFBundleName": "Melix",
      "CFBundlePackageType": "APPL",
      "CFBundleShortVersionString": "3.0.0",
      "CFBundleVersion": "300",
      "SUFeedURL": SoftwareUpdateConfiguration.feedURLString,
      "SUPublicEDKey": publicKey,
    ]
    #expect(info.write(to: contentsURL.appendingPathComponent("Info.plist"), atomically: true))
    let bundle = try #require(Bundle(path: appURL.path))

    #expect(
      SoftwareUpdateBundleResolver.resolve(environment: [:], fallbackBundle: .main) === Bundle.main
    )
    #expect(
      SoftwareUpdateBundleResolver.resolve(
        environment: [SoftwareUpdateBundleResolver.applicationBundlePathEnvironmentKey: "  "],
        fallbackBundle: .main
      ) === Bundle.main
    )
    #expect(
      SoftwareUpdateBundleResolver.resolve(
        environment: [SoftwareUpdateBundleResolver.applicationBundlePathEnvironmentKey: "/tmp/Melix"],
        fallbackBundle: .main
      ) === Bundle.main
    )
    #expect(
      SoftwareUpdateBundleResolver.resolve(
        environment: [SoftwareUpdateBundleResolver.applicationBundlePathEnvironmentKey: appURL.path],
        fallbackBundle: .main
      ).bundlePath == bundle.bundlePath
    )

    let controller = SoftwareUpdateController.live(
      environment: [SoftwareUpdateBundleResolver.applicationBundlePathEnvironmentKey: appURL.path],
      fallbackBundle: .main
    )
    #expect(controller.isAvailable)
    #expect(controller.version.displayName == "3.0.0 (300)")
  }

  @Test("preview configuration stays unavailable and never constructs an engine")
  @MainActor
  func previewConfigurationDoesNotStart() {
    var factoryCalls = 0
    let configuration = SoftwareUpdateConfiguration(infoDictionary: nil)
    let controller = SoftwareUpdateController(
      applicationBundle: .main,
      configuration: configuration,
      version: .init(marketingVersion: "0.1.0", buildNumber: "0.1.0"),
      engineFactory: { _, _ in
        factoryCalls += 1
        return RecordingSoftwareUpdateEngine()
      }
    )

    controller.start()
    controller.checkForUpdates()
    controller.setAutomaticChecksEnabled(true)

    #expect(factoryCalls == 0)
    #expect(controller.stage == .unavailable)
    #expect(controller.isAvailable == false)
    #expect(controller.canCheckForUpdates == false)
    #expect(
      controller.configurationMessage == "Signed updates are unavailable in this preview build.")
  }

  @Test("engine start failure is a redacted configuration failure")
  @MainActor
  func engineStartFailureIsRedacted() {
    let engine = RecordingSoftwareUpdateEngine()
    engine.startError = SoftwareUpdateTestError.failedToStart
    let controller = makeController(engine: engine)

    controller.start()

    #expect(controller.stage == .unavailable)
    #expect(controller.lastFailure?.kind == .configuration)
    #expect(controller.lastFailure?.displayMessage.contains("configured correctly") == true)
    #expect(controller.lastFailure?.displayMessage.contains("private") == false)
  }

  @Test("manual check exposes update download verification install and relaunch states")
  @MainActor
  func manualCheckExposesFullLifecycle() {
    let engine = RecordingSoftwareUpdateEngine()
    let controller = makeController(engine: engine)
    controller.start()

    controller.checkForUpdates()
    #expect(controller.stage == .checking)
    #expect(engine.checkCount == 1)

    engine.send(.found(version: "0.2.0"))
    #expect(controller.stage == .updateAvailable(version: "0.2.0"))

    engine.send(.downloading(version: "0.2.0"))
    #expect(controller.stage == .downloading(version: "0.2.0"))

    engine.send(.downloaded(version: "0.2.0"))
    #expect(controller.stage == .verifying(version: "0.2.0"))

    engine.send(.extracting(version: "0.2.0"))
    #expect(controller.stage == .verifying(version: "0.2.0"))

    engine.send(.installing(version: "0.2.0"))
    #expect(controller.stage == .installing(version: "0.2.0"))

    engine.send(.relaunching(version: "0.2.0"))
    #expect(controller.stage == .relaunching(version: "0.2.0"))
  }

  @Test("no-update cycle records up-to-date state and check date")
  @MainActor
  func noUpdateCycleRecordsStatus() {
    let engine = RecordingSoftwareUpdateEngine()
    let controller = makeController(engine: engine)
    let checkDate = Date(timeIntervalSince1970: 1_800_000_000)
    controller.start()
    controller.checkForUpdates()

    engine.send(.noUpdate)
    engine.lastUpdateCheckDate = checkDate
    engine.canCheckForUpdates = true
    engine.send(.finished(lastCheckDate: checkDate))

    #expect(controller.stage == .upToDate)
    #expect(controller.lastCheckDate == checkDate)
    #expect(controller.canCheckForUpdates)
    #expect(controller.lastFailure == nil)
  }

  @Test("finished checking returns to idle and start remains idempotent")
  @MainActor
  func finishedCheckingReturnsToIdle() {
    let engine = RecordingSoftwareUpdateEngine()
    let controller = makeController(engine: engine)
    controller.start()
    controller.start()
    #expect(engine.startCount == 1)

    engine.canCheckForUpdates = false
    engine.send(.finished(lastCheckDate: nil))
    controller.checkForUpdates()
    #expect(engine.checkCount == 0)

    let checkDate = Date(timeIntervalSince1970: 1_810_000_000)
    engine.canCheckForUpdates = true
    engine.lastUpdateCheckDate = checkDate
    engine.send(.finished(lastCheckDate: nil))
    controller.checkForUpdates()
    #expect(controller.stage == .checking)
    engine.send(.finished(lastCheckDate: nil))

    #expect(controller.stage == .idle)
    #expect(controller.lastCheckDate == checkDate)
    #expect(controller.canCheckForUpdates)
  }

  @Test(
    "network download authenticity extraction replacement and relaunch errors stay typed and redacted",
    arguments: [
      (
        NSError(domain: NSURLErrorDomain, code: NSURLErrorCannotConnectToHost),
        SoftwareUpdateFailureKind.metadata
      ),
      (NSError(domain: SoftwareUpdateErrorMapper.sparkleErrorDomain, code: 2001), .metadata),
      (NSError(domain: SoftwareUpdateErrorMapper.sparkleErrorDomain, code: 3001), .authenticity),
      (NSError(domain: SoftwareUpdateErrorMapper.sparkleErrorDomain, code: 3002), .authenticity),
      (NSError(domain: SoftwareUpdateErrorMapper.sparkleErrorDomain, code: 3000), .extraction),
      (NSError(domain: SoftwareUpdateErrorMapper.sparkleErrorDomain, code: 4000), .replacement),
      (NSError(domain: SoftwareUpdateErrorMapper.sparkleErrorDomain, code: 4004), .relaunch),
      (NSError(domain: SoftwareUpdateErrorMapper.sparkleErrorDomain, code: 1), .configuration),
      (NSError(domain: SoftwareUpdateErrorMapper.sparkleErrorDomain, code: 1000), .metadata),
      (NSError(domain: SoftwareUpdateErrorMapper.sparkleErrorDomain, code: 9999), .unknown),
    ])
  func failuresStayTypedAndRedacted(error: NSError, expectedKind: SoftwareUpdateFailureKind) throws
  {
    let failure = try #require(SoftwareUpdateErrorMapper.failure(from: error))

    #expect(failure.kind == expectedKind)
    #expect(failure.code == error.code)
    #expect(failure.displayMessage.contains("/") == false)
    #expect(failure.displayMessage.contains("http") == false)
  }

  @Test("Sparkle no-update sentinel is not surfaced as a failure")
  func noUpdateSentinelIsNotFailure() {
    let error = NSError(domain: SoftwareUpdateErrorMapper.sparkleErrorDomain, code: 1001)

    #expect(SoftwareUpdateErrorMapper.failure(from: error) == nil)
  }

  @Test(
    "Sparkle cancellation and authorize-later outcomes are not failures", arguments: [4007, 4008])
  func cancellationIsNotFailure(code: Int) {
    let error = NSError(domain: SoftwareUpdateErrorMapper.sparkleErrorDomain, code: code)

    #expect(SoftwareUpdateErrorMapper.isCancellation(error))
    #expect(SoftwareUpdateErrorMapper.failure(from: error) == nil)
  }

  @Test("network failures after discovery are download failures")
  func postDiscoveryNetworkFailureIsDownloadFailure() throws {
    let error = NSError(domain: NSURLErrorDomain, code: NSURLErrorNetworkConnectionLost)

    let failure = try #require(
      SoftwareUpdateErrorMapper.failure(from: error, updateWasDiscovered: true)
    )
    #expect(failure.kind == .download)
  }

  @Test("Sparkle 2001 before discovery is a metadata failure")
  func sparkle2001BeforeDiscoveryIsMetadataFailure() throws {
    let error = NSError(domain: SoftwareUpdateErrorMapper.sparkleErrorDomain, code: 2001)

    let failure = try #require(SoftwareUpdateErrorMapper.failure(from: error))
    #expect(failure.kind == .metadata)
  }

  @Test("Sparkle 2001 after discovery is a download failure")
  func sparkle2001AfterDiscoveryIsDownloadFailure() throws {
    let error = NSError(domain: SoftwareUpdateErrorMapper.sparkleErrorDomain, code: 2001)

    let failure = try #require(
      SoftwareUpdateErrorMapper.failure(from: error, updateWasDiscovered: true)
    )
    #expect(failure.kind == .download)
  }

  @Test("cancelled download returns to a retryable non-failure state")
  @MainActor
  func cancelledDownloadPermitsRetry() {
    let engine = RecordingSoftwareUpdateEngine()
    let controller = makeController(engine: engine)
    controller.start()
    controller.checkForUpdates()
    engine.send(.downloading(version: "2.0.0"))

    engine.send(.cancelled)
    engine.canCheckForUpdates = true
    engine.send(.finished(lastCheckDate: nil))

    #expect(controller.stage == .idle)
    #expect(controller.lastFailure == nil)
    #expect(controller.canCheckForUpdates)
    controller.checkForUpdates()
    #expect(engine.checkCount == 2)
  }

  @Test("failed cycle keeps current App and permits another check")
  @MainActor
  func failedCyclePermitsRetry() {
    let engine = RecordingSoftwareUpdateEngine()
    let controller = makeController(engine: engine)
    let failure = SoftwareUpdateFailure(kind: .authenticity, code: 3001)
    controller.start()
    controller.checkForUpdates()

    engine.send(.failed(failure))
    engine.canCheckForUpdates = true
    engine.send(.finished(lastCheckDate: nil))

    #expect(controller.stage == .idle)
    #expect(controller.lastFailure == failure)
    #expect(controller.canCheckForUpdates)

    controller.checkForUpdates()
    #expect(engine.checkCount == 2)
    #expect(controller.lastFailure == nil)
  }

  @Test("automatic check preference is owned by the update engine")
  @MainActor
  func automaticCheckPreferenceUsesEngine() {
    let engine = RecordingSoftwareUpdateEngine()
    engine.automaticallyChecksForUpdates = true
    let controller = makeController(engine: engine)
    controller.start()
    #expect(controller.automaticChecksEnabled)

    controller.setAutomaticChecksEnabled(false)

    #expect(engine.automaticallyChecksForUpdates == false)
    #expect(controller.automaticChecksEnabled == false)
  }

  @Test("View Releases opens only the stable repository page")
  @MainActor
  func viewReleasesOpensStablePage() {
    let engine = RecordingSoftwareUpdateEngine()
    var openedURL: URL?
    let controller = makeController(engine: engine) { openedURL = $0 }

    controller.openReleasesPage()

    #expect(openedURL?.absoluteString == SoftwareUpdateConfiguration.releasesURLString)
  }

  @Test("configuration performance probe stays below ten milliseconds for one hundred resolutions")
  func configurationPerformanceProbe() {
    let info: [String: Any] = [
      "SUFeedURL": SoftwareUpdateConfiguration.feedURLString,
      "SUPublicEDKey": Data(repeating: 9, count: 32).base64EncodedString(),
    ]
    let clock = ContinuousClock()

    let duration = clock.measure {
      for _ in 0..<100 {
        _ = SoftwareUpdateConfiguration(infoDictionary: info)
      }
    }

    #expect(duration < .milliseconds(10))
  }

  @Test("Sparkle delegate events preserve the update lifecycle and redact failures")
  @MainActor
  func sparkleDelegateEventsPreserveLifecycle() throws {
    var events: [SoftwareUpdateEngineEvent] = []
    let drivingEngine = try SparkleSoftwareUpdateEngine.make(
      applicationBundle: .main,
      eventHandler: { events.append($0) }
    )
    let engine = try #require(drivingEngine as? SparkleSoftwareUpdateEngine)
    let updater = try #require(engine.updater)
    let item = SUAppcastItem.empty()
    item.setValue(" 2.0.0 ", forKey: "displayVersionString")

    engine.checkForUpdates()
    do {
      try engine.start()
    } catch {
      #expect((error as NSError).localizedDescription.isEmpty == false)
    }

    engine.updater(updater, didFindValidUpdate: item)
    engine.updater(
      updater,
      willDownloadUpdate: item,
      with: NSMutableURLRequest(url: URL(string: "https://github.com")!)
    )
    engine.updater(updater, didDownloadUpdate: item)
    engine.updater(updater, willExtractUpdate: item)
    engine.updater(updater, willInstallUpdate: item)
    engine.updaterWillRelaunchApplication(updater)
    engine.updaterDidNotFindUpdate(
      updater,
      error: NSError(domain: SoftwareUpdateErrorMapper.sparkleErrorDomain, code: 1001)
    )
    engine.updater(updater, didFinishUpdateCycleFor: .updates, error: nil)
    engine.updater(updater, didFindValidUpdate: item)
    engine.updater(
      updater,
      failedToDownloadUpdate: item,
      error: NSError(domain: NSURLErrorDomain, code: NSURLErrorNetworkConnectionLost)
    )
    engine.userDidCancelDownload(updater)
    engine.updater(
      updater,
      didFinishUpdateCycleFor: .updates,
      error: NSError(domain: SoftwareUpdateErrorMapper.sparkleErrorDomain, code: 3001)
    )

    #expect(events.contains(.found(version: "2.0.0")))
    #expect(events.contains(.downloading(version: "2.0.0")))
    #expect(events.contains(.downloaded(version: "2.0.0")))
    #expect(events.contains(.extracting(version: "2.0.0")))
    #expect(events.contains(.installing(version: "2.0.0")))
    #expect(events.contains(.relaunching(version: "2.0.0")))
    #expect(events.contains(.noUpdate))
    #expect(events.contains(.failed(.init(kind: .download, code: NSURLErrorNetworkConnectionLost))))
    #expect(
      events.filter {
        if case .failed = $0 { return true }
        return false
      }.count == 1)
    #expect(events.contains(.cancelled) == false)
    #expect(
      events.contains { event in
        if case .finished = event { return true }
        return false
      })

    _ = engine.automaticallyChecksForUpdates
    _ = engine.lastUpdateCheckDate
    _ = engine.canCheckForUpdates
    engine.automaticallyChecksForUpdates = false
  }

  @Test("Sparkle cancellation emits once and finish suppresses duplicate failure")
  @MainActor
  func sparkleCancellationIsSingleTerminalEvent() throws {
    var events: [SoftwareUpdateEngineEvent] = []
    let drivingEngine = try SparkleSoftwareUpdateEngine.make(
      applicationBundle: .main,
      eventHandler: { events.append($0) }
    )
    let engine = try #require(drivingEngine as? SparkleSoftwareUpdateEngine)
    let updater = try #require(engine.updater)
    let item = SUAppcastItem.empty()
    item.setValue("2.0.0", forKey: "displayVersionString")
    engine.updater(updater, didFindValidUpdate: item)

    engine.userDidCancelDownload(updater)
    engine.updater(
      updater,
      didFinishUpdateCycleFor: .updates,
      error: NSError(domain: SoftwareUpdateErrorMapper.sparkleErrorDomain, code: 4007)
    )

    #expect(events.filter { $0 == .cancelled }.count == 1)
    #expect(
      events.contains {
        if case .failed = $0 { return true }
        return false
      } == false)
  }

  @MainActor
  private func makeController(
    engine: RecordingSoftwareUpdateEngine,
    openURL: @escaping @MainActor (URL) -> Void = { _ in }
  ) -> SoftwareUpdateController {
    let configuration = SoftwareUpdateConfiguration(infoDictionary: [
      "SUFeedURL": SoftwareUpdateConfiguration.feedURLString,
      "SUPublicEDKey": Data(repeating: 4, count: 32).base64EncodedString(),
    ])
    return SoftwareUpdateController(
      applicationBundle: .main,
      configuration: configuration,
      version: .init(marketingVersion: "0.1.0", buildNumber: "0.1.0"),
      engineFactory: { _, eventHandler in
        engine.eventHandler = eventHandler
        return engine
      },
      openURL: openURL
    )
  }
}

@MainActor
private final class RecordingSoftwareUpdateEngine: SoftwareUpdateDriving {
  var automaticallyChecksForUpdates = true
  var lastUpdateCheckDate: Date?
  var canCheckForUpdates = true
  var startError: (any Error)?
  var eventHandler: (@MainActor (SoftwareUpdateEngineEvent) -> Void)?
  private(set) var startCount = 0
  private(set) var checkCount = 0

  func start() throws {
    startCount += 1
    if let startError {
      throw startError
    }
  }

  func checkForUpdates() {
    checkCount += 1
  }

  func send(_ event: SoftwareUpdateEngineEvent) {
    eventHandler?(event)
  }
}

private enum SoftwareUpdateTestError: Error {
  case failedToStart
}
