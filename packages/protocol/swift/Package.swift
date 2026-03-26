// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "MelixProtocolSwift",
    platforms: [
        .macOS(.v14),
    ],
    products: [
        .library(name: "MelixControlPlaneProtocol", targets: ["MelixControlPlaneProtocol"]),
        .library(name: "MelixWorkerProtocol", targets: ["MelixWorkerProtocol"]),
    ],
    dependencies: [
        .package(url: "https://github.com/apple/swift-protobuf.git", from: "1.36.0"),
    ],
    targets: [
        .target(
            name: "MelixControlPlaneProtocol",
            dependencies: [
                .product(name: "SwiftProtobuf", package: "swift-protobuf"),
            ],
            path: "controlplane/v1",
            sources: ["control_plane.pb.swift"]
        ),
        .target(
            name: "MelixWorkerProtocol",
            dependencies: [
                .product(name: "SwiftProtobuf", package: "swift-protobuf"),
            ],
            path: "worker/v1",
            sources: [
                "common.pb.swift",
                "runtime.pb.swift",
                "inference.pb.swift",
                "cache.pb.swift",
                "maintenance.pb.swift",
            ]
        ),
    ]
)
