// Copyright © 2026 Apple Inc.

import Foundation
import MLX
import MLXNN

public typealias RoPELayer = OffsetLayer & ArrayOffsetLayer

public protocol BatchPositionedKVCache: KVCache {
    var batchOffset: MLXArray { get }
}
