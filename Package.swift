// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "melix",
    platforms: [
        .macOS(.v14),
    ],
    products: [
        .library(name: "MelixWorkspace", targets: ["MelixWorkspace"]),
    ],
    targets: [
        .target(
            name: "MelixWorkspace",
            path: "Sources/MelixWorkspace"
        ),
    ]
)
