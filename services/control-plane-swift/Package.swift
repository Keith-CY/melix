// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "MelixControlPlane",
    platforms: [
        .macOS(.v14),
    ],
    products: [
        .library(name: "MelixControlPlaneCore", targets: ["MelixControlPlaneCore"]),
        .executable(name: "melix-control-plane", targets: ["Bootstrap"]),
    ],
    dependencies: [
        .package(path: "../../packages/protocol/swift"),
    ],
    targets: [
        .target(
            name: "MelixControlPlaneCore",
            dependencies: [
                .product(name: "MelixControlPlaneProtocol", package: "swift"),
                .product(name: "MelixWorkerProtocol", package: "swift"),
            ],
            path: "Sources",
            exclude: ["Bootstrap"]
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
