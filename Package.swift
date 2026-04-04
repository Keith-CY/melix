// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "melix",
    platforms: [
        .macOS(.v15),
    ],
    products: [
        .library(name: "MelixWorkspace", targets: ["MelixWorkspace"]),
        .executable(name: "melix", targets: ["MelixCLI"]),
        .executable(name: "melix-session-lifecycle-smoke", targets: ["MelixSessionLifecycleSmoke"]),
    ],
    dependencies: [
        .package(path: "services/control-plane-swift"),
        .package(path: "packages/protocol/swift"),
    ],
    targets: [
        .target(
            name: "MelixWorkspace",
            path: "Sources/MelixWorkspace"
        ),
        .target(
            name: "MelixCLICore",
            dependencies: [
                .product(name: "MelixControlPlaneCore", package: "control-plane-swift"),
                .product(name: "MelixControlPlaneProtocol", package: "swift"),
            ],
            path: "Sources/MelixCLICore"
        ),
        .executableTarget(
            name: "MelixCLI",
            dependencies: ["MelixCLICore"],
            path: "Sources/MelixCLI"
        ),
        .executableTarget(
            name: "MelixSessionLifecycleSmoke",
            dependencies: ["MelixCLICore"],
            path: "Sources/MelixSessionLifecycleSmoke"
        ),
        .testTarget(
            name: "MelixCLITests",
            dependencies: ["MelixCLICore"],
            path: "tests/MelixCLITests"
        ),
    ]
)
