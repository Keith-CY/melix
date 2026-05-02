// Copyright © 2025 Apple Inc.

/// A mutex providing exclusive access with `async` blocks.
///
/// This is used as a building block for ``SerialAccessContainer``. Normal locks
/// do not work with `async` blocks and an `actor` does not guarantee exclusive access
/// for the duration of an `async` function.
private actor AsyncMutex {
    private var isLocked = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    private func lock() async {
        if !isLocked {
            isLocked = true
            return
        }

        await withCheckedContinuation { cont in
            waiters.append(cont)
        }
    }

    private func unlock() {
        if let next = waiters.first {
            waiters.removeFirst()
            next.resume()
        } else {
            isLocked = false
        }
    }

    func withLock<T>(_ body: () async throws -> sending T) async rethrows -> sending T {
        await lock()
        defer { unlock() }
        return try await body()
    }
}

/// Provide serial exclusive access to state `<T>` to async callers.
///
/// Unlike an `actor`, this guarantees exclusive access for the duration of the async
/// call. This is important for model containers that have to perform async work but
/// also need to prevent other callers from using any internal state concurrently.
final class SerialAccessContainer<T>: @unchecked Sendable {

    private var value: T
    private let lock = AsyncMutex()

    init(_ value: consuming T) {
        self.value = consume value
    }

    func read<R>(_ body: @Sendable (T) async throws -> sending R) async rethrows -> sending R {
        try await lock.withLock {
            try await body(value)
        }
    }

    func update<R>(_ body: @Sendable (inout T) async throws -> sending R) async rethrows
        -> sending R
    {
        try await lock.withLock {
            try await body(&value)
        }
    }
}

/// Internal box to wrap non-Sendable data transferred across task boundaries.
///
/// The wrapped value must be consumed exactly once.
final class SendableBox<T>: @unchecked Sendable {
    private var value: T?

    init(_ value: consuming T) {
        self.value = consume value
    }

    consuming func consume() -> T {
        guard let value else {
            fatalError("value already consumed")
        }
        self.value = nil
        return value
    }
}
