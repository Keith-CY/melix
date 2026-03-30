import MelixControlPlaneProtocol
import MelixWorkerProtocol

func makeControlPlaneCacheMode(
    from workerMode: Melix_Worker_V1_CacheMode
) -> Melix_Controlplane_V1_CacheMode {
    switch workerMode {
    case .tiered:
        return .tiered
    case .rotating:
        return .rotating
    case .hybrid:
        return .hybrid
    case .unspecified:
        fallthrough
    case .UNRECOGNIZED:
        fallthrough
    @unknown default:
        return .unspecified
    }
}

func cacheModeLabel(
    _ mode: Melix_Controlplane_V1_CacheMode
) -> String {
    switch mode {
    case .tiered:
        return "tiered"
    case .rotating:
        return "rotating"
    case .hybrid:
        return "hybrid"
    case .unspecified:
        fallthrough
    case .UNRECOGNIZED:
        fallthrough
    @unknown default:
        return "unspecified"
    }
}

func cacheModeMetricValue(
    _ mode: Melix_Controlplane_V1_CacheMode
) -> Double {
    switch mode {
    case .tiered:
        return 1
    case .rotating:
        return 2
    case .hybrid:
        return 3
    case .unspecified:
        fallthrough
    case .UNRECOGNIZED:
        fallthrough
    @unknown default:
        return 0
    }
}
