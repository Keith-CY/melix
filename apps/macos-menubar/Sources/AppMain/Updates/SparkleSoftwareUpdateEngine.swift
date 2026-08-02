import Foundation
import Sparkle

@MainActor
final class SparkleSoftwareUpdateEngine: NSObject, SoftwareUpdateDriving {
  private let eventHandler: @MainActor (SoftwareUpdateEngineEvent) -> Void
  private var userDriver: SPUStandardUserDriver!
  private(set) var updater: SPUUpdater!
  private var activeUpdateVersion = "update"
  private var updateWasDiscovered = false
  private var terminalEventEmitted = false

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
    beginUpdateCycle()
    updater.checkForUpdates()
  }

  private func beginUpdateCycle() {
    updateWasDiscovered = false
    terminalEventEmitted = false
  }

  private func emitCancellationIfNeeded() {
    guard terminalEventEmitted == false else { return }
    terminalEventEmitted = true
    eventHandler(.cancelled)
  }

  private func emitFailureIfNeeded(_ error: NSError) {
    guard terminalEventEmitted == false else { return }
    if SoftwareUpdateErrorMapper.isCancellation(error) {
      emitCancellationIfNeeded()
      return
    }
    guard
      let failure = SoftwareUpdateErrorMapper.failure(
        from: error,
        updateWasDiscovered: updateWasDiscovered
      )
    else { return }
    terminalEventEmitted = true
    eventHandler(.failed(failure))
  }

  private func version(for item: SUAppcastItem) -> String {
    item.displayVersionString.trimmingCharacters(in: .whitespacesAndNewlines)
  }
}

extension SparkleSoftwareUpdateEngine: SPUUpdaterDelegate {
  func updater(_ updater: SPUUpdater, didFindValidUpdate item: SUAppcastItem) {
    updateWasDiscovered = true
    activeUpdateVersion = version(for: item)
    eventHandler(.found(version: activeUpdateVersion))
  }

  func updaterDidNotFindUpdate(_ updater: SPUUpdater, error: any Error) {
    terminalEventEmitted = true
    eventHandler(.noUpdate)
  }

  func updater(
    _ updater: SPUUpdater,
    willDownloadUpdate item: SUAppcastItem,
    with request: NSMutableURLRequest
  ) {
    _ = request
    updateWasDiscovered = true
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
    emitFailureIfNeeded(error as NSError)
  }

  func userDidCancelDownload(_ updater: SPUUpdater) {
    _ = updater
    emitCancellationIfNeeded()
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
    if let error {
      emitFailureIfNeeded(error as NSError)
    }
    eventHandler(.finished(lastCheckDate: updater.lastUpdateCheckDate))
    beginUpdateCycle()
  }
}
