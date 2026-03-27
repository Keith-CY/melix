import MelixTextWorkerCore

@main
struct BootstrapMain {
    static func main() async throws {
        let configuration = WorkerConfiguration.fromEnvironment()
        let bootstrap = try WorkerBootstrap.build(configuration: configuration)
        try await bootstrap.server.serve()
    }
}
