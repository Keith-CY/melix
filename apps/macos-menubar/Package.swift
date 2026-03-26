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
    targets: [
        .executableTarget(
            name: "AppMain",
            path: "Sources/AppMain"
        ),
        .testTarget(
            name: "MenuBarTests",
            dependencies: ["AppMain"],
            path: "Tests/MenuBarTests"
        ),
    ]
)
