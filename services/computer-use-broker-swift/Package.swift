// swift-tools-version: 6.1

import PackageDescription

let package = Package(
    name: "MelixComputerUseBroker",
    platforms: [
        .macOS(.v15),
    ],
    products: [
        .library(name: "ComputerUseBrokerCore", targets: ["ComputerUseBrokerCore"]),
        .library(name: "ComputerUseBrokerMacOS", targets: ["ComputerUseBrokerMacOS"]),
        .library(name: "ComputerUseBrokerTransport", targets: ["ComputerUseBrokerTransport"]),
        .executable(name: "melix-computer-broker", targets: ["ComputerUseBrokerCLI"]),
    ],
    dependencies: [
        .package(path: "../../packages/protocol/swift"),
        .package(url: "https://github.com/grpc/grpc-swift-2.git", from: "2.4.1"),
        .package(url: "https://github.com/grpc/grpc-swift-nio-transport.git", from: "2.7.0"),
    ],
    targets: [
        .target(
            name: "ComputerUseBrokerCore"
        ),
        .target(
            name: "ComputerUseBrokerMacOS",
            dependencies: ["ComputerUseBrokerCore"],
            linkerSettings: [
                .linkedFramework("ApplicationServices"),
                .linkedFramework("CoreGraphics"),
                .linkedFramework("ScreenCaptureKit"),
            ]
        ),
        .target(
            name: "ComputerUseBrokerTransport",
            dependencies: [
                "ComputerUseBrokerCore",
                .product(name: "MelixComputerProtocol", package: "swift"),
                .product(name: "GRPCCore", package: "grpc-swift-2"),
                .product(name: "GRPCNIOTransportHTTP2Posix", package: "grpc-swift-nio-transport"),
            ]
        ),
        .executableTarget(
            name: "ComputerUseBrokerCLI",
            dependencies: [
                "ComputerUseBrokerCore",
                "ComputerUseBrokerMacOS",
                "ComputerUseBrokerTransport",
            ]
        ),
        .testTarget(
            name: "ComputerUseBrokerCoreTests",
            dependencies: [
                "ComputerUseBrokerCore",
                "ComputerUseBrokerTransport",
                .product(name: "MelixComputerProtocol", package: "swift"),
                .product(name: "GRPCCore", package: "grpc-swift-2"),
                .product(name: "GRPCNIOTransportHTTP2Posix", package: "grpc-swift-nio-transport"),
            ]
        ),
        .testTarget(
            name: "ComputerUseBrokerMacOSTests",
            dependencies: [
                "ComputerUseBrokerCore",
                "ComputerUseBrokerMacOS",
            ]
        ),
    ]
)
