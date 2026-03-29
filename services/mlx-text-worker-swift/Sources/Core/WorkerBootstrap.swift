import GRPCCore
import GRPCNIOTransportHTTP2Posix
import Foundation

package struct WorkerBootstrap: Sendable {
    let configuration: WorkerConfiguration
    let services: WorkerServices
    package let server: GRPCServer<HTTP2ServerTransport.Posix>

    package static func build(
        configuration: WorkerConfiguration,
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) throws -> WorkerBootstrap {
        let bootstrapStartedAt = Date()
        let metrics = MetricsStore(exportPath: configuration.metricsExportPath)
        metrics.recordMilliseconds(
            "swift_text.spawn_to_bootstrap_ms",
            value: spawnToBootstrapMilliseconds(from: environment["MELIX_SWIFT_TEXT_WORKER_STARTUP_T0_NS"])
        )

        let registryStartedAt = Date()
        let registry = WorkerRuntimeRegistry(
            configuration: configuration,
            modelCatalog: WorkerModelCatalog(),
            runtime: makeTextRuntime(for: configuration),
            cacheStore: HotCacheStore(
                diskStore: DiskCacheStore(rootPath: configuration.cacheRootPath)
            )
        )
        metrics.recordMilliseconds("swift_text.registry_init_ms", value: elapsedMilliseconds(since: registryStartedAt))

        let servicesStartedAt = Date()
        let abortRegistry = AbortRegistry()
        let services = WorkerServices(
            configuration: configuration,
            registry: registry,
            abortRegistry: abortRegistry,
            metrics: metrics
        )
        metrics.recordMilliseconds("swift_text.services_init_ms", value: elapsedMilliseconds(since: servicesStartedAt))

        let serverStartedAt = Date()
        let transport = HTTP2ServerTransport.Posix(
            address: .unixDomainSocket(path: configuration.socketPath),
            transportSecurity: .plaintext
        )
        let server = GRPCServer(transport: transport, services: services.registrableServices)
        metrics.recordMilliseconds("swift_text.server_construct_ms", value: elapsedMilliseconds(since: serverStartedAt))
        metrics.recordMilliseconds("swift_text.bootstrap_ms", value: elapsedMilliseconds(since: bootstrapStartedAt))

        return WorkerBootstrap(
            configuration: configuration,
            services: services,
            server: server
        )
    }
}

private func elapsedMilliseconds(since startedAt: Date) -> Int {
    max(0, Int(Date().timeIntervalSince(startedAt) * 1_000.0))
}

private func spawnToBootstrapMilliseconds(from rawValue: String?) -> Int {
    guard
        let rawValue,
        let startedAtNanoseconds = UInt64(rawValue)
    else {
        return 0
    }

    let currentNanoseconds = DispatchTime.now().uptimeNanoseconds
    guard currentNanoseconds >= startedAtNanoseconds else {
        return 0
    }

    return Int((currentNanoseconds - startedAtNanoseconds) / 1_000_000)
}
