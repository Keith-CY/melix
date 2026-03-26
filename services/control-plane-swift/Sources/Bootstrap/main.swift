import Foundation
import MelixControlPlaneCore

@main
enum MelixControlPlaneBootstrap {
    static func main() {
        _ = ControlPlaneService()
        print("Melix control plane ready")
    }
}
