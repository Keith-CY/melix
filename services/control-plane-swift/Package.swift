// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "MelixControlPlane",
    platforms: [
        .macOS(.v15),
    ],
    products: [
        .library(name: "MelixControlPlaneCore", targets: ["MelixControlPlaneCore"]),
        .executable(name: "melix-control-plane", targets: ["Bootstrap"]),
    ],
    dependencies: [
        .package(path: "../../packages/protocol/swift"),
        .package(url: "https://github.com/grpc/grpc-swift-2.git", from: "2.0.0"),
        .package(url: "https://github.com/grpc/grpc-swift-nio-transport.git", from: "2.6.1"),
    ],
    targets: [
        .target(
            name: "MelixControlPlaneCore",
            dependencies: [
                .product(name: "MelixControlPlaneProtocol", package: "swift"),
                .product(name: "MelixWorkerProtocol", package: "swift"),
                .product(name: "GRPCCore", package: "grpc-swift-2"),
                .product(name: "GRPCNIOTransportHTTP2Posix", package: "grpc-swift-nio-transport"),
            ],
            path: "Sources",
            exclude: ["Bootstrap"],
            sources: [
                "EnginePool",
                "HTTPGateway",
                "Metrics",
                "ModelCatalog",
                "Requests",
                "Snapshots",
                "WorkerClient",
                "XPCService",
            ]
        ),
        .executableTarget(
            name: "Bootstrap",
            dependencies: ["MelixControlPlaneCore"],
            path: "Sources/Bootstrap"
        ),
        .testTarget(
            name: "ControlPlaneTests",
            dependencies: ["MelixControlPlaneCore"],
            path: "Tests/ControlPlaneTests"
        ),
        .testTarget(
            name: "HTTPGatewayTests",
            dependencies: ["MelixControlPlaneCore"],
            path: "Tests/HTTPGatewayTests"
        ),
        .testTarget(
            name: "WorkerClientTests",
            dependencies: ["MelixControlPlaneCore"],
            path: "Tests/WorkerClientTests"
        ),
    ]
)
