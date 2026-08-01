import AppKit
import Foundation
import Observation

struct MelixAppVersion: Equatable, Sendable {
  let marketingVersion: String
  let buildNumber: String

  var displayName: String {
    guard buildNumber.isEmpty == false, buildNumber != marketingVersion else {
      return marketingVersion
    }
    return "\(marketingVersion) (\(buildNumber))"
  }

  init(marketingVersion: String, buildNumber: String) {
    self.marketingVersion = marketingVersion
    self.buildNumber = buildNumber
  }

  init(infoDictionary: [String: Any]?) {
    let marketingVersion = infoDictionary?["CFBundleShortVersionString"] as? String
    let buildNumber = infoDictionary?["CFBundleVersion"] as? String
    self.init(
      marketingVersion: marketingVersion?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
        ?? "Development",
      buildNumber: buildNumber?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    )
  }
}

enum SoftwareUpdateConfigurationIssue: String, Equatable, Sendable {
  case missingFeedURL
  case invalidFeedURL
  case missingPublicKey
  case invalidPublicKey

  var displayMessage: String {
    switch self {
    case .missingFeedURL, .missingPublicKey:
      return "Signed updates are unavailable in this preview build."
    case .invalidFeedURL, .invalidPublicKey:
      return "Signed updates are disabled because this App bundle is misconfigured."
    }
  }
}

struct SoftwareUpdateConfiguration: Equatable, Sendable {
  static let repositoryURLString = "https://github.com/Keith-CY/melix"
  static let releasesURLString = "\(repositoryURLString)/releases"
  static let feedURLString = "\(repositoryURLString)/releases/latest/download/appcast.xml"
  static let feedURLInfoKey = "SUFeedURL"
  static let publicKeyInfoKey = "SUPublicEDKey"

  let feedURL: URL?
  let publicEDKey: String?
  let issue: SoftwareUpdateConfigurationIssue?

  var isEnabled: Bool {
    issue == nil && feedURL != nil && publicEDKey != nil
  }

  init(infoDictionary: [String: Any]?) {
    let rawFeedURL = (infoDictionary?[Self.feedURLInfoKey] as? String)?
      .trimmingCharacters(in: .whitespacesAndNewlines)
    let rawPublicKey = (infoDictionary?[Self.publicKeyInfoKey] as? String)?
      .trimmingCharacters(in: .whitespacesAndNewlines)

    guard let rawFeedURL, rawFeedURL.isEmpty == false else {
      self.feedURL = nil
      self.publicEDKey = rawPublicKey?.nilIfEmpty
      self.issue = .missingFeedURL
      return
    }
    guard let feedURL = URL(string: rawFeedURL), Self.isTrustedFeedURL(feedURL) else {
      self.feedURL = nil
      self.publicEDKey = rawPublicKey?.nilIfEmpty
      self.issue = .invalidFeedURL
      return
    }
    guard let rawPublicKey, rawPublicKey.isEmpty == false else {
      self.feedURL = feedURL
      self.publicEDKey = nil
      self.issue = .missingPublicKey
      return
    }
    guard let decodedKey = Data(base64Encoded: rawPublicKey), decodedKey.count == 32 else {
      self.feedURL = feedURL
      self.publicEDKey = nil
      self.issue = .invalidPublicKey
      return
    }

    self.feedURL = feedURL
    self.publicEDKey = rawPublicKey
    self.issue = nil
  }

  private static func isTrustedFeedURL(_ url: URL) -> Bool {
    guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
      return false
    }
    return components.scheme == "https"
      && components.host?.lowercased() == "github.com"
      && components.port == nil
      && components.user == nil
      && components.password == nil
      && components.query == nil
      && components.fragment == nil
      && components.path == "/Keith-CY/melix/releases/latest/download/appcast.xml"
  }
}

enum SoftwareUpdateFailureKind: String, Equatable, Sendable {
  case configuration
  case metadata
  case download
  case authenticity
  case extraction
  case replacement
  case relaunch
  case unknown

  var displayMessage: String {
    switch self {
    case .configuration:
      return "The signed updater is not configured correctly."
    case .metadata:
      return "Melix could not load verified update information."
    case .download:
      return "The update download did not complete. Your current App was not changed."
    case .authenticity:
      return "The update could not be authenticated and was not installed."
    case .extraction:
      return "The verified update could not be prepared. Your current App was not changed."
    case .replacement:
      return "Melix could not replace the App and kept the previous version."
    case .relaunch:
      return "The update was prepared, but Melix could not relaunch automatically."
    case .unknown:
      return "The update did not complete. Your current App was not changed."
    }
  }
}

struct SoftwareUpdateFailure: Equatable, Sendable {
  let kind: SoftwareUpdateFailureKind
  let code: Int

  var displayMessage: String {
    kind.displayMessage
  }
}

enum SoftwareUpdateStage: Equatable, Sendable {
  case unavailable
  case idle
  case checking
  case upToDate
  case updateAvailable(version: String)
  case downloading(version: String)
  case verifying(version: String)
  case installing(version: String)
  case relaunching(version: String)

  var displayTitle: String {
    switch self {
    case .unavailable:
      return "Unavailable"
    case .idle:
      return "Ready"
    case .checking:
      return "Checking for updates..."
    case .upToDate:
      return "Melix is up to date"
    case .updateAvailable(let version):
      return "Version \(version) is available"
    case .downloading(let version):
      return "Downloading version \(version)..."
    case .verifying(let version):
      return "Verifying version \(version)..."
    case .installing(let version):
      return "Installing version \(version)..."
    case .relaunching(let version):
      return "Relaunching version \(version)..."
    }
  }
}

enum SoftwareUpdateEngineEvent: Equatable, Sendable {
  case found(version: String)
  case noUpdate
  case downloading(version: String)
  case downloaded(version: String)
  case extracting(version: String)
  case installing(version: String)
  case relaunching(version: String)
  case cancelled
  case failed(SoftwareUpdateFailure)
  case finished(lastCheckDate: Date?)
}

@MainActor
protocol SoftwareUpdateDriving: AnyObject {
  var automaticallyChecksForUpdates: Bool { get set }
  var lastUpdateCheckDate: Date? { get }
  var canCheckForUpdates: Bool { get }

  func start() throws
  func checkForUpdates()
}

typealias SoftwareUpdateEngineFactory = (
  Bundle,
  @escaping @MainActor (SoftwareUpdateEngineEvent) -> Void
) throws -> any SoftwareUpdateDriving

@MainActor
@Observable
final class SoftwareUpdateController {
  static let shared = SoftwareUpdateController.live()

  private(set) var stage: SoftwareUpdateStage
  private(set) var lastCheckDate: Date?
  private(set) var lastFailure: SoftwareUpdateFailure?
  private(set) var automaticChecksEnabled = false
  private(set) var canCheckForUpdates = false

  let version: MelixAppVersion
  let configuration: SoftwareUpdateConfiguration

  private let applicationBundle: Bundle
  private let engineFactory: SoftwareUpdateEngineFactory
  private let openURL: @MainActor (URL) -> Void
  private var engine: (any SoftwareUpdateDriving)?

  var isAvailable: Bool {
    configuration.isEnabled
  }

  var configurationMessage: String? {
    configuration.issue?.displayMessage
  }

  init(
    applicationBundle: Bundle,
    configuration: SoftwareUpdateConfiguration,
    version: MelixAppVersion,
    engineFactory: @escaping SoftwareUpdateEngineFactory,
    openURL: @escaping @MainActor (URL) -> Void = { NSWorkspace.shared.open($0) }
  ) {
    self.applicationBundle = applicationBundle
    self.configuration = configuration
    self.version = version
    self.engineFactory = engineFactory
    self.openURL = openURL
    self.stage = configuration.isEnabled ? .idle : .unavailable
  }

  static func live(
    environment: [String: String] = ProcessInfo.processInfo.environment,
    fallbackBundle: Bundle = .main
  ) -> SoftwareUpdateController {
    let bundle = SoftwareUpdateBundleResolver.resolve(
      environment: environment,
      fallbackBundle: fallbackBundle
    )
    let configuration = SoftwareUpdateConfiguration(infoDictionary: bundle.infoDictionary)
    return SoftwareUpdateController(
      applicationBundle: bundle,
      configuration: configuration,
      version: MelixAppVersion(infoDictionary: bundle.infoDictionary),
      engineFactory: SparkleSoftwareUpdateEngine.make
    )
  }

  func start() {
    guard configuration.isEnabled, engine == nil else {
      return
    }

    do {
      let engine = try engineFactory(applicationBundle) { [weak self] event in
        self?.handle(event)
      }
      try engine.start()
      self.engine = engine
      refreshEngineState()
      stage = .idle
    } catch {
      let failure = SoftwareUpdateFailure(kind: .configuration, code: (error as NSError).code)
      lastFailure = failure
      stage = .unavailable
      canCheckForUpdates = false
    }
  }

  func setAutomaticChecksEnabled(_ enabled: Bool) {
    guard let engine else {
      return
    }
    engine.automaticallyChecksForUpdates = enabled
    refreshEngineState()
  }

  @objc
  func checkForUpdates(_ sender: Any? = nil) {
    _ = sender
    guard let engine, engine.canCheckForUpdates else {
      return
    }
    lastFailure = nil
    stage = .checking
    canCheckForUpdates = false
    engine.checkForUpdates()
  }

  func openReleasesPage() {
    guard let url = URL(string: SoftwareUpdateConfiguration.releasesURLString) else {
      return
    }
    openURL(url)
  }

  private func handle(_ event: SoftwareUpdateEngineEvent) {
    switch event {
    case .found(let version):
      stage = .updateAvailable(version: version)
    case .noUpdate:
      stage = .upToDate
      lastFailure = nil
    case .downloading(let version):
      stage = .downloading(version: version)
    case .downloaded(let version), .extracting(let version):
      stage = .verifying(version: version)
    case .installing(let version):
      stage = .installing(version: version)
    case .relaunching(let version):
      stage = .relaunching(version: version)
    case .cancelled:
      lastFailure = nil
      stage = configuration.isEnabled ? .idle : .unavailable
    case .failed(let failure):
      lastFailure = failure
      stage = configuration.isEnabled ? .idle : .unavailable
    case .finished(let lastCheckDate):
      self.lastCheckDate = lastCheckDate
      refreshEngineState()
      if lastFailure == nil, case .checking = stage {
        stage = .idle
      }
    }
  }

  private func refreshEngineState() {
    guard let engine else {
      automaticChecksEnabled = false
      canCheckForUpdates = false
      return
    }
    automaticChecksEnabled = engine.automaticallyChecksForUpdates
    canCheckForUpdates = engine.canCheckForUpdates
    lastCheckDate = engine.lastUpdateCheckDate ?? lastCheckDate
  }
}

enum SoftwareUpdateBundleResolver {
  static let applicationBundlePathEnvironmentKey = "MELIX_APP_BUNDLE_PATH"

  static func resolve(
    environment: [String: String],
    fallbackBundle: Bundle
  ) -> Bundle {
    guard
      let rawPath = environment[applicationBundlePathEnvironmentKey]?
        .trimmingCharacters(in: .whitespacesAndNewlines),
      rawPath.isEmpty == false,
      URL(fileURLWithPath: rawPath).pathExtension == "app",
      let bundle = Bundle(path: rawPath)
    else {
      return fallbackBundle
    }
    return bundle
  }
}

enum SoftwareUpdateErrorMapper {
  static let sparkleErrorDomain = "SUSparkleErrorDomain"

  static func isCancellation(_ error: NSError) -> Bool {
    error.domain == sparkleErrorDomain && [4007, 4008].contains(error.code)
  }

  static func failure(
    from error: NSError,
    updateWasDiscovered: Bool = false
  ) -> SoftwareUpdateFailure? {
    if error.domain == sparkleErrorDomain,
      error.code == 1001 || isCancellation(error)
    {
      return nil
    }
    guard error.domain == sparkleErrorDomain else {
      return SoftwareUpdateFailure(
        kind: updateWasDiscovered ? .download : .metadata,
        code: error.code
      )
    }

    let kind: SoftwareUpdateFailureKind
    switch error.code {
    case 1...7, 5000:
      kind = .configuration
    case 1000...1007:
      kind = .metadata
    case 2000...2001:
      kind = .download
    case 3001...3002:
      kind = .authenticity
    case 3000:
      kind = .extraction
    case 4004:
      kind = .relaunch
    case 4000...4006, 4009...4012:
      kind = .replacement
    default:
      kind = .unknown
    }
    return SoftwareUpdateFailure(kind: kind, code: error.code)
  }
}

extension String {
  fileprivate var nilIfEmpty: String? {
    isEmpty ? nil : self
  }
}
