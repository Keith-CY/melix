// swift-tools-version: 6.1

import PackageDescription

let package = Package(
    name: "MelixProtocolSwift",
    platforms: [
        .macOS(.v15),
    ],
    products: [
        .library(name: "MelixControlPlaneProtocol", targets: ["MelixControlPlaneProtocol"]),
        .library(name: "MelixWorkspaceProtocol", targets: ["MelixWorkspaceProtocol"]),
        .library(name: "MelixWorkerProtocol", targets: ["MelixWorkerProtocol"]),
    ],
    dependencies: [
        .package(url: "https://github.com/apple/swift-protobuf.git", from: "1.37.0"),
        .package(url: "https://github.com/grpc/grpc-swift-2.git", from: "2.4.1"),
        .package(url: "https://github.com/grpc/grpc-swift-protobuf.git", from: "2.3.0"),
    ],
    targets: [
        .target(
            name: "MelixControlPlaneProtocol",
            dependencies: [
                .product(name: "SwiftProtobuf", package: "swift-protobuf"),
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
