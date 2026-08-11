import Testing

@testable import MelixControlPlaneCore

@Suite("Agent tool JSON Schema validator")
struct AgentToolJSONSchemaValidatorTests {
    @Test("supported MCP schema vocabulary validates representative values")
    func supportedVocabularyValidatesRepresentativeValues() throws {
        let validator = AgentToolJSONSchemaValidator()
        let passingCases: [(String, String)] = [
            (
                #"{"name":"Tokyo","count":4}"#,
                #"{"type":["object"],"properties":{"name":{"type":"string","minLength":2,"maxLength":8,"pattern":"^[A-Z]"},"count":{"type":"integer","minimum":2,"maximum":6,"exclusiveMinimum":1,"exclusiveMaximum":7,"multipleOf":2}},"required":["name","count"],"additionalProperties":false}"#
            ),
            (
                #"{"items":["prefix",2,4]}"#,
                #"{"type":"object","properties":{"items":{"type":"array","minItems":3,"maxItems":3,"uniqueItems":true,"prefixItems":[{"const":"prefix"}],"items":{"type":"integer"},"contains":{"type":"integer","multipleOf":2},"minContains":2,"maxContains":2}},"required":["items"]}"#
            ),
            (
                #"{"mode":"safe","value":"ok"}"#,
                #"{"type":"object","properties":{"mode":{"enum":["safe","fast"]},"value":{"allOf":[{"type":"string"},{"minLength":2}],"not":{"const":"blocked"}}},"if":{"properties":{"mode":{"const":"safe"}}},"then":{"properties":{"value":{"maxLength":2}}},"else":{"properties":{"value":{"minLength":3}}},"required":["mode","value"]}"#
            ),
            (
                #"{"primary":"ready","copy":"ready"}"#,
                ##"{"$defs":{"text":{"type":"string"}},"definitions":{"alias":{"$ref":"#/$defs/text"}},"type":"object","properties":{"primary":{"$ref":"#/$defs/text"},"copy":{"$ref":"#/definitions/alias"}},"required":["primary","copy"]}"##
            ),
            (
                #"{"value":4}"#,
                ##"{"allOf":[{"properties":{"value":{"type":"integer"}}}],"type":"object","properties":{"value":{"$ref":"#/allOf/0/properties/value"}},"required":["value"]}"##
            ),
            (
                #"{"x-id":"one","dependency":"yes"}"#,
                #"{"type":"object","minProperties":2,"maxProperties":2,"patternProperties":{"^x-":{"type":"string"}},"propertyNames":{"pattern":"^(x-id|dependency)$"},"dependentRequired":{"x-id":["dependency"]},"additionalProperties":{"type":"string"}}"#
            ),
            (
                #"{"choice":null}"#,
                #"{"type":"object","properties":{"choice":{"type":"string","nullable":true}},"required":["choice"]}"#
            ),
            (
                #"{"value":3}"#,
                #"{"type":"object","properties":{"value":{"anyOf":[{"type":"integer"},{"type":"string"}],"oneOf":[{"type":"integer"},{"type":"string"}]}},"required":["value"]}"#
            ),
        ]

        for (index, item) in passingCases.enumerated() {
            do {
                try validator.validateSchemaDefinition(item.1)
                try validator.validate(argumentsJSON: item.0, schemaJSON: item.1)
            } catch {
                Issue.record("Supported schema case \(index) failed: \(error)")
            }
        }

        try validator.validateSchemaDefinition(
            #"{"description":"escaped quote: \" and delimiters: } ]","type":"string"}"#
        )
    }

    @Test("malformed and unsupported schemas fail closed")
    func malformedAndUnsupportedSchemasFailClosed() throws {
        let invalidSchemas = [
            "not-json",
            "}",
            "[]",
            #"{"unknownAssertion":true}"#,
            #"{"type":7}"#,
            #"{"type":["string",7]}"#,
            #"{"type":[]}"#,
            #"{"type":["string","string"]}"#,
            #"{"type":"unsupported"}"#,
            #"{"nullable":"yes"}"#,
            #"{"enum":[]}"#,
            #"{"enum":"x"}"#,
            #"{"properties":[]}"#,
            #"{"patternProperties":{"[":{"type":"string"}}}"#,
            #"{"properties":{"value":7}}"#,
            #"{"additionalProperties":7}"#,
            #"{"prefixItems":{}}"#,
            #"{"prefixItems":[7]}"#,
            #"{"allOf":[]}"#,
            #"{"anyOf":{}}"#,
            #"{"$ref":"https://example.test/schema"}"#,
            ##"{"$ref":"#/$defs/missing"}"##,
            #"{"required":"value"}"#,
            #"{"required":["value","value"]}"#,
            #"{"dependentRequired":[]}"#,
            #"{"dependentRequired":{"value":"other"}}"#,
            #"{"minItems":-1}"#,
            #"{"maxLength":1.5}"#,
            #"{"minimum":"zero"}"#,
            #"{"multipleOf":0}"#,
            #"{"pattern":7}"#,
            #"{"pattern":"["}"#,
            #"{"uniqueItems":"yes"}"#,
            #"{"type":"string","type":"object"}"#,
            #"{"type":"string",}"#,
            #"{"type":"string" "nullable":true}"#,
            #"{"const":01}"#,
            #"{"const":true} trailing"#,
            #"{"const":"\uD800"}"#,
            #"{"type":"string""#,
            #"{{}}"#,
            #"[}"#,
            #"{]"#,
            #"[1,]"#,
            #"{:}"#,
            ",",
            #"{"x":1,,"y":2}"#,
            #"[,1]"#,
            #""root""#,
            "true false",
            #"[1 2]"#,
            "{\"const\":\"line\nbreak\"}",
            #"{"const":1e400}"#,
        ]
        let validator = AgentToolJSONSchemaValidator()

        for schema in invalidSchemas {
            expectValidationError(.invalidSchema) {
                try validator.validateSchemaDefinition(schema)
            }
        }

        var deeplyNested = #"{"type":"string"}"#
        for _ in 0..<66 {
            deeplyNested = #"{"allOf":[\#(deeplyNested)]}"#
        }
        expectValidationError(.invalidSchema) {
            try validator.validateSchemaDefinition(deeplyNested)
        }

        var maximumDepthProperties = #"{"type":"string"}"#
        for _ in 0..<64 {
            maximumDepthProperties = #"{"type":"object","properties":{"value":\#(maximumDepthProperties)}}"#
        }
        try validator.validateSchemaDefinition(maximumDepthProperties)
        var maximumDepthArguments = #""leaf""#
        for _ in 0..<64 {
            maximumDepthArguments = #"{"value":\#(maximumDepthArguments)}"#
        }
        try validator.validate(
            argumentsJSON: maximumDepthArguments,
            schemaJSON: maximumDepthProperties
        )

        try validator.validateSchemaDefinition(#"{"const":1e2}"#)

        var semanticallyDeep = #"{"type":"string"}"#
        for _ in 0..<66 {
            semanticallyDeep = #"{"additionalProperties":\#(semanticallyDeep)}"#
        }
        expectValidationError(.invalidSchema) {
            try validator.validateSchemaDefinition(semanticallyDeep)
        }

        expectValidationError(.invalidSchema) {
            try AgentToolJSONSchemaValidator(allowRegularExpressions: false)
                .validateSchemaDefinition(#"{"pattern":"x"}"#)
        }
    }

    @Test("argument assertions reject every supported constraint family")
    func argumentAssertionsRejectEveryConstraintFamily() throws {
        let validator = AgentToolJSONSchemaValidator()
        expectValidationError(.invalidArguments) {
            try validator.validate(argumentsJSON: "not-json", schemaJSON: #"{"type":"object"}"#)
        }
        expectValidationError(.invalidArguments) {
            try validator.validate(argumentsJSON: "[]", schemaJSON: #"{"type":"object"}"#)
        }
        expectValidationError(.invalidSchema) {
            try validator.validate(argumentsJSON: "{}", schemaJSON: "not-json")
        }
        expectValidationError(.invalidSchema) {
            try validator.validate(argumentsJSON: "{}", schemaJSON: "[]")
        }

        let violations: [(String, String)] = [
            ("{}", #"{"required":["value"]}"#),
            (#"{"value":1}"#, objectSchema(#"{"type":"string"}"#)),
            (#"{"value":"b"}"#, objectSchema(#"{"const":"a"}"#)),
            (#"{"value":"b"}"#, objectSchema(#"{"enum":["a"]}"#)),
            (#"{"value":1}"#, objectSchema(#"{"allOf":[{"minimum":0},{"maximum":0}]}"#)),
            (#"{"value":1}"#, objectSchema(#"{"anyOf":[{"type":"string"},{"type":"null"}]}"#)),
            (#"{"value":1}"#, objectSchema(#"{"oneOf":[{"minimum":0},{"maximum":2}]}"#)),
            (#"{"value":"blocked"}"#, objectSchema(#"{"not":{"const":"blocked"}}"#)),
            (#"{"value":"x"}"#, #"{"properties":{"value":{"type":"string"}},"if":{"properties":{"value":{"const":"x"}}},"then":{"properties":{"value":{"minLength":2}}}}"#),
            (#"{"value":"x"}"#, #"{"properties":{"value":{"type":"string"}},"if":{"properties":{"value":{"const":"y"}}},"else":{"properties":{"value":{"minLength":2}}}}"#),
            (#"{"value":"x"}"#, objectSchema(#"{"minLength":2}"#)),
            (#"{"value":"xxx"}"#, objectSchema(#"{"maxLength":2}"#)),
            (#"{"value":"lower"}"#, objectSchema(#"{"pattern":"^[A-Z]"}"#)),
            (#"{"value":1}"#, objectSchema(#"{"minimum":2}"#)),
            (#"{"value":3}"#, objectSchema(#"{"maximum":2}"#)),
            (#"{"value":2}"#, objectSchema(#"{"exclusiveMinimum":2}"#)),
            (#"{"value":2}"#, objectSchema(#"{"exclusiveMaximum":2}"#)),
            (#"{"value":3}"#, objectSchema(#"{"multipleOf":2}"#)),
            (#"{"value":[]}"#, objectSchema(#"{"minItems":1}"#)),
            (#"{"value":[1,2]}"#, objectSchema(#"{"maxItems":1}"#)),
            (#"{"value":[1,1]}"#, objectSchema(#"{"uniqueItems":true}"#)),
            (#"{"value":[1]}"#, objectSchema(#"{"prefixItems":[{"type":"string"}]}"#)),
            (#"{"value":["prefix",1]}"#, objectSchema(#"{"prefixItems":[true],"items":{"type":"string"}}"#)),
            (#"{"value":[1,2]}"#, objectSchema(#"{"contains":{"type":"string"}}"#)),
            (#"{"value":[1,2]}"#, objectSchema(#"{"contains":{"type":"integer"},"maxContains":1}"#)),
            (#"{"value":{}}"#, objectSchema(#"{"minProperties":1}"#)),
            (#"{"value":{"a":1,"b":2}}"#, objectSchema(#"{"maxProperties":1}"#)),
            (#"{"value":{"x-id":1}}"#, objectSchema(#"{"patternProperties":{"^x-":{"type":"string"}}}"#)),
            (#"{"value":{"extra":1}}"#, objectSchema(#"{"additionalProperties":false}"#)),
            (#"{"value":{"BAD":1}}"#, objectSchema(#"{"propertyNames":{"pattern":"^[a-z]+$"}}"#)),
            (#"{"value":{"a":1}}"#, objectSchema(#"{"dependentRequired":{"a":["b"]}}"#)),
            (#"{"value":"x"}"#, ##"{"$defs":{"number":{"type":"number"}},"properties":{"value":{"$ref":"#/$defs/number"}}}"##),
            (#"{"value":1.5}"#, objectSchema(#"{"type":"integer"}"#)),
            (#"{"value":1}"#, objectSchema("false")),
        ]

        for (arguments, schema) in violations {
            expectValidationError(.schemaViolation) {
                try validator.validate(argumentsJSON: arguments, schemaJSON: schema)
            }
        }
    }
}

private func objectSchema(_ propertySchema: String) -> String {
    #"{"type":"object","properties":{"value":\#(propertySchema)},"required":["value"]}"#
}

private func expectValidationError(
    _ expected: AgentToolJSONSchemaValidationError,
    operation: () throws -> Void
) {
    do {
        try operation()
        Issue.record("Expected JSON Schema validation to fail with \(expected)")
    } catch let error as AgentToolJSONSchemaValidationError {
        #expect(error == expected)
    } catch {
        Issue.record("Unexpected JSON Schema validation error: \(error)")
    }
}
