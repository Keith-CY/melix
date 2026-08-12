// swift-tools-version: 6.1

import PackageDescription

let package = Package(
    name: "MelixProtocolSwift",
    platforms: [
        .macOS(.v15),
    ],
    products: [
        .library(name: "MelixComputerProtocol", targets: ["MelixComputerProtocol"]),
        .library(name: "MelixControlPlaneProtocol", targets: ["MelixControlPlaneProtocol"]),
        .library(name: "MelixWorkspaceProtocol", targets: ["MelixWorkspaceProtocol"]),
        .library(name: "MelixWorkerProtocol", targets: ["MelixWorkerProtocol"]),
    ],
    dependencies: [
        // Swift Collections 1.5.0 fails to compile its ContainersPreview target
        // with Xcode 26.6 / Swift 6.3.3. This shared package participates in all
        // five committed SwiftPM graphs, so keep every workspace on the tested
        // 1.6.0 release with one exact constraint.
        .package(url: "https://github.com/apple/swift-collections.git", exact: "1.6.0"),
        .package(url: "https://github.com/apple/swift-protobuf.git", from: "1.37.0"),
        .package(url: "https://github.com/grpc/grpc-swift-2.git", from: "2.4.1"),
        .package(url: "https://github.com/grpc/grpc-swift-protobuf.git", from: "2.3.0"),
    ],
    targets: [
        .target(
            name: "MelixComputerProtocol",
            dependencies: [
                .product(name: "SwiftProtobuf", package: "swift-protobuf"),
                .product(name: "GRPCCore", package: "grpc-swift-2"),
                .product(name: "GRPCProtobuf", package: "grpc-swift-protobuf"),
            ],
            path: "computer/v1"
        ),
        .target(
            name: "MelixControlPlaneProtocol",
            dependencies: [
                .product(name: "SwiftProtobuf", package: "swift-protobuf"),
                .product(name: "GRPCCore", package: "grpc-swift-2"),
                .product(name: "GRPCProtobuf", package: "grpc-swift-protobuf"),
            ],
            path: "controlplane/v1"
        ),
        .target(
            name: "MelixWorkspaceProtocol",
            dependencies: [
                .product(name: "SwiftProtobuf", package: "swift-protobuf"),
            ],
            path: "workspace/v1"
        ),
        .target(
            name: "MelixWorkerProtocol",
            dependencies: [
                .product(name: "SwiftProtobuf", package: "swift-protobuf"),
                .product(name: "GRPCCore", package: "grpc-swift-2"),
                .product(name: "GRPCProtobuf", package: "grpc-swift-protobuf"),
            ],
            path: "worker/v1"
        ),
        .testTarget(
            name: "MelixProtocolSwiftTests",
            path: "Tests"
        ),
    ]
)
