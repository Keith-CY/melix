import Testing

@testable import AppMain

@Suite("Desktop Shell State", .serialized)
struct DesktopShellStateTests {
    @Test("lifecycle capability flags cover operator-facing states")
    func lifecycleCapabilityFlagsCoverOperatorFacingStates() {
        let draft = makeDesktopShellSession(lifecycle: .draft, powerState: .unavailable)
        let starting = makeDesktopShellSession(lifecycle: .starting, powerState: .active)
        let running = makeDesktopShellSession(lifecycle: .running, powerState: .active)
        let paused = makeDesktopShellSession(lifecycle: .paused, powerState: .active)
        let sleeping = makeDesktopShellSession(lifecycle: .sleeping, powerState: .deepSleep)
        let stopped = makeDesktopShellSession(lifecycle: .stopped, powerState: .stopped)
        let failed = makeDesktopShellSession(lifecycle: .error, powerState: .unavailable)
        let unavailable = makeDesktopShellSession(lifecycle: .unavailable, powerState: .unavailable)

        #expect(draft.canStart)
        #expect(draft.canStop == false)
        #expect(draft.retainsGatewayAccessConfiguration == false)
        #expect(draft.isInteractiveReady == false)

        #expect(starting.canStart == false)
        #expect(starting.canStop)
        #expect(starting.retainsGatewayAccessConfiguration)
        #expect(starting.isInteractiveReady == false)

        #expect(running.canPause)
        #expect(running.canResume == false)
        #expect(running.canWake == false)
        #expect(running.canStop)
        #expect(running.retainsGatewayAccessConfiguration)
        #expect(running.isInteractiveReady)

        #expect(paused.canResume)
        #expect(paused.canPause == false)
        #expect(paused.canStop)
        #expect(paused.retainsGatewayAccessConfiguration)
        #expect(paused.isInteractiveReady == false)

        #expect(sleeping.canWake)
        #expect(sleeping.canStop)
        #expect(sleeping.retainsGatewayAccessConfiguration)
        #expect(sleeping.isInteractiveReady)

        #expect(stopped.canStart)
        #expect(stopped.canStop == false)
        #expect(stopped.retainsGatewayAccessConfiguration == false)

        #expect(failed.canStart)
        #expect(failed.canStop)
        #expect(failed.retainsGatewayAccessConfiguration == false)

        #expect(unavailable.canStart)
        #expect(unavailable.canStop == false)
        #expect(unavailable.retainsGatewayAccessConfiguration == false)
    }

    @Test("idle policy and runtime summaries cover disabled active and unset thresholds")
    func idlePolicyAndRuntimeSummariesCoverDisabledActiveAndUnsetThresholds() {
        let disabled = makeDesktopShellSession(
            lifecycle: .running,
            powerState: .active,
            idleTimerSeconds: 0,
            autoSleepEnabled: false,
            lightSleepAfterSeconds: 0,
            deepSleepAfterSeconds: 0,
            wakeReason: .initialBoot
        )
        let enabledUnset = makeDesktopShellSession(
            lifecycle: .paused,
            powerState: .active,
            idleTimerSeconds: 0,
            autoSleepEnabled: true,
            lightSleepAfterSeconds: 0,
            deepSleepAfterSeconds: 0,
            wakeReason: .policyApply
        )
        let enabledConfigured = makeDesktopShellSession(
            lifecycle: .sleeping,
            powerState: .lightSleep,
            idleTimerSeconds: 42,
            autoSleepEnabled: true,
            lightSleepAfterSeconds: 300,
            deepSleepAfterSeconds: 900,
            wakeReason: .requestActivity
        )

        #expect(disabled.idlePolicySummaryText == "Auto sleep disabled.")
        #expect(disabled.runtimeDetailText == "Running • Active • Wake Initial Boot • Idle timer idle")

        #expect(enabledUnset.idlePolicySummaryText == "Auto sleep enabled • light sleep threshold unset • deep sleep threshold unset")
        #expect(enabledUnset.runtimeDetailText == "Paused • Active • Wake Policy Apply • Idle timer idle")

        #expect(enabledConfigured.lifecycleSummaryText == "Sleeping • Light Sleep")
        #expect(enabledConfigured.idlePolicySummaryText == "Auto sleep enabled • light after 300s • deep after 900s")
        #expect(enabledConfigured.runtimeDetailText == "Sleeping • Light Sleep • Wake Request Activity • Idle 42s")
    }

    @Test("lifecycle banners cover all surfaced desktop states")
    func lifecycleBannersCoverAllSurfacedDesktopStates() {
        let starting = makeDesktopShellSession(lifecycle: .starting, powerState: .active)
        let paused = makeDesktopShellSession(
            lifecycle: .paused,
            powerState: .active,
            autoSleepEnabled: true,
            lightSleepAfterSeconds: 300,
            deepSleepAfterSeconds: 900
        )
        let sleeping = makeDesktopShellSession(lifecycle: .sleeping, powerState: .deepSleep)
        let stopping = makeDesktopShellSession(lifecycle: .stopping, powerState: .active)
        let stopped = makeDesktopShellSession(lifecycle: .stopped, powerState: .stopped)
        let failed = makeDesktopShellSession(lifecycle: .error, powerState: .unavailable, lastError: "runtime failed")
        let unavailable = makeDesktopShellSession(lifecycle: .unavailable, powerState: .unavailable)

        #expect(makeDesktopShellSession(lifecycle: .draft, powerState: .unavailable).lifecycleBannerState == nil)
        #expect(makeDesktopShellSession(lifecycle: .running, powerState: .active).lifecycleBannerState == nil)

        #expect(starting.lifecycleBannerState?.severity == .info)
        #expect(starting.lifecycleBannerState?.title == "Server Is Starting")

        #expect(paused.lifecycleBannerState?.severity == .warning)
        #expect(paused.lifecycleBannerState?.detail.contains("Auto sleep enabled") ?? false)

        #expect(sleeping.lifecycleBannerState?.severity == .info)
        #expect(sleeping.lifecycleBannerState?.detail.contains("Deep Sleep mode is active") ?? false)

        #expect(stopping.lifecycleBannerState?.severity == .info)
        #expect(stopping.lifecycleBannerState?.title == "Server Is Stopping")

        #expect(stopped.lifecycleBannerState?.severity == .warning)
        #expect(stopped.lifecycleBannerState?.detail.contains("serve melix-dev-text") ?? false)

        #expect(failed.lifecycleBannerState?.severity == .critical)
        #expect(failed.lifecycleBannerState?.detail == "runtime failed")

        #expect(unavailable.lifecycleBannerState?.severity == .warning)
        #expect(unavailable.lifecycleBannerState?.detail.contains("available text model") ?? false)
    }

    @Test("chat workspace notices cover operator-facing server states")
    func chatWorkspaceNoticesCoverOperatorFacingServerStates() {
        let sleeping = makeDesktopShellSession(lifecycle: .sleeping, powerState: .deepSleep)
        let paused = makeDesktopShellSession(lifecycle: .paused, powerState: .active)
        let starting = makeDesktopShellSession(lifecycle: .starting, powerState: .active)
        let stopping = makeDesktopShellSession(lifecycle: .stopping, powerState: .active)
        let stopped = makeDesktopShellSession(lifecycle: .stopped, powerState: .stopped)
        let failedEmpty = makeDesktopShellSession(lifecycle: .error, powerState: .unavailable, lastError: "")
        let failedFilled = makeDesktopShellSession(lifecycle: .error, powerState: .unavailable, lastError: "gpu lost")
        let draft = makeDesktopShellSession(lifecycle: .draft, powerState: .unavailable)
        let unavailable = makeDesktopShellSession(lifecycle: .unavailable, powerState: .unavailable)

        #expect(makeDesktopShellSession(lifecycle: .running, powerState: .active).chatWorkspaceNoticeState == nil)

        #expect(sleeping.chatWorkspaceNoticeState?.severity == .info)
        #expect(sleeping.chatWorkspaceNoticeState?.detail.contains("deep sleep") ?? false)

        #expect(paused.chatWorkspaceNoticeState?.severity == .warning)
        #expect(paused.chatWorkspaceNoticeState?.title == "Server Is Paused")

        #expect(starting.chatWorkspaceNoticeState?.severity == .info)
        #expect(starting.chatWorkspaceNoticeState?.detail.contains("read-only") ?? false)

        #expect(stopping.chatWorkspaceNoticeState?.severity == .warning)
        #expect(stopping.chatWorkspaceNoticeState?.title == "Server Is Stopping")

        #expect(stopped.chatWorkspaceNoticeState?.severity == .warning)
        #expect(stopped.chatWorkspaceNoticeState?.detail.contains("Start the bound server session") ?? false)

        #expect(failedEmpty.chatWorkspaceNoticeState?.severity == .critical)
        #expect(failedEmpty.chatWorkspaceNoticeState?.detail == "The bound server session failed.")

        #expect(failedFilled.chatWorkspaceNoticeState?.severity == .critical)
        #expect(failedFilled.chatWorkspaceNoticeState?.detail == "gpu lost")

        #expect(draft.chatWorkspaceNoticeState?.severity == .warning)
        #expect(draft.chatWorkspaceNoticeState?.title == "No Active Server Session")

        #expect(unavailable.chatWorkspaceNoticeState?.severity == .warning)
        #expect(unavailable.chatWorkspaceNoticeState?.detail.contains("Choose a valid server session") ?? false)
    }
}

private func makeDesktopShellSession(
    lifecycle: DesktopServerSessionLifecycle,
    powerState: DesktopServerPowerState,
    idleTimerSeconds: Int = 0,
    autoSleepEnabled: Bool = false,
    lightSleepAfterSeconds: Int = 300,
    deepSleepAfterSeconds: Int = 900,
    wakeReason: DesktopServerWakeReason = .initialBoot,
    lastError: String = ""
) -> DesktopServerSessionState {
    DesktopServerSessionState(
        id: "server-session-1",
        title: "Server",
        modelID: "melix-dev-text",
        lifecycle: lifecycle,
        powerState: powerState,
        wakeReason: wakeReason,
        idleTimerSeconds: idleTimerSeconds,
        autoSleepEnabled: autoSleepEnabled,
        lightSleepAfterSeconds: lightSleepAfterSeconds,
        deepSleepAfterSeconds: deepSleepAfterSeconds,
        lastError: lastError
    )
}
