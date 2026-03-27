// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "MelixTextWorkerSwift",
    platforms: [
        .macOS(.v15),
    ],
    products: [
        .library(name: "MelixTextWorkerCore", targets: ["MelixTextWorkerCore"]),
        .executable(name: "melix-text-worker-swift", targets: ["Bootstrap"]),
    ],
    dependencies: [
        .package(path: "../../packages/protocol/swift"),
        .package(url: "https://github.com/grpc/grpc-swift-2.git", from: "2.0.0"),
        .package(url: "https://github.com/grpc/grpc-swift-nio-transport.git", from: "2.6.1"),
        .package(url: "https://github.com/ml-explore/mlx-swift-lm/", .upToNextMinor(from: "2.29.1")),
    ],
    targets: [
        .target(
            name: "MelixTextWorkerCore",
            dependencies: [
                .product(name: "MelixWorkerProtocol", package: "swift"),
                .product(name: "GRPCCore", package: "grpc-swift-2"),
                .product(name: "GRPCNIOTransportHTTP2Posix", package: "grpc-swift-nio-transport"),
                .product(name: "MLXLMCommon", package: "mlx-swift-lm"),
            ],
            path: "Sources/Core"
        ),
        .executableTarget(
            name: "Bootstrap",
            dependencies: ["MelixTextWorkerCore"],
            path: "Sources/Bootstrap"
        ),
        .testTarget(
            name: "MelixTextWorkerCoreTests",
            dependencies: ["MelixTextWorkerCore"],
            path: "Tests/CoreTests"
        ),
    ]
)
