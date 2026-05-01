import Dispatch
import Foundation

func elapsedMilliseconds(since start: DispatchTime) -> Double {
    let end = DispatchTime.now()
    let nanos = end.uptimeNanoseconds - start.uptimeNanoseconds
    return Double(nanos) / 1_000_000
}

enum MelixCLIJSONMetricPatch {
    private static let metricLiteralLocale = Locale(identifier: "en_US_POSIX")

    struct Placeholder {
        let token: String

        var jsonLiteral: String {
            "\"\(token)\""
        }
    }

    static func makePlaceholder(metricName: String) -> Placeholder {
        let safeMetricName = metricName
            .map { character in
                character.isLetter || character.isNumber ? character : "_"
            }
        return Placeholder(token: "__MELIX_METRIC_\(String(safeMetricName))_\(UUID().uuidString)__")
    }

    static func literal(for value: Double) -> String {
        let finiteValue = value.isFinite ? max(value, 0) : 0
        return String(
            format: "%.16e",
            locale: metricLiteralLocale,
            finiteValue
        )
    }

    static func replacePlaceholder(in text: String, with value: Double) throws -> String {
        try replacePlaceholder(
            in: text,
            placeholder: Placeholder(token: "__MELIX_METRIC_PLACEHOLDER__"),
            with: value
        )
    }

    static func replacePlaceholder(
        in text: String,
        placeholder: Placeholder,
        with value: Double
    ) throws -> String {
        let markerLiteral = placeholder.jsonLiteral
        guard let range = text.range(of: markerLiteral) else {
            throw MelixCLIError.runtime("Failed to encode CLI metrics placeholder.")
        }
        guard text.range(of: markerLiteral, range: range.upperBound..<text.endIndex) == nil else {
            throw MelixCLIError.runtime("Found duplicate CLI metrics placeholders.")
        }
        var patched = text
        patched.replaceSubrange(range, with: literal(for: value))
        return patched
    }

    static func placeholderRange(in data: Data) throws -> Range<Data.Index> {
        try placeholderRange(
            in: data,
            placeholder: Placeholder(token: "__MELIX_METRIC_PLACEHOLDER__")
        )
    }

    static func placeholderRange(
        in data: Data,
        placeholder: Placeholder
    ) throws -> Range<Data.Index> {
        let placeholderData = Data(placeholder.jsonLiteral.utf8)
        guard let range = data.range(of: placeholderData) else {
            throw MelixCLIError.runtime("Failed to locate pipeline metrics placeholder.")
        }
        if data.range(of: placeholderData, options: [], in: range.upperBound..<data.endIndex) != nil {
            throw MelixCLIError.runtime("Found duplicate pipeline metrics placeholders.")
        }
        return range
    }

    static func paddedLiteralData(for value: Double, byteCount: Int) throws -> Data {
        let literalData = Data(literal(for: value).utf8)
        guard literalData.count <= byteCount else {
            throw MelixCLIError.runtime("Pipeline metrics placeholder is too short for the encoded metric.")
        }
        var data = literalData
        data.append(contentsOf: repeatElement(UInt8(ascii: " "), count: byteCount - literalData.count))
        return data
    }
}

enum MelixCLIJSON {
    static func prettyString(_ payload: Any) throws -> String {
        let data = try JSONSerialization.data(
            withJSONObject: payload,
            options: [.prettyPrinted, .sortedKeys]
        )
        return String(decoding: data, as: UTF8.self) + "\n"
    }

    static func jsonValue(from text: String) -> Any {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let data = trimmed.data(using: .utf8),
              let value = try? JSONSerialization.jsonObject(with: data)
        else {
            return ["text": trimmed]
        }
        return value
    }

    static func metricsObject(
        from metrics: [String: Double],
        adding metricName: String,
        placeholder: MelixCLIJSONMetricPatch.Placeholder
    ) -> [String: Any] {
        var finalMetrics = [String: Any](minimumCapacity: metrics.count + 1)
        for (key, value) in metrics {
            finalMetrics[key] = value
        }
        finalMetrics[metricName] = placeholder.token
        return finalMetrics
    }
}

public enum MelixCLIJSONEnvelope {
    public static func outputEnvelopeString(
        commandID: String,
        traceID: String,
        result: Any,
        warnings: [String] = [],
        artifacts: [[String: Any]] = [],
        metrics: [String: Double] = [:],
        status: String = "succeeded"
    ) throws -> String {
        let placeholder = MelixCLIJSONMetricPatch.makePlaceholder(metricName: "melix.cli.json_encode_ms")
        let finalMetrics = MelixCLIJSON.metricsObject(
            from: metrics,
            adding: "melix.cli.json_encode_ms",
            placeholder: placeholder
        )
        let payload: [String: Any] = [
            "schema_version": "melix.cli.output.v1",
            "command_id": commandID,
            "status": status,
            "trace_id": traceID,
            "result": result,
            "warnings": warnings,
            "artifacts": artifacts,
            "metrics": finalMetrics,
        ]
        let encodeStart = DispatchTime.now()
        let text = try MelixCLIJSON.prettyString(payload)
        return try MelixCLIJSONMetricPatch.replacePlaceholder(
            in: text,
            placeholder: placeholder,
            with: elapsedMilliseconds(since: encodeStart)
        )
    }

    public static func errorEnvelopeString(
        commandID: String,
        traceID: String,
        error: MelixCLIError,
        metrics: [String: Double] = [:]
    ) throws -> String {
        try errorEnvelopeString(
            commandID: commandID,
            traceID: traceID,
            code: code(for: error),
            message: error.errorDescription ?? "\(error)",
            metrics: metrics
        )
    }

    public static func errorEnvelopeString(
        commandID: String,
        traceID: String,
        code: String,
        message: String,
        metrics: [String: Double] = [:]
    ) throws -> String {
        let placeholder = MelixCLIJSONMetricPatch.makePlaceholder(metricName: "melix.cli.json_encode_ms")
        let finalMetrics = MelixCLIJSON.metricsObject(
            from: metrics,
            adding: "melix.cli.json_encode_ms",
            placeholder: placeholder
        )
        let payload: [String: Any] = [
            "schema_version": "melix.cli.error.v1",
            "command_id": commandID,
            "status": "failed",
            "trace_id": traceID,
            "error": [
                "code": code,
                "message": message,
            ],
            "warnings": [],
            "artifacts": [],
            "metrics": finalMetrics,
        ]
        let encodeStart = DispatchTime.now()
        let text = try MelixCLIJSON.prettyString(payload)
        return try MelixCLIJSONMetricPatch.replacePlaceholder(
            in: text,
            placeholder: placeholder,
            with: elapsedMilliseconds(since: encodeStart)
        )
    }

    public static func code(for error: MelixCLIError) -> String {
        switch error {
        case .usage:
            return "usage"
        case .missingValue:
            return "missing_value"
        case .missingRequired:
            return "missing_required"
        case .runtime:
            return "runtime"
        case .requestFailed(let code, _):
            return code.isEmpty ? "runtime" : code
        }
    }
}

extension MelixCLIRunner {
    public func run(_ invocation: MelixCLIInvocation) async throws -> String {
        guard invocation.outputFormat == .jsonV1 else {
            return try await run(invocation.command)
        }

        let traceID = invocation.traceID.isEmpty ? UUID().uuidString : invocation.traceID
        let command = try MelixCLICommandCodec.jsonEnabledCommand(for: invocation.command)
        let commandStart = DispatchTime.now()
        let rawOutput = try await run(command)
        let commandDurationMS = elapsedMilliseconds(since: commandStart)
        let result = MelixCLIJSON.jsonValue(from: rawOutput)
        return try MelixCLIJSONEnvelope.outputEnvelopeString(
            commandID: MelixCLICommandCodec.commandID(for: invocation.command),
            traceID: traceID,
            result: result,
            metrics: [
                "melix.cli.parse_ms": invocation.parseDurationMS,
                "melix.cli.command_ms": commandDurationMS,
            ]
        )
    }
}
