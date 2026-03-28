import GRPCCore
import GRPCNIOTransportHTTP2Posix

package struct WorkerBootstrap: Sendable {
    let configuration: WorkerConfiguration
    let services: WorkerServices
    package let server: GRPCServer<HTTP2ServerTransport.Posix>

    package static func build(configuration: WorkerConfiguration) throws -> WorkerBootstrap {
        let metrics = MetricsStore(exportPath: configuration.metricsExportPath)
        metrics.recordMilliseconds("swift_text.bootstrap_ms", value: 0)

        let registry = WorkerRuntimeRegistry(
            configuration: configuration,
            modelCatalog: WorkerModelCatalog(),
            runtime: makeTextRuntime(for: configuration),
            cacheStore: HotCacheStore(
                diskStore: DiskCacheStore(rootPath: configuration.cacheRootPath)
            )
        )
        let abortRegistry = AbortRegistry()
        let services = WorkerServices(
            configuration: configuration,
            registry: registry,
            abortRegistry: abortRegistry,
            metrics: metrics
        )

        let transport = HTTP2ServerTransport.Posix(
            address: .unixDomainSocket(path: configuration.socketPath),
            transportSecurity: .plaintext
        )
        let server = GRPCServer(transport: transport, services: services.registrableServices)

        return WorkerBootstrap(
            configuration: configuration,
            services: services,
            server: server
        )
    }
}
