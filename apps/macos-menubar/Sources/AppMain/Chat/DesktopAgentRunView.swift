import MelixControlPlaneProtocol
import SwiftUI

struct DesktopChatAgentModeBarControls: Equatable {
    let showsReviewAgents: Bool
    let showsStop: Bool
    let showsCheckingStatus: Bool
    let showsRetryStatus: Bool
}

@MainActor
func desktopChatAgentModeBarControls(
    for viewModel: RuntimeViewModel
) -> DesktopChatAgentModeBarControls {
    if viewModel.agentRunConflictRunIDs.isEmpty == false {
        return DesktopChatAgentModeBarControls(
            showsReviewAgents: true,
            showsStop: viewModel.canStopActiveChatOrAgent,
            showsCheckingStatus: false,
            showsRetryStatus: false
        )
    }
    return DesktopChatAgentModeBarControls(
        showsReviewAgents: false,
        showsStop: viewModel.canStopActiveChatOrAgent,
        showsCheckingStatus:
            viewModel.isAgentRunReconciliationBlocking
                && viewModel.agentRunReconciliationNeedsRetry == false,
        showsRetryStatus: viewModel.agentRunReconciliationNeedsRetry
    )
}

@MainActor
struct DesktopChatAgentModeBar: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        let controls = desktopChatAgentModeBarControls(for: viewModel)
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                Picker(
                    "Interaction Mode",
                    selection: Binding(
                        get: { viewModel.chatInteractionMode },
                        set: { viewModel.setChatInteractionMode($0) }
                    )
                ) {
                    ForEach(DesktopChatInteractionMode.allCases) { mode in
                        Label(mode.rawValue, systemImage: mode.systemImageName)
                            .tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                .frame(width: 178)
                .disabled(viewModel.isChatBusy)
                .help(
                    viewModel.chatInteractionMode == .ask
                        ? "Ask answers without executing tools."
                        : "Act can call approved tools and continue until the task is complete."
                )
                .accessibilityHint(
                    "Ask never executes tools. Act enables the realtime Agent runtime."
                )

                if viewModel.chatInteractionMode == .act {
                    DesktopAgentCapabilityBadge(
                        capability: viewModel.selectedAgentProviderCapability
                    )
                    ForEach(viewModel.agentCapabilityRows) { capability in
                        DesktopAgentCapabilityBadge(capability: capability)
                    }
                }

                Spacer(minLength: 8)

                if controls.showsReviewAgents {
                    Button("Review Agents") {
                        viewModel.selectSurface(.agents)
                    }
                    .buttonStyle(.bordered)
                    .help("Review each active run before continuing in Chat")
                }
                if controls.showsStop {
                    Button("Stop", role: .destructive) {
                        Task {
                            await viewModel.stopActiveChatOrAgent()
                        }
                    }
                    .buttonStyle(.bordered)
                    .help("Request backend cancellation and wait for a typed receipt")
                    .accessibilityHint("Stops the active response, tool call, or Agent run.")
                }
                if controls.showsCheckingStatus {
                    Label(
                        "Checking Agent Status",
                        systemImage: "arrow.triangle.2.circlepath"
                    )
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .accessibilityLabel("Checking Agent status")
                }
                if controls.showsRetryStatus {
                    Button("Retry Agent Status") {
                        Task {
                            await viewModel.refreshAgentRunsForOperator()
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .help("Retry the authoritative Agent history refresh")
                }
            }

            if viewModel.chatInteractionMode == .act,
               viewModel.agentOperations.computerUse.brokerConfigured {
                DesktopComputerTargetPicker(viewModel: viewModel)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

@MainActor
private struct DesktopComputerTargetPicker: View {
    let viewModel: RuntimeViewModel

    private var selection: Binding<String> {
        Binding(
            get: { viewModel.selectedComputerUseTargetID },
            set: { viewModel.selectComputerUseTarget(id: $0) }
        )
    }

    var body: some View {
        HStack(spacing: 8) {
            Label("Computer target", systemImage: "macwindow")
                .font(.caption.weight(.semibold))
            Picker("Computer target", selection: selection) {
                Text("No window selected").tag("")
                ForEach(viewModel.availableComputerUseTargets, id: \.targetID) { target in
                    Text(targetLabel(target)).tag(target.targetID)
                }
            }
            .labelsHidden()
            .pickerStyle(.menu)
            .controlSize(.small)
            .frame(maxWidth: 340)
            .disabled(viewModel.isChatBusy || viewModel.availableComputerUseTargets.isEmpty)
            .help(
                "Choose one live window. Melix freezes its app, process launch, and window identity into the next Agent run."
            )
            .accessibilityIdentifier("desktop.chat.computer-target-picker")

            Button {
                Task {
                    await viewModel.refreshAgentOperationsForOperator()
                }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.plain)
            .disabled(viewModel.isChatBusy)
            .help("Refresh live Computer Use windows")
            .accessibilityLabel("Refresh Computer Use windows")

            if viewModel.isComputerUseTargetDiscoveryFailed {
                Text(viewModel.computerUseTargetDiscoveryStatusText)
                    .font(.caption2)
                    .foregroundStyle(MelixDesignTokens.StatusColor.warning)
                    .accessibilityIdentifier(
                        "desktop.chat.computer-target-discovery-failed"
                    )
            } else if viewModel.availableComputerUseTargets.isEmpty {
                Text(viewModel.computerUseTargetDiscoveryStatusText)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .accessibilityIdentifier(
                        "desktop.chat.computer-target-discovery-status"
                    )
            } else if viewModel.selectedComputerUseTarget == nil {
                Text("Computer Use stays unavailable until you choose a window")
                    .font(.caption2)
                    .foregroundStyle(MelixDesignTokens.StatusColor.warning)
            } else {
                Text("Scope freezes when you send")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 7)
        .background(
            Color.secondary.opacity(0.045),
            in: RoundedRectangle(cornerRadius: 8)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(
                    Color.primary.opacity(MelixDesignTokens.StrokeOpacity.hairline),
                    lineWidth: 1
                )
        )
    }

    private func targetLabel(
        _ target: Melix_Controlplane_V1_AgentComputerUseTarget
    ) -> String {
        let app = target.applicationName.isEmpty
            ? target.bundleID
            : target.applicationName
        let window = target.windowTitle.isEmpty
            ? "Window \(target.windowID)"
            : target.windowTitle
        return "\(app) — \(window)"
    }
}

private struct DesktopAgentCapabilityBadge: View {
    let capability: DesktopChatCapabilityRow

    var body: some View {
        Label(capability.shortTitle, systemImage: capability.systemImageName)
            .font(.caption2.weight(.medium))
            .foregroundStyle(capability.isReady ? MelixDesignTokens.accent : Color.secondary)
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(
                capability.isReady
                    ? MelixDesignTokens.accent.opacity(0.09)
                    : Color.secondary.opacity(0.055),
                in: Capsule()
            )
            .overlay(
                Capsule()
                    .stroke(
                        Color.primary.opacity(MelixDesignTokens.StrokeOpacity.hairline),
                        lineWidth: 1
                    )
            )
            .help(
                "\(capability.title) · \(capability.isReady ? "Ready" : "Unavailable") · \(capability.detail)"
            )
            .accessibilityLabel(capability.title)
            .accessibilityValue(capability.isReady ? "Ready" : "Unavailable")
    }
}

@MainActor
struct DesktopAgentLiveRunCard: View {
    let viewModel: RuntimeViewModel
    let run: Melix_Controlplane_V1_AgentRunSnapshot?
    @State private var approvalArgumentsExpanded = false

    init(
        viewModel: RuntimeViewModel,
        run: Melix_Controlplane_V1_AgentRunSnapshot? = nil
    ) {
        self.viewModel = viewModel
        self.run = run
    }

    var body: some View {
        if let run = run ?? viewModel.currentChatAgentRun {
            VStack(alignment: .leading, spacing: 12) {
                header(run)

                if run.toolCalls.isEmpty == false {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(run.toolCalls, id: \.callID) { tool in
                            toolRow(tool)
                        }
                    }
                }

                if run.hasPendingApproval {
                    approvalCard(run.pendingApproval)
                }

                if let receipt = viewModel.agentApprovalDecisionReceipt(
                    for: run.runID
                ) {
                    approvalOutcome(receipt)
                }

                if let receipt = viewModel.agentCancellationReceipt(
                    for: run.runID
                ) {
                    cancellationOutcome(receipt)
                }

                if isCurrentLiveRun(run),
                   let session = viewModel.currentComputerUseSessionPresentation {
                    computerUseControls(session)
                } else if isCurrentLiveRun(run),
                          viewModel.shouldDisplayActiveComputerUseControlStatus {
                    computerUseReceiptStatus
                }

                if run.assistantText.isEmpty == false,
                   isCurrentLiveRun(run) {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("Live response")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)
                        Text(run.assistantText)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .padding(.top, 2)
                }
            }
            .padding(13)
            .background(
                Color.secondary.opacity(0.05),
                in: RoundedRectangle(cornerRadius: 12)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(
                        run.hasPendingApproval
                            ? MelixDesignTokens.StatusColor.warning.opacity(0.65)
                            : MelixDesignTokens.accent.opacity(0.24),
                        lineWidth: run.hasPendingApproval ? 1.5 : 1
                    )
            )
            .accessibilityElement(children: .contain)
            .accessibilityLabel(
                "Agent run \(viewModel.agentStateDisplayName(run.state))"
            )
        }
    }

    private func header(
        _ run: Melix_Controlplane_V1_AgentRunSnapshot
    ) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 9) {
            Image(systemName: "bolt.horizontal.circle.fill")
                .foregroundStyle(MelixDesignTokens.accent)
            Text("Melix Agent")
                .font(.headline)
            Text(viewModel.agentStateDisplayName(run.state))
                .font(.caption.weight(.semibold))
                .foregroundStyle(stateColor(run.state))
            Spacer()
            Text("\(run.modelTurnCount) turns · \(run.toolCallCount) tools")
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
        }
    }

    private func toolRow(
        _ tool: Melix_Controlplane_V1_AgentToolCallSnapshot
    ) -> some View {
        HStack(alignment: .top, spacing: 9) {
            Image(
                systemName: tool.sourceID == "computer"
                    ? "macwindow"
                    : "wrench.and.screwdriver"
            )
            .frame(width: 18)
            .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 7) {
                    Text(tool.title.isEmpty ? tool.toolName : tool.title)
                        .font(.callout.weight(.semibold))
                    Text(viewModel.agentToolStateDisplayName(tool.state))
                        .font(.caption2.weight(.medium))
                        .foregroundStyle(toolStateColor(tool.state))
                }
                if tool.intendedEffect.isEmpty == false {
                    Text(tool.intendedEffect)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                HStack(spacing: 9) {
                    Text(tool.sourceID)
                    Text("tool \(tool.toolName)")
                    if tool.riskClass.isEmpty == false {
                        Text(tool.riskClass)
                    }
                    if tool.durationMs > 0 {
                        Text("\(tool.durationMs, format: .number.precision(.fractionLength(0))) ms")
                    }
                }
                .font(.caption2.monospaced())
                .foregroundStyle(.tertiary)

                if isTerminalTool(tool) {
                    toolTerminalDetails(tool)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(9)
        .background(
            Color(nsColor: .controlBackgroundColor).opacity(0.56),
            in: RoundedRectangle(cornerRadius: 8)
        )
        .accessibilityElement(children: .contain)
        .accessibilityLabel(
            "Agent tool \(tool.title.isEmpty ? tool.toolName : tool.title)"
        )
        .accessibilityValue(
            viewModel.agentToolStateDisplayName(tool.state)
        )
    }

    @ViewBuilder
    private func toolTerminalDetails(
        _ tool: Melix_Controlplane_V1_AgentToolCallSnapshot
    ) -> some View {
        if !tool.resultSummary.isEmpty {
            VStack(alignment: .leading, spacing: 3) {
                Text("Result summary")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text(tool.resultSummary)
                    .font(.caption)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Tool result summary")
            .accessibilityValue(tool.resultSummary)
        }

        if tool.resultTruncated {
            Label(
                "Result truncated at the typed runtime boundary",
                systemImage: "scissors"
            )
            .font(.caption2)
            .foregroundStyle(MelixDesignTokens.StatusColor.warning)
            .accessibilityLabel("Tool result truncated")
            .accessibilityHint(
                "The visible result is the complete bounded summary returned by the backend."
            )
        }

        if !tool.evidenceReference.isEmpty {
            VStack(alignment: .leading, spacing: 3) {
                Text("Redacted evidence")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text(tool.evidenceReference)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                    .lineLimit(2)
                    .truncationMode(.middle)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .help(tool.evidenceReference)
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel("Redacted tool evidence reference")
            .accessibilityValue(tool.evidenceReference)
        }

        if let issue = desktopAgentToolIssuePresentation(for: tool) {
            VStack(alignment: .leading, spacing: 4) {
                Text(issue.title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(toolIssueColor(issue.tone))
                if !tool.failureStage.isEmpty {
                    labeledToolDetail("Failure stage", tool.failureStage)
                }
                labeledToolDetail("Error code", tool.error.code)
                if !tool.error.message.isEmpty {
                    Text(tool.error.message)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(7)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                toolIssueColor(issue.tone).opacity(0.07),
                in: RoundedRectangle(cornerRadius: 7)
            )
            .accessibilityElement(children: .contain)
            .accessibilityLabel(issue.title)
            .accessibilityValue(
                [tool.failureStage, tool.error.code, tool.error.message]
                    .filter { !$0.isEmpty }
                    .joined(separator: ", ")
            )
        }
    }

    private func labeledToolDetail(
        _ label: String,
        _ value: String
    ) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text(label)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption2.monospaced())
                .textSelection(.enabled)
        }
        .accessibilityElement(children: .combine)
    }

    private func approvalCard(
        _ approval: Melix_Controlplane_V1_AgentPendingApproval
    ) -> some View {
        let alwaysAllowEligible = approval.persistentAllowEligible
        let alwaysAllowUnavailableReason = approval
            .persistentAllowUnavailableReason.isEmpty
            ? "Always Allow is unavailable for this approval. You can still allow this call once."
            : approval.persistentAllowUnavailableReason
        return VStack(alignment: .leading, spacing: 9) {
            Label("Approval required", systemImage: "checkmark.shield")
                .font(.headline)
                .foregroundStyle(MelixDesignTokens.StatusColor.warning)
            Text(approval.title.isEmpty ? approval.toolName : approval.title)
                .font(.callout.weight(.semibold))
            Text(
                approval.intendedEffect.isEmpty
                    ? "This tool did not provide an intended-effect summary."
                    : approval.intendedEffect
            )
            .font(.callout)
            .foregroundStyle(.secondary)
            Text(
                "source \(approval.sourceID) · tool \(approval.toolName) · risk \(approval.riskClass) · operation \(approval.operationKind.isEmpty ? "unknown" : approval.operationKind)"
            )
                .font(.caption2.monospaced())
                .foregroundStyle(.tertiary)

            Text(
                "binding \(String(approval.binding.bindingDigest.prefix(12))) · schema \(String(approval.binding.schemaDigest.prefix(12))) · policy revision \(approval.binding.policyRevision)"
            )
            .font(.caption2.monospaced())
            .foregroundStyle(.tertiary)
            .textSelection(.enabled)

            if approval.targetScopes.isEmpty == false {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Exact call targets and saved-policy scope")
                        .font(.caption.weight(.semibold))
                    ForEach(approval.targetScopes, id: \.self) { scope in
                        Text(scope)
                            .font(.caption2.monospaced())
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                    }
                }
            }

            if approval.redactedArgumentsJson.isEmpty == false {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text("Validated redacted arguments")
                            .font(.caption.weight(.semibold))
                        Spacer(minLength: 8)
                        Button(
                            approvalArgumentsExpanded
                                ? "Collapse arguments"
                                : "Expand arguments"
                        ) {
                            approvalArgumentsExpanded.toggle()
                        }
                        .buttonStyle(.plain)
                        .font(.caption)
                        .accessibilityHint(
                            approvalArgumentsExpanded
                                ? "Reduce the argument preview height."
                                : "Increase the argument preview height."
                        )
                    }
                    Text(approval.redactedArgumentsJson)
                        .font(.caption2.monospaced())
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                        .lineLimit(approvalArgumentsExpanded ? 24 : 8)
                        .truncationMode(.middle)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(8)
                    .background(
                        Color.secondary.opacity(0.055),
                        in: RoundedRectangle(cornerRadius: 7)
                    )
                    .help(approval.redactedArgumentsJson)
                    .accessibilityLabel("Validated redacted approval arguments")
                    .accessibilityValue(
                        approval.argumentsTruncated
                            ? "Backend argument preview truncated"
                            : "Complete backend argument preview"
                    )
                    if approval.argumentsTruncated {
                        Label(
                            "Backend arguments truncated at the typed runtime boundary. Deny unless the shown scope is sufficient.",
                            systemImage: "scissors"
                        )
                        .font(.caption)
                        .foregroundStyle(MelixDesignTokens.StatusColor.warning)
                        .accessibilityLabel("Backend approval arguments truncated")
                    }
                }
            }

            HStack(spacing: 8) {
                Button("Allow Once") {
                    decide(.agentApprovalAllowOnce)
                }
                .buttonStyle(.borderedProminent)
                .disabled(viewModel.agentApprovalDecisionInProgress)

                Button("Always Allow This Tool") {
                    decide(.agentApprovalAlwaysAllow)
                }
                .buttonStyle(.bordered)
                .disabled(
                    viewModel.agentApprovalDecisionInProgress
                        || !alwaysAllowEligible
                )
                .help(
                    alwaysAllowEligible
                        ? "Allow this exact tool schema for the current chat session and branch"
                        : alwaysAllowUnavailableReason
                )

                Button("Deny", role: .destructive) {
                    decide(.agentApprovalDeny)
                }
                .buttonStyle(.bordered)
                .disabled(viewModel.agentApprovalDecisionInProgress)
            }
            if !alwaysAllowEligible {
                Text(alwaysAllowUnavailableReason)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text("Saved approvals remain protected by Melix's safety floor.")
                .font(.caption2)
                .foregroundStyle(.tertiary)
        }
        .padding(11)
        .background(
            MelixDesignTokens.StatusColor.warning.opacity(0.09),
            in: RoundedRectangle(cornerRadius: 9)
        )
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Agent approval required")
    }

    private func approvalOutcome(
        _ receipt: Melix_Controlplane_V1_AgentApprovalDecisionReceipt
    ) -> some View {
        let presentation = desktopAgentApprovalOutcomePresentation(receipt)
        return VStack(alignment: .leading, spacing: 5) {
            Label(presentation.title, systemImage: "checkmark.shield")
                .font(.callout.weight(.semibold))
                .foregroundStyle(
                    presentation.isWarning
                        ? MelixDesignTokens.StatusColor.warning
                        : MelixDesignTokens.StatusColor.success
                )
            Text("Decision \(receipt.decisionID.isEmpty ? "Unavailable" : receipt.decisionID)")
                .font(.caption2.monospaced())
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
            if !presentation.errorCode.isEmpty {
                labeledOutcomeDetail("Persistence error", presentation.errorCode)
            }
            if !presentation.errorMessage.isEmpty {
                Text(presentation.errorMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(9)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            (presentation.isWarning
                ? MelixDesignTokens.StatusColor.warning
                : MelixDesignTokens.StatusColor.success).opacity(0.075),
            in: RoundedRectangle(cornerRadius: 8)
        )
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Agent approval outcome")
        .accessibilityValue(presentation.accessibilityValue)
    }

    private func cancellationOutcome(
        _ receipt: Melix_Controlplane_V1_AgentRunCancellationReceipt
    ) -> some View {
        let presentation = desktopAgentCancellationOutcomePresentation(receipt)
        return VStack(alignment: .leading, spacing: 5) {
            Label("Cancellation receipt", systemImage: "stop.circle")
                .font(.callout.weight(.semibold))
                .foregroundStyle(
                    presentation.isWarning
                        ? MelixDesignTokens.StatusColor.warning
                        : MelixDesignTokens.StatusColor.success
                )
            labeledOutcomeDetail("Outcome", presentation.disposition)
            labeledOutcomeDetail("Side effects", presentation.sideEffectState)
            if !receipt.cancellationID.isEmpty {
                labeledOutcomeDetail("Receipt", receipt.cancellationID)
            }
            Text(presentation.detail)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(9)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            (presentation.isWarning
                ? MelixDesignTokens.StatusColor.warning
                : MelixDesignTokens.StatusColor.success).opacity(0.075),
            in: RoundedRectangle(cornerRadius: 8)
        )
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Agent cancellation receipt")
        .accessibilityValue(presentation.accessibilityValue)
    }

    private func labeledOutcomeDetail(
        _ label: String,
        _ value: String
    ) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text(label)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption2.monospaced())
                .textSelection(.enabled)
        }
        .accessibilityElement(children: .combine)
    }

    private func isCurrentLiveRun(
        _ run: Melix_Controlplane_V1_AgentRunSnapshot
    ) -> Bool {
        viewModel.currentChatAgentRun?.runID == run.runID
            && viewModel.isActiveAgentRun(run)
    }

    private func computerUseControls(
        _ session: DesktopComputerUseSessionPresentation
    ) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("Computer Use", systemImage: "macwindow")
                    .font(.callout.weight(.semibold))
                Text(session.state)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(computerUseStateColor(session.state))
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(
                        computerUseStateColor(session.state).opacity(0.1),
                        in: Capsule()
                    )
                Spacer()
                if session.canStop {
                    Button("Stop", role: .destructive) {
                        Task {
                            await viewModel.stopActiveComputerUse()
                        }
                    }
                    .buttonStyle(.bordered)
                    .help(
                        "Cancel the Agent run, then inspect the typed cancellation receipt"
                    )
                }
            }

            VStack(alignment: .leading, spacing: 5) {
                Text(session.targetHeading)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                if session.targets.isEmpty {
                    Text("Unavailable")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(session.targets) { target in
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(target.app)
                                .font(.caption.monospaced())
                                .lineLimit(1)
                            Text(target.window)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                            Spacer(minLength: 0)
                        }
                        .accessibilityElement(children: .combine)
                    }
                    if session.additionalTargetCount > 0 {
                        Text("+\(session.additionalTargetCount) more allowed targets")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }
            }

            LazyVGrid(
                columns: [
                    GridItem(.flexible(), alignment: .leading),
                    GridItem(.flexible(), alignment: .leading),
                ],
                alignment: .leading,
                spacing: 8
            ) {
                computerUseDetail("Frames", session.frameBudget)
                computerUseDetail("Actions", session.actionBudget)
                computerUseDetail(
                    "Idle deadline",
                    computerUseDeadlineLabel(session.idleDeadline)
                )
                computerUseDetail(
                    "Absolute deadline",
                    computerUseDeadlineLabel(session.absoluteDeadline)
                )
                computerUseDetail(
                    "Screen Recording",
                    session.screenRecordingPermission
                )
                computerUseDetail(
                    "Accessibility",
                    session.accessibilityPermission
                )
                computerUseDetail("Restart", session.restartStatus)
                computerUseDetail("Last action", session.lastAction)
                computerUseDetail("Last result", session.lastResult)
            }

            if viewModel.activeComputerUseControlStatus.isEmpty == false {
                Text(viewModel.activeComputerUseControlStatus)
                    .font(.caption)
                    .foregroundStyle(
                        viewModel.activeComputerUseControlIsWarning
                            ? MelixDesignTokens.StatusColor.warning
                            : Color.secondary
                    )
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(10)
        .background(
            computerUseStateColor(session.state).opacity(0.07),
            in: RoundedRectangle(cornerRadius: 9)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 9)
                .stroke(
                    computerUseStateColor(session.state).opacity(0.22),
                    lineWidth: 1
                )
        )
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Computer Use session")
        .accessibilityValue(session.state)
    }

    private func computerUseDetail(
        _ label: String,
        _ value: String
    ) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption)
                .lineLimit(2)
        }
        .accessibilityElement(children: .combine)
    }

    private var computerUseReceiptStatus: some View {
        VStack(alignment: .leading, spacing: 5) {
            Label("Computer Use receipt", systemImage: "doc.text.magnifyingglass")
                .font(.callout.weight(.semibold))
            Text(viewModel.activeComputerUseControlStatus)
                .font(.caption)
                .foregroundStyle(
                    viewModel.activeComputerUseControlIsWarning
                        ? MelixDesignTokens.StatusColor.warning
                        : Color.secondary
                )
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            Color.secondary.opacity(0.055),
            in: RoundedRectangle(cornerRadius: 9)
        )
        .accessibilityElement(children: .combine)
    }

    private func computerUseDeadlineLabel(_ date: Date?) -> String {
        date?.formatted(date: .abbreviated, time: .shortened) ?? "Unavailable"
    }

    private func computerUseStateColor(_ state: String) -> Color {
        switch state {
        case "Open":
            return MelixDesignTokens.accent
        case "Closed":
            return MelixDesignTokens.StatusColor.success
        default:
            return .secondary
        }
    }

    private func decide(
        _ choice: Melix_Controlplane_V1_AgentApprovalChoice
    ) {
        Task {
            await viewModel.decideAgentApproval(choice)
        }
    }

    private func stateColor(_ state: String) -> Color {
        switch state {
        case "waiting_for_approval":
            return MelixDesignTokens.StatusColor.warning
        case "failed":
            return MelixDesignTokens.StatusColor.error
        case "completed":
            return MelixDesignTokens.StatusColor.success
        default:
            return MelixDesignTokens.accent
        }
    }

    private func toolStateColor(_ state: String) -> Color {
        switch state {
        case "waiting_for_approval":
            return MelixDesignTokens.StatusColor.warning
        case "failed":
            return MelixDesignTokens.StatusColor.error
        case "completed":
            return MelixDesignTokens.StatusColor.success
        default:
            return .secondary
        }
    }

    private func isTerminalTool(
        _ tool: Melix_Controlplane_V1_AgentToolCallSnapshot
    ) -> Bool {
        ["completed", "failed", "cancelled"].contains(tool.state)
    }

    private func toolIssueColor(_ tone: DesktopAgentToolIssueTone) -> Color {
        switch tone {
        case .warning:
            return MelixDesignTokens.StatusColor.warning
        case .error:
            return MelixDesignTokens.StatusColor.error
        }
    }
}

struct DesktopAgentApprovalOutcomePresentation: Equatable {
    let title: String
    let errorCode: String
    let errorMessage: String
    let accessibilityValue: String
    let isWarning: Bool
}

func desktopAgentApprovalOutcomePresentation(
    _ receipt: Melix_Controlplane_V1_AgentApprovalDecisionReceipt
) -> DesktopAgentApprovalOutcomePresentation {
    let title: String
    let isWarning: Bool
    switch receipt.choice {
    case .agentApprovalAllowOnce:
        title = "Allowed This Call"
        isWarning = false
    case .agentApprovalAlwaysAllow:
        if receipt.policyPersistenceDisposition
            == .agentApprovalPolicyPersistenceApplied {
            title = "Allowed This Call · Always Allow Saved"
            isWarning = false
        } else if receipt.policyPersistenceDisposition
            == .agentApprovalPolicyPersistenceNotApplied {
            title = "Allowed This Call · Always Allow Not Saved"
            isWarning = true
        } else {
            title = "Allowed This Call · Always Allow Outcome Unknown"
            isWarning = true
        }
    case .agentApprovalDeny:
        title = "Approval Denied"
        isWarning = false
    case .unspecified, .UNRECOGNIZED:
        title = "Approval Outcome Unknown"
        isWarning = true
    }
    let errorCode = receipt.hasPolicyPersistenceError
        ? receipt.policyPersistenceError.code
        : ""
    let errorMessage: String
    if receipt.hasPolicyPersistenceError,
       !receipt.policyPersistenceError.message.isEmpty {
        errorMessage = receipt.policyPersistenceError.message
    } else if receipt.policyPersistenceDisposition
        == .agentApprovalPolicyPersistenceNotApplied {
        errorMessage = "The current call was approved, but the saved policy was not updated."
    } else {
        errorMessage = ""
    }
    return DesktopAgentApprovalOutcomePresentation(
        title: title,
        errorCode: errorCode,
        errorMessage: errorMessage,
        accessibilityValue: [title, errorCode, errorMessage]
            .filter { !$0.isEmpty }
            .joined(separator: ", "),
        isWarning: isWarning
    )
}

struct DesktopAgentCancellationOutcomePresentation: Equatable {
    let disposition: String
    let sideEffectState: String
    let detail: String
    let accessibilityValue: String
    let isWarning: Bool
}

func desktopAgentCancellationOutcomePresentation(
    _ receipt: Melix_Controlplane_V1_AgentRunCancellationReceipt
) -> DesktopAgentCancellationOutcomePresentation {
    let disposition = receipt.disposition.isEmpty
        ? "unknown"
        : receipt.disposition
    let sideEffectState: String
    switch receipt.sideEffectState {
    case .agentToolSideEffectNone:
        sideEffectState = "none"
    case .agentToolSideEffectCommitted:
        sideEffectState = "committed"
    case .agentToolSideEffectUnknown:
        sideEffectState = "unknown"
    case .unspecified:
        sideEffectState = receipt.sideEffectCommitted
            ? "committed (legacy receipt)"
            : "unknown (legacy receipt)"
    case .UNRECOGNIZED:
        sideEffectState = "unrecognized"
    }
    let confirmedBeforeSideEffect = disposition == "accepted"
        && receipt.sideEffectState == .agentToolSideEffectNone
    let sideEffectCommitted = sideEffectState.hasPrefix("committed")
    let detail: String
    switch disposition {
    case "accepted" where confirmedBeforeSideEffect:
        detail = "Stop accepted before any side effect was reported."
    case "accepted":
        detail = sideEffectCommitted
            ? "Stop was accepted, but a side effect committed before cancellation. Verify the target before continuing."
            : "Stop was accepted, but the side-effect state is unknown. Verify the target before continuing."
    case "already_terminal":
        if sideEffectState == "none" {
            detail = "The run was already terminal when Stop arrived; no side effect was reported. Verify the target before continuing."
        } else if sideEffectCommitted {
            detail = "The run was already terminal when Stop arrived, and a side effect had committed. Verify the target before continuing."
        } else {
            detail = "The run was already terminal when Stop arrived; the side-effect state is unknown. Verify the target before continuing."
        }
    case "not_found":
        if sideEffectState == "none" {
            detail = "No matching run was found; Stop was not confirmed, and no side effect was reported. Verify the target before continuing."
        } else if sideEffectCommitted {
            detail = "No matching run was found; Stop was not confirmed, and a side effect had committed. Verify the target before continuing."
        } else {
            detail = "No matching run was found; Stop was not confirmed, and the side-effect state is unknown. Verify the target before continuing."
        }
    case "too_late":
        detail = sideEffectCommitted
            ? "Stop arrived too late; a side effect had committed. Verify the target before continuing."
            : "Stop arrived too late; the side-effect state is unknown. Verify the target before continuing."
    default:
        detail = sideEffectCommitted
            ? "Stop outcome is unknown, and a side effect had committed. Verify the target before continuing."
            : "Stop outcome and side-effect state are unknown. Verify the target before continuing."
    }
    return DesktopAgentCancellationOutcomePresentation(
        disposition: disposition,
        sideEffectState: sideEffectState,
        detail: detail,
        accessibilityValue: "\(disposition), side effects \(sideEffectState), \(detail)",
        isWarning: !confirmedBeforeSideEffect
    )
}
