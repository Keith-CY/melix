import Dispatch
import Foundation

func elapsedMilliseconds(since start: DispatchTime) -> Double {
    let end = DispatchTime.now()
    let nanos = end.uptimeNanoseconds - start.uptimeNanoseconds
    return Double(nanos) / 1_000_000
}

enum MelixCLIJSONMetricPatch {
    static let placeholderValue = 9.999999999999e99
    static let placeholderLiteral = "9.9999999999989997e+99"

    static func literal(for value: Double) -> String {
        let finiteValue = value.isFinite ? max(value, 0) : 0
        let boundedValue = min(finiteValue, placeholderValue)
        let literal = String(
            format: "%.16e",
            locale: Locale(identifier: "en_US_POSIX"),
            boundedValue
        )
        return literal
    }

    static func replacePlaceholder(in text: String, with value: Double) throws -> String {
        guard let range = text.range(of: placeholderLiteral) else {
            throw MelixCLIError.runtime("Failed to encode CLI metrics placeholder.")
        }
        var patched = text
        patched.replaceSubrange(range, with: literal(for: value))
        return patched
    }

    static func placeholderRange(in data: Data) throws -> Range<Data.Index> {
        let placeholderData = Data(placeholderLiteral.utf8)
        guard let range = data.range(of: placeholderData) else {
            throw MelixCLIError.runtime("Failed to locate pipeline metrics placeholder.")
        }
        return range
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
        var finalMetrics = metrics
        finalMetrics["melix.cli.json_encode_ms"] = MelixCLIJSONMetricPatch.placeholderValue
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
        var finalMetrics = metrics
        finalMetrics["melix.cli.json_encode_ms"] = MelixCLIJSONMetricPatch.placeholderValue
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
