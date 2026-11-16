// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "GoddardApp",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "GoddardApp",
            path: "Sources/GoddardApp",
            resources: [.copy("Resources")]
        )
    ]
)
