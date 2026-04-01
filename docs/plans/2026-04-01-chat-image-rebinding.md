# Chat And Image Rebinding

## Goal

Bind Chat to `Server Session` while keeping Image model and job oriented.

## Scope

- chat-session list and selection model
- `Chat Session -> Server Session` binding
- branch placement rules
- chat export behavior
- image-page preservation of model and job semantics

## Non-Goals

- rebinding Image to server sessions
- promoting `Branch` into the main left sidebar unit

## Chat Rules

- left sidebar unit is `Chat Session`
- every chat session binds to exactly one server session
- switching to another server requires a new or forked chat session
- `Branch` appears only in chat header or inspector
- `Export` is chat-session local
- if no running server session exists, Chat shows a blocking empty state routing to `Server`

## Image Rules

- left sidebar unit is `Image Job`
- center workspace owns the `Generate / Edit` switch, parameters, and results
- image execution continues to use image models and jobs
- image does not depend on server-session state

## Required Interfaces

- `DesktopChatSessionState`
- explicit `serverSessionID` on each chat session
- chat export metadata on the chat-session object
- image workspace mode selection that does not reference server-session state

## Files

- modify `apps/macos-menubar/Sources/AppMain/Chat/`
- modify `apps/macos-menubar/Sources/AppMain/Image/`
- modify `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- modify related tests under `apps/macos-menubar/Tests/MenuBarTests/`

## Performance Probes

- `menu.chat_submit_ms`
- `menu.chat_first_delta_ms`
- `desktop.image_action_latency_ms`
- image cancellation latency where applicable

## Verification

- `swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests`
- `swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests`

## Acceptance

- chat cannot send when no running server session exists
- creating a chat session binds the currently selected server session
- branch metadata remains secondary rather than becoming the primary navigation unit
- chat export stays local to the chat page
- image generation and edit flows continue to work through models and jobs
