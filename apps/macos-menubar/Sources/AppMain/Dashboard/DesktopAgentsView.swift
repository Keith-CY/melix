import MelixControlPlaneProtocol
import SwiftUI

@MainActor
struct DesktopAgentsView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        HStack(spacing: 0) {
            runHistory
                .frame(width: 260)

            Divider()

            VStack(spacing: 0) {
                DesktopAgentOperationsOverview(viewModel: viewModel)

                Divider()

                Group {
                    if let run = viewModel.selectedAgentRun {
                        DesktopAgentRunDetailView(
                            viewModel: viewModel,
                            run: run
                        )
                    } else {
                        MelixActionableEmptyState(
                            title: "No Agent Runs",
                            systemImage: "bolt.horizontal.circle",
                            detail: "Switch Chat to Act, choose a provider, and give Melix a task. Tool calls, approvals, cancellation receipts, and evidence appear here."
                        ) {
                            Button("Start in Chat") {
                                viewModel.setChatInteractionMode(.act)
                                viewModel.selectSurface(.chat)
                            }
                            .buttonStyle(.borderedProminent)
                        }
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(Color(nsColor: .windowBackgroundColor))
    }

    private var runHistory: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Run History")
                    .melixSectionLabel()
                Spacer()
                Button {
                    Task {
                        await viewModel.refreshAgentRunsForOperator()
                    }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .help("Refresh Agent Runs")
                .accessibilityLabel("Refresh Agent Runs")
            }

            if viewModel.agentRuns.isEmpty {
                Text("No runs yet")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 12)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 7) {
                        ForEach(viewModel.agentRuns, id: \.runID) { run in
                            DesktopAgentRunRow(
                                viewModel: viewModel,
                                run: run,
                                isSelected: run.runID == viewModel.selectedAgentRunID
                            )
                        }
                    }
                }
            }

            Spacer(minLength: 0)

            Button {
                viewModel.setChatInteractionMode(.act)
                viewModel.selectSurface(.chat)
            } label: {
                Label("Start in Chat", systemImage: "plus")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(viewModel.isChatBusy)
        }
        .padding(14)
        .background(Color(nsColor: .controlBackgroundColor).opacity(0.42))
    }
}

@MainActor
private struct DesktopAgentOperationsOverview: View {
    let viewModel: RuntimeViewModel

    @Environment(\.openURL) private var openURL

    private var readySourceCount: Int {
        viewModel.agentOperations.toolSources.filter {
            ["ready", "live"].contains($0.connectionState)
        }.count
    }

    private var computerStatus: Melix_Controlplane_V1_AgentComputerUseStatus {
        viewModel.agentOperations.computerUse
    }

    private var computerReady: Bool {
        computerStatus.capabilityLevel == "ax_semantic_press_only"
            && computerStatus.screenRecordingPermission == "granted"
            && computerStatus.accessibilityPermission == "granted"
    }

    private var hasRepairableComputerPermission: Bool {
        guard computerStatus.brokerConfigured,
              computerStatus.capabilityLevel == "ax_semantic_press_only" else {
            return false
        }
        return permissionNeedsGrant(computerStatus.screenRecordingPermission)
            || permissionNeedsGrant(computerStatus.accessibilityPermission)
    }

    private var computerRestartRequired: Bool {
        computerStatus.screenRecordingPermission == "restart_required"
            || computerStatus.accessibilityPermission == "restart_required"
    }

    private var computerProbeUnavailable: Bool {
        let unavailableStates = ["", "unknown", "unavailable"]
        return unavailableStates.contains(computerStatus.screenRecordingPermission)
            || unavailableStates.contains(computerStatus.accessibilityPermission)
    }

    private var computerTargetDiscoveryFailed: Bool {
        computerStatus.targetDiscoveryState
            == .agentComputerUseTargetDiscoveryFailed
    }

    private var computerValue: String {
        guard computerStatus.brokerConfigured else {
            return "Not configured"
        }
        guard computerStatus.capabilityLevel == "ax_semantic_press_only" else {
            return "Probe unavailable"
        }
        if computerRestartRequired {
            return "Restart required"
        }
        if computerProbeUnavailable {
            return "Probe unavailable"
        }
        if computerTargetDiscoveryFailed {
            return "Window refresh failed"
        }
        return computerReady ? "Permissions ready" : "Permission needed"
    }

    private var computerDetail: String {
        guard computerStatus.brokerConfigured else {
            return "The signed private broker transport is not configured."
        }
        let permissions = "Screen \(permissionLabel(computerStatus.screenRecordingPermission)) · Accessibility \(permissionLabel(computerStatus.accessibilityPermission))"
        let budget = computerStatus.maximumFrames > 0
            && computerStatus.maximumActions > 0
            ? " · \(computerStatus.maximumFrames) frames / \(computerStatus.maximumActions) actions"
            : ""
        let targetState: String
        switch computerStatus.targetDiscoveryState {
        case .agentComputerUseTargetDiscoveryReady,
             .agentComputerUseTargetDiscoveryEmpty,
             .agentComputerUseTargetDiscoveryFailed:
            targetState = " · \(viewModel.computerUseTargetDiscoveryStatusText)"
        case .unspecified,
             .agentComputerUseTargetDiscoveryNotRequested,
             .UNRECOGNIZED(_):
            targetState = ""
        }
        return "\(permissions)\(budget)\(targetState)"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 10) {
                DesktopAgentOperationsCard(
                    title: "Tool Sources",
                    value: viewModel.agentOperations.toolSources.isEmpty
                        ? "Not inspected"
                        : "\(readySourceCount) / \(viewModel.agentOperations.toolSources.count) ready",
                    detail: "Live worker receipts, not run history. Catalog-only sources cannot execute.",
                    systemImage: "point.3.connected.trianglepath.dotted",
                    isReady: readySourceCount > 0
                )
                DesktopAgentOperationsCard(
                    title: "Tool Sets",
                    value: viewModel.agentOperations.tools.isEmpty
                        ? "No callable tools"
                        : "\(viewModel.agentOperations.tools.count) callable",
                    detail: "Current names, adapters, risks, and schema digests from the worker catalog.",
                    systemImage: "square.stack.3d.up",
                    isReady: viewModel.agentOperations.tools.isEmpty == false
                )
                DesktopAgentOperationsCard(
                    title: "Approval Policies",
                    value: viewModel.agentApprovalPolicy.rules.isEmpty
                        ? "Ask by default"
                        : "\(viewModel.agentApprovalPolicy.rules.count) saved",
                    detail: "Always Allow This Tool is exact-scope and can be revoked below.",
                    systemImage: "checkmark.shield",
                    isReady: viewModel.isAgentRuntimeAvailable
                )
                DesktopAgentOperationsCard(
                    title: "Computer Use · Semantic Press",
                    value: computerValue,
                    detail: computerDetail,
                    systemImage: "macwindow",
                    isReady: computerReady
                )
            }

            if hasRepairableComputerPermission {
                computerPermissionRepair
            }
            if computerRestartRequired {
                computerRestartRepair
            }
            if computerProbeUnavailable,
               computerStatus.brokerConfigured,
               computerStatus.capabilityLevel == "ax_semantic_press_only" {
                computerProbeRepair
            }
            if computerTargetDiscoveryFailed {
                computerTargetDiscoveryRepair
            }

            runtimeInventory
            approvalPolicies
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(nsColor: .controlBackgroundColor).opacity(0.24))
    }

    private var computerPermissionRepair: some View {
        HStack(alignment: .center, spacing: 9) {
            Image(systemName: "exclamationmark.shield")
                .foregroundStyle(MelixDesignTokens.StatusColor.warning)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text("Computer Use needs macOS permission")
                    .font(.caption.weight(.semibold))
                Text("Grant the missing permission in System Settings, then refresh the live probe. Restart Melix if macOS asks you to.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            if permissionNeedsGrant(computerStatus.screenRecordingPermission) {
                Button("Open Screen Recording") {
                    openComputerUsePermissionPane("Privacy_ScreenCapture")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .accessibilityIdentifier(
                    "desktop.agents.computer-use.open-screen-recording"
                )
            }
            if permissionNeedsGrant(computerStatus.accessibilityPermission) {
                Button("Open Accessibility") {
                    openComputerUsePermissionPane("Privacy_Accessibility")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .accessibilityIdentifier(
                    "desktop.agents.computer-use.open-accessibility"
                )
            }
            Button("Refresh") {
                Task {
                    await viewModel.refreshAgentOperationsForOperator()
                }
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.small)
            .accessibilityIdentifier(
                "desktop.agents.computer-use.refresh-permissions"
            )
        }
        .padding(10)
        .background(
            MelixDesignTokens.StatusColor.warning.opacity(0.08),
            in: RoundedRectangle(cornerRadius: 10)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(
                    MelixDesignTokens.StatusColor.warning.opacity(0.24),
                    lineWidth: 1
                )
        )
    }

    private var computerRestartRepair: some View {
        HStack(alignment: .center, spacing: 9) {
            Image(systemName: "arrow.clockwise.circle")
                .foregroundStyle(MelixDesignTokens.StatusColor.warning)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text("Computer Use permission is ready after restart")
                    .font(.caption.weight(.semibold))
                Text("Quit the full Melix stack now, then reopen Melix so the broker can adopt the new macOS permission.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            Button("Quit Melix") {
                MelixMenuBarApp.requestPermissionRestart()
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.small)
            .accessibilityIdentifier(
                "desktop.agents.computer-use.quit-for-restart"
            )
        }
        .padding(10)
        .background(
            MelixDesignTokens.StatusColor.warning.opacity(0.08),
            in: RoundedRectangle(cornerRadius: 10)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(
                    MelixDesignTokens.StatusColor.warning.opacity(0.24),
                    lineWidth: 1
                )
        )
    }

    private var computerProbeRepair: some View {
        HStack(alignment: .center, spacing: 9) {
            Image(systemName: "questionmark.diamond")
                .foregroundStyle(MelixDesignTokens.StatusColor.warning)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text("Computer Use status unavailable")
                    .font(.caption.weight(.semibold))
                Text("Melix could not verify one or more macOS permissions. Retry the live probe and review the runtime inventory below; do not open Settings unless the probe reports denied or not requested.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            Button("Retry Probe") {
                Task {
                    await viewModel.refreshAgentOperationsForOperator()
                }
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.small)
            .accessibilityIdentifier(
                "desktop.agents.computer-use.retry-probe"
            )
        }
        .padding(10)
        .background(
            MelixDesignTokens.StatusColor.warning.opacity(0.08),
            in: RoundedRectangle(cornerRadius: 10)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(
                    MelixDesignTokens.StatusColor.warning.opacity(0.24),
                    lineWidth: 1
                )
        )
    }

    private var computerTargetDiscoveryRepair: some View {
        HStack(alignment: .center, spacing: 9) {
            Image(systemName: "exclamationmark.triangle")
                .foregroundStyle(MelixDesignTokens.StatusColor.warning)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text("Computer Use window refresh failed")
                    .font(.caption.weight(.semibold))
                Text(
                    viewModel.canRetryComputerUseTargetDiscovery
                        ? "Melix could not refresh the live window list. Retry before starting an Agent run; this is different from having no eligible windows."
                        : "Melix received an invalid window-discovery response. Review the runtime inventory before starting an Agent run."
                )
                .font(.caption2)
                .foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            Button("Retry Window Refresh") {
                Task {
                    await viewModel.refreshAgentOperationsForOperator()
                }
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.small)
            .accessibilityIdentifier(
                "desktop.agents.computer-use.retry-target-discovery"
            )
        }
        .padding(10)
        .background(
            MelixDesignTokens.StatusColor.warning.opacity(0.08),
            in: RoundedRectangle(cornerRadius: 10)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(
                    MelixDesignTokens.StatusColor.warning.opacity(0.24),
                    lineWidth: 1
                )
        )
    }

    private func openComputerUsePermissionPane(_ pane: String) {
        guard let url = URL(
            string: "x-apple.systempreferences:com.apple.preference.security?\(pane)"
        ) else {
            return
        }
        openURL(url)
    }

    private func permissionNeedsGrant(_ state: String) -> Bool {
        ["denied", "not_determined"].contains(state)
    }

    private var runtimeInventory: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 8) {
                Label("Runtime Inventory", systemImage: "shippingbox")
                    .font(.callout.weight(.semibold))
                Text(viewModel.agentOperationsStatusText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                Spacer()
                Button {
                    Task {
                        await viewModel.refreshAgentOperationsForOperator()
                    }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .help("Refresh live Agent runtime inventory")
                .accessibilityLabel("Refresh live Agent runtime inventory")
            }

            HStack(alignment: .top, spacing: 10) {
                runtimeSourceList
                runtimeToolList
            }
        }
        .padding(11)
        .background(
            Color(nsColor: .controlBackgroundColor).opacity(0.55),
            in: RoundedRectangle(cornerRadius: 10)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(
                    Color.primary.opacity(MelixDesignTokens.StrokeOpacity.hairline),
                    lineWidth: 1
                )
        )
    }

    private var runtimeSourceList: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Sources")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            if viewModel.agentOperations.toolSources.isEmpty {
                Text("No source receipt available.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 5) {
                        ForEach(
                            viewModel.agentOperations.toolSources,
                            id: \.sourceID
                        ) { source in
                            HStack(spacing: 7) {
                                Circle()
                                    .fill(sourceStateColor(source.connectionState))
                                    .frame(width: 6, height: 6)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(source.sourceID)
                                        .font(.caption.weight(.medium))
                                        .lineLimit(1)
                                    Text(sourceSummary(source))
                                        .font(.caption2.monospaced())
                                        .foregroundStyle(.secondary)
                                        .lineLimit(1)
                                }
                                Spacer(minLength: 4)
                                Text("\(source.toolCount)")
                                    .font(.caption2.monospacedDigit())
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                .frame(maxHeight: 104)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var runtimeToolList: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Callable Tools")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            if viewModel.agentOperations.tools.isEmpty {
                Text("No callable tool schema available.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 5) {
                        ForEach(
                            Array(viewModel.agentOperations.tools.indices),
                            id: \.self
                        ) { index in
                            let tool = viewModel.agentOperations.tools[index]
                            HStack(spacing: 7) {
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(tool.name)
                                        .font(.caption.weight(.medium))
                                        .lineLimit(1)
                                    Text("\(tool.sourceID) · \(tool.adapterKind) · \(tool.riskClass)")
                                        .font(.caption2.monospaced())
                                        .foregroundStyle(.secondary)
                                        .lineLimit(1)
                                }
                                Spacer(minLength: 4)
                                Text(String(tool.schemaDigest.prefix(8)))
                                    .font(.caption2.monospaced())
                                    .foregroundStyle(.tertiary)
                            }
                        }
                    }
                }
                .frame(maxHeight: 104)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func sourceSummary(
        _ source: Melix_Controlplane_V1_AgentToolSourceStatus
    ) -> String {
        var parts = [source.connectionState, source.transportKind]
            .filter { !$0.isEmpty }
        if source.catalogOnly {
            parts.append("non-executable")
        }
        if !source.errorCode.isEmpty {
            parts.append(source.errorCode)
        }
        return parts.isEmpty ? "unknown" : parts.joined(separator: " · ")
    }

    private func sourceStateColor(_ state: String) -> Color {
        switch state {
        case "ready", "live": MelixDesignTokens.StatusColor.success
        case "catalog_only", "disabled": .secondary
        case "failed", "blocked", "unavailable":
            MelixDesignTokens.StatusColor.error
        default: MelixDesignTokens.StatusColor.warning
        }
    }

    private func permissionLabel(_ state: String) -> String {
        switch state {
        case "granted": "granted"
        case "denied": "denied"
        case "not_determined": "not requested"
        case "restart_required": "restart required"
        case "unavailable": "unavailable"
        default: "unknown"
        }
    }

    private var approvalPolicies: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 8) {
                Label("Saved Approval Policies", systemImage: "checkmark.shield")
                    .font(.callout.weight(.semibold))
                Text("Revision \(viewModel.agentApprovalPolicy.revision)")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
                Spacer()
                if viewModel.agentApprovalPolicyStatusText.isEmpty == false {
                    Text(viewModel.agentApprovalPolicyStatusText)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Button {
                    Task {
                        await viewModel.refreshAgentApprovalPolicyForOperator()
                    }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .disabled(viewModel.agentApprovalPolicyMutationInProgress)
                .help("Refresh saved approval policies")
                .accessibilityLabel("Refresh saved approval policies")
            }

            if viewModel.agentApprovalPolicy.rules.isEmpty {
                Text(
                    "No saved overrides. Risk defaults remain active. Use Always Allow This Tool only from a bound approval card."
                )
                .font(.caption)
                .foregroundStyle(.secondary)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 7) {
                        ForEach(viewModel.agentApprovalPolicy.rules, id: \.id) { rule in
                            approvalPolicyRow(rule)
                        }
                    }
                }
                .frame(maxHeight: 170)
            }
        }
        .padding(11)
        .background(
            Color(nsColor: .controlBackgroundColor).opacity(0.55),
            in: RoundedRectangle(cornerRadius: 10)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(
                    Color.primary.opacity(MelixDesignTokens.StrokeOpacity.hairline),
                    lineWidth: 1
                )
        )
    }

    private func approvalPolicyRow(
        _ rule: Melix_Controlplane_V1_AgentApprovalPolicyRule
    ) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text(policyEffectLabel(rule.effect))
                .font(.caption2.weight(.semibold))
                .foregroundStyle(policyEffectColor(rule.effect))
                .padding(.horizontal, 7)
                .padding(.vertical, 4)
                .background(
                    policyEffectColor(rule.effect).opacity(0.1),
                    in: Capsule()
                )

            VStack(alignment: .leading, spacing: 3) {
                Text(policyPrimaryScope(rule))
                    .font(.caption.weight(.semibold))
                    .textSelection(.enabled)
                Text(policySecondaryScope(rule))
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                    .lineLimit(2)
            }

            Spacer(minLength: 8)

            Button("Revoke", role: .destructive) {
                Task {
                    await viewModel.revokeAgentApprovalPolicyRule(id: rule.id)
                }
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .disabled(viewModel.agentApprovalPolicyMutationInProgress)
            .help("Revoke this saved policy; future matching calls return to risk defaults")
            .accessibilityLabel("Revoke saved policy for \(policyPrimaryScope(rule))")
        }
        .padding(8)
        .background(
            Color.secondary.opacity(0.045),
            in: RoundedRectangle(cornerRadius: 8)
        )
    }

    private func policyEffectLabel(
        _ effect: Melix_Controlplane_V1_AgentApprovalPolicyEffect
    ) -> String {
        switch effect {
        case .agentApprovalPolicyAllow: "Allow"
        case .agentApprovalPolicyAsk: "Ask"
        case .agentApprovalPolicyDeny: "Deny"
        case .unspecified, .UNRECOGNIZED: "Unknown"
        }
    }

    private func policyEffectColor(
        _ effect: Melix_Controlplane_V1_AgentApprovalPolicyEffect
    ) -> Color {
        switch effect {
        case .agentApprovalPolicyAllow: MelixDesignTokens.StatusColor.success
        case .agentApprovalPolicyAsk: MelixDesignTokens.StatusColor.warning
        case .agentApprovalPolicyDeny: MelixDesignTokens.StatusColor.error
        case .unspecified, .UNRECOGNIZED: .secondary
        }
    }

    private func policyPrimaryScope(
        _ rule: Melix_Controlplane_V1_AgentApprovalPolicyRule
    ) -> String {
        let source = rule.sourceID.isEmpty ? "Any source" : rule.sourceID
        let tool = rule.toolName.isEmpty ? "any tool" : rule.toolName
        return "\(source) · \(tool)"
    }

    private func policySecondaryScope(
        _ rule: Melix_Controlplane_V1_AgentApprovalPolicyRule
    ) -> String {
        var parts: [String] = [
            "risk \(policyRiskLabel(rule.riskClass))",
            "operation \(policyOperationLabel(rule.operationKind))",
        ]
        if rule.schemaDigest.isEmpty == false {
            parts.append("schema \(String(rule.schemaDigest.prefix(12)))")
        }
        if rule.workspaceScope.isEmpty == false {
            parts.append("workspace \(rule.workspaceScope)")
        }
        if rule.appBundleID.isEmpty == false {
            parts.append("app \(rule.appBundleID)")
        }
        if rule.networkHost.isEmpty == false {
            parts.append("host \(rule.networkHost)")
        }
        if parts.isEmpty {
            parts.append("Default match scope")
        }
        return parts.joined(separator: " · ")
    }

    private func policyRiskLabel(
        _ risk: Melix_Controlplane_V1_AgentApprovalRiskClass
    ) -> String {
        switch risk {
        case .low: "low"
        case .medium: "medium"
        case .high: "high"
        case .critical: "critical"
        case .unknown, .unspecified, .UNRECOGNIZED:
            "unknown"
        }
    }

    private func policyOperationLabel(
        _ operation: Melix_Controlplane_V1_AgentApprovalOperationKind
    ) -> String {
        switch operation {
        case .agentApprovalOperationRead: "read"
        case .agentApprovalOperationWrite: "write"
        case .agentApprovalOperationCredentialAccess: "credential access"
        case .agentApprovalOperationAuthentication: "authentication"
        case .agentApprovalOperationUpload: "upload"
        case .agentApprovalOperationSend: "send"
        case .agentApprovalOperationPurchase: "purchase"
        case .agentApprovalOperationDestructiveMutation:
            "destructive mutation"
        case .agentApprovalOperationProcessExecution: "process execution"
        case .agentApprovalOperationSecureFieldInteraction:
            "secure field interaction"
        case .agentApprovalOperationUnknown, .unspecified, .UNRECOGNIZED:
            "unknown"
        }
    }
}

private struct DesktopAgentOperationsCard: View {
    let title: String
    let value: String
    let detail: String
    let systemImage: String
    let isReady: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 6) {
                Image(systemName: systemImage)
                    .foregroundStyle(isReady ? MelixDesignTokens.accent : Color.secondary)
                Text(title)
                    .font(.caption.weight(.semibold))
                Spacer(minLength: 0)
            }
            Text(value)
                .font(.callout.weight(.semibold))
            Text(detail)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(10)
        .frame(maxWidth: .infinity, minHeight: 96, alignment: .topLeading)
        .background(
            Color.secondary.opacity(0.05),
            in: RoundedRectangle(cornerRadius: 9)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 9)
                .stroke(
                    Color.primary.opacity(MelixDesignTokens.StrokeOpacity.hairline),
                    lineWidth: 1
                )
        )
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(title), \(value). \(detail)")
    }
}

@MainActor
private struct DesktopAgentRunRow: View {
    let viewModel: RuntimeViewModel
    let run: Melix_Controlplane_V1_AgentRunSnapshot
    let isSelected: Bool

    var body: some View {
        Button {
            viewModel.selectAgentRun(id: run.runID)
        } label: {
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 7) {
                    Circle()
                        .fill(stateColor)
                        .frame(width: 7, height: 7)
                    Text(viewModel.agentStateDisplayName(run.state))
                        .font(.caption.weight(.semibold))
                    Spacer(minLength: 4)
                    Text("\(run.toolCallCount) tools")
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
                Text(run.modelID.isEmpty ? "Unknown model" : run.modelID)
                    .font(.caption)
                    .lineLimit(1)
                Text(run.runID)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.tertiary)
                    .lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(10)
        .melixSelection(isSelected)
        .accessibilityLabel(
            "\(viewModel.agentStateDisplayName(run.state)) Agent run, \(run.toolCallCount) tools"
        )
    }

    private var stateColor: Color {
        switch run.state {
        case "completed":
            return MelixDesignTokens.StatusColor.success
        case "failed":
            return MelixDesignTokens.StatusColor.error
        case "cancelled":
            return .secondary
        case "waiting_for_approval":
            return MelixDesignTokens.StatusColor.warning
        default:
            return MelixDesignTokens.accent
        }
    }
}

@MainActor
private struct DesktopAgentRunDetailView: View {
    let viewModel: RuntimeViewModel
    let run: Melix_Controlplane_V1_AgentRunSnapshot

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                header
                runFailure
                capabilitySummary
                timeline
                cancellationReceipt
            }
            .frame(maxWidth: 920, alignment: .leading)
            .padding(22)
            .frame(maxWidth: .infinity, alignment: .center)
        }
    }

    @ViewBuilder
    private var runFailure: some View {
        if run.state == "failed", !run.error.code.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Label(
                    run.failureStage.isEmpty
                        ? "Run Failure"
                        : "Run Failure · \(run.failureStage)",
                    systemImage: "exclamationmark.triangle"
                )
                .font(.headline)
                .foregroundStyle(MelixDesignTokens.StatusColor.error)
                Text(run.error.code)
                    .font(.caption.monospaced())
                    .textSelection(.enabled)
                if !run.error.message.isEmpty {
                    Text(run.error.message)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                MelixDesignTokens.StatusColor.error.opacity(0.08),
                in: RoundedRectangle(cornerRadius: 10)
            )
        }
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 10)
                    .fill(MelixDesignTokens.accent.opacity(0.12))
                Image(systemName: "bolt.horizontal.circle")
                    .font(.title2)
                    .foregroundStyle(MelixDesignTokens.accent)
            }
            .frame(width: 44, height: 44)

            VStack(alignment: .leading, spacing: 5) {
                Text("Agent Run")
                    .font(.title2.weight(.semibold))
                Text(run.runID)
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                HStack(spacing: 10) {
                    Label(
                        viewModel.agentStateDisplayName(run.state),
                        systemImage: "circle.fill"
                    )
                    Text(run.modelID)
                    Text("\(run.modelTurnCount) turns")
                    Text("\(run.toolCallCount) tools")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }

            Spacer()

            if ["created", "model_turn", "waiting_for_approval", "tool_running"].contains(run.state) {
                Button("Stop", role: .destructive) {
                    Task {
                        await viewModel.stopAgentRun(runID: run.runID)
                    }
                }
                .buttonStyle(.bordered)
            }
        }
    }

    private var capabilitySummary: some View {
        HStack(alignment: .top, spacing: 12) {
            DesktopAgentSummaryCard(
                title: "Tool Sources",
                value: sourceSummary,
                detail: "Live sources are discovered by the control plane and executed by the worker.",
                systemImage: "wrench.and.screwdriver"
            )
            DesktopAgentSummaryCard(
                title: "Approval Policy",
                value: run.hasPendingApproval ? "Decision required" : "Evaluated",
                detail: "New chats start at Ask. Always Allow This Tool is scoped to this session and branch.",
                systemImage: "checkmark.shield"
            )
            DesktopAgentSummaryCard(
                title: "Computer Use · Semantic Press",
                value: computerUseSummary,
                detail: "Live permission probe; only window capture and approved semantic press are advertised.",
                systemImage: "macwindow"
            )
        }
    }

    private var computerUseSummary: String {
        let status = viewModel.agentOperations.computerUse
        guard status.brokerConfigured else {
            return "Not configured"
        }
        guard status.capabilityLevel == "ax_semantic_press_only" else {
            return "Probe unavailable"
        }
        if status.screenRecordingPermission == "granted",
           status.accessibilityPermission == "granted" {
            return "Permissions ready"
        }
        return "Permission needed"
    }

    @ViewBuilder
    private var timeline: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Tool Timeline")
                .font(.headline)

            if run.toolCalls.isEmpty {
                Text("No tool calls were requested.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 12)
            } else {
                ForEach(run.toolCalls, id: \.callID) { tool in
                    DesktopAgentToolTimelineCard(
                        viewModel: viewModel,
                        tool: tool
                    )
                }
            }

            if run.assistantText.isEmpty == false {
                VStack(alignment: .leading, spacing: 6) {
                    Text(run.state == "completed" ? "Final response" : "Live response")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    Text(run.assistantText)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(12)
                .background(
                    Color.secondary.opacity(0.055),
                    in: RoundedRectangle(cornerRadius: 10)
                )
            }
        }
    }

    @ViewBuilder
    private var cancellationReceipt: some View {
        if let receipt = viewModel.agentCancellationReceipt(for: run.runID) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Cancellation Receipt")
                    .font(.headline)
                Text(receipt.cancellationID)
                    .font(.caption.monospaced())
                    .textSelection(.enabled)
                HStack(spacing: 12) {
                    Text(receipt.disposition)
                    Text(
                        RuntimeViewModel.agentCancellationSideEffectSummary(
                            receipt
                        )
                    )
                    if receipt.hasTool {
                        Text(receipt.tool.adapterKind)
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            .padding(12)
            .background(
                Color.secondary.opacity(0.055),
                in: RoundedRectangle(cornerRadius: 10)
            )
        }
    }

    private var sourceSummary: String {
        let sources = Set(run.toolCalls.map(\.sourceID).filter { $0.isEmpty == false })
        return sources.isEmpty ? "No calls" : sources.sorted().joined(separator: ", ")
    }
}

private struct DesktopAgentSummaryCard: View {
    let title: String
    let value: String
    let detail: String
    let systemImage: String

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Label(title, systemImage: systemImage)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.headline)
            Text(detail)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 118, alignment: .topLeading)
        .background(
            Color.secondary.opacity(0.055),
            in: RoundedRectangle(cornerRadius: 10)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(
                    Color.primary.opacity(MelixDesignTokens.StrokeOpacity.hairline),
                    lineWidth: 1
                )
        )
    }
}

@MainActor
private struct DesktopAgentToolTimelineCard: View {
    let viewModel: RuntimeViewModel
    let tool: Melix_Controlplane_V1_AgentToolCallSnapshot

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Image(systemName: tool.sourceID == "computer" ? "macwindow" : "wrench.and.screwdriver")
                    .foregroundStyle(MelixDesignTokens.accent)
                Text(tool.title.isEmpty ? tool.toolName : tool.title)
                    .font(.headline)
                Spacer()
                Text(viewModel.agentToolStateDisplayName(tool.state))
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(toolStateColor)
            }

            Text(tool.intendedEffect.isEmpty ? "No intended effect was provided." : tool.intendedEffect)
                .font(.callout)
                .foregroundStyle(.secondary)

            HStack(spacing: 12) {
                Text(tool.sourceID)
                Text(tool.riskClass.isEmpty ? "risk unknown" : tool.riskClass)
                if tool.durationMs > 0 {
                    Text("\(tool.durationMs, format: .number.precision(.fractionLength(0))) ms")
                }
            }
            .font(.caption2.monospaced())
            .foregroundStyle(.tertiary)

            if tool.evidenceReference.isEmpty == false {
                Text(tool.evidenceReference)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                    .lineLimit(2)
            }

            if !tool.resultSummary.isEmpty {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Result summary")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    Text(tool.resultSummary)
                        .font(.caption)
                        .textSelection(.enabled)
                    if tool.resultTruncated {
                        Label(
                            "Result was truncated at a typed runtime boundary.",
                            systemImage: "scissors"
                        )
                        .font(.caption2)
                        .foregroundStyle(MelixDesignTokens.StatusColor.warning)
                    }
                }
            }

            if let issue = desktopAgentToolIssuePresentation(for: tool) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(issue.title)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(issueColor(issue.tone))
                    Text(tool.error.code)
                        .font(.caption2.monospaced())
                        .textSelection(.enabled)
                    if !tool.error.message.isEmpty {
                        Text(tool.error.message)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                    }
                }
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(
                    issueColor(issue.tone).opacity(0.07),
                    in: RoundedRectangle(cornerRadius: 7)
                )
            }
        }
        .padding(12)
        .background(
            Color(nsColor: .controlBackgroundColor).opacity(0.55),
            in: RoundedRectangle(cornerRadius: 10)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(
                    Color.primary.opacity(MelixDesignTokens.StrokeOpacity.hairline),
                    lineWidth: 1
                )
        )
    }

    private var toolStateColor: Color {
        switch tool.state {
        case "completed":
            return MelixDesignTokens.StatusColor.success
        case "failed":
            return MelixDesignTokens.StatusColor.error
        case "waiting_for_approval":
            return MelixDesignTokens.StatusColor.warning
        default:
            return .secondary
        }
    }

    private func issueColor(_ tone: DesktopAgentToolIssueTone) -> Color {
        switch tone {
        case .warning:
            return MelixDesignTokens.StatusColor.warning
        case .error:
            return MelixDesignTokens.StatusColor.error
        }
    }
}

enum DesktopAgentToolIssueTone: Equatable {
    case warning
    case error
}

struct DesktopAgentToolIssuePresentation: Equatable {
    let title: String
    let tone: DesktopAgentToolIssueTone
}

func desktopAgentToolIssuePresentation(
    for tool: Melix_Controlplane_V1_AgentToolCallSnapshot
) -> DesktopAgentToolIssuePresentation? {
    guard !tool.error.code.isEmpty else {
        return nil
    }
    if tool.state == "completed",
       tool.failureStage.isEmpty,
       tool.error.code == "agent_tool_evidence_unavailable" {
        return DesktopAgentToolIssuePresentation(
            title: "Evidence unavailable",
            tone: .warning
        )
    }
    return DesktopAgentToolIssuePresentation(
        title: tool.failureStage.isEmpty
            ? "Tool failure"
            : "Tool failure · \(tool.failureStage)",
        tone: .error
    )
}
