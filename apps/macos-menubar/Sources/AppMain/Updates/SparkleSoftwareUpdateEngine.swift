import Foundation
import Sparkle

@MainActor
final class SparkleSoftwareUpdateEngine: NSObject, SoftwareUpdateDriving {
  private let eventHandler: @MainActor (SoftwareUpdateEngineEvent) -> Void
  private var userDriver: SPUStandardUserDriver!
  private(set) var updater: SPUUpdater!
  private var activeUpdateVersion = "update"

  static func make(
    applicationBundle: Bundle,
    eventHandler: @escaping @MainActor (SoftwareUpdateEngineEvent) -> Void
  ) throws -> any SoftwareUpdateDriving {
    SparkleSoftwareUpdateEngine(
      applicationBundle: applicationBundle,
      eventHandler: eventHandler
    )
  }

  init(
    applicationBundle: Bundle,
    eventHandler: @escaping @MainActor (SoftwareUpdateEngineEvent) -> Void
  ) {
    self.eventHandler = eventHandler
    super.init()
    userDriver = SPUStandardUserDriver(hostBundle: applicationBundle, delegate: nil)
    updater = SPUUpdater(
      hostBundle: applicationBundle,
      applicationBundle: applicationBundle,
      userDriver: userDriver,
      delegate: self
    )
  }

  var automaticallyChecksForUpdates: Bool {
    get { updater.automaticallyChecksForUpdates }
    set { updater.automaticallyChecksForUpdates = newValue }
  }

  var lastUpdateCheckDate: Date? {
    updater.lastUpdateCheckDate
  }

  var canCheckForUpdates: Bool {
    updater.canCheckForUpdates
  }

  func start() throws {
    try updater.start()
  }

  func checkForUpdates() {
    updater.checkForUpdates()
  }

  private func version(for item: SUAppcastItem) -> String {
    item.displayVersionString.trimmingCharacters(in: .whitespacesAndNewlines)
  }
}

extension SparkleSoftwareUpdateEngine: SPUUpdaterDelegate {
  func updater(_ updater: SPUUpdater, didFindValidUpdate item: SUAppcastItem) {
    activeUpdateVersion = version(for: item)
    eventHandler(.found(version: activeUpdateVersion))
  }

  func updaterDidNotFindUpdate(_ updater: SPUUpdater, error: any Error) {
    eventHandler(.noUpdate)
  }

  func updater(
    _ updater: SPUUpdater,
    willDownloadUpdate item: SUAppcastItem,
    with request: NSMutableURLRequest
  ) {
    _ = request
    activeUpdateVersion = version(for: item)
    eventHandler(.downloading(version: activeUpdateVersion))
  }

  func updater(_ updater: SPUUpdater, didDownloadUpdate item: SUAppcastItem) {
    activeUpdateVersion = version(for: item)
    eventHandler(.downloaded(version: activeUpdateVersion))
  }

  func updater(
    _ updater: SPUUpdater,
    failedToDownloadUpdate item: SUAppcastItem,
    error: any Error
  ) {
    _ = item
    let failure = SoftwareUpdateFailure(kind: .download, code: (error as NSError).code)
    eventHandler(.failed(failure))
  }

  func updater(_ updater: SPUUpdater, willExtractUpdate item: SUAppcastItem) {
    activeUpdateVersion = version(for: item)
    eventHandler(.extracting(version: activeUpdateVersion))
  }

  func updater(_ updater: SPUUpdater, willInstallUpdate item: SUAppcastItem) {
    activeUpdateVersion = version(for: item)
    eventHandler(.installing(version: activeUpdateVersion))
  }

  func updaterWillRelaunchApplication(_ updater: SPUUpdater) {
    eventHandler(.relaunching(version: activeUpdateVersion))
  }

  func updater(
    _ updater: SPUUpdater,
    didFinishUpdateCycleFor updateCheck: SPUUpdateCheck,
    error: (any Error)?
  ) {
    _ = updateCheck
    if let error,
      let failure = SoftwareUpdateErrorMapper.failure(from: error as NSError)
    {
      eventHandler(.failed(failure))
    }
    eventHandler(.finished(lastCheckDate: updater.lastUpdateCheckDate))
  }
}
