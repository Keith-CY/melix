// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "MelixMacOSMenubar",
    platforms: [
        .macOS(.v14),
    ],
    products: [
        .executable(name: "melix-menubar", targets: ["AppMain"]),
    ],
    dependencies: [
        .package(path: "../../services/control-plane-swift"),
        .package(path: "../../packages/protocol/swift"),
    ],
    targets: [
        .executableTarget(
            name: "AppMain",
            dependencies: [
                .product(name: "MelixControlPlaneCore", package: "control-plane-swift"),
                .product(name: "MelixControlPlaneProtocol", package: "swift"),
            ],
            path: "Sources/AppMain"
        ),
        .testTarget(
            name: "MenuBarTests",
            dependencies: [
                "AppMain",
                .product(name: "MelixControlPlaneCore", package: "control-plane-swift"),
                .product(name: "MelixControlPlaneProtocol", package: "swift"),
            ],
            path: "Tests/MenuBarTests"
        ),
    ]
)
