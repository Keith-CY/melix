import Foundation
import Testing

@testable import MelixControlPlaneCore

@Suite("Rich Output Sanitizer")
struct RichOutputSanitizerTests {
    @Test("sanitizer strips html fragments and unsafe uris outside fenced code blocks")
    func stripsHTMLFragmentsAndUnsafeURIsOutsideCodeFences() {
        let input = """
        <b>Hello</b> [click](javascript:alert(1)) file:///tmp/melix

        ```html
        <script>alert(1)</script>
        [keep](javascript:alert(1))
        ```
        """

        let result = RichOutputSanitizer.sanitize(input)

        #expect(result.text == """
        Hello click [unsafe link removed]

        ```html
        <script>alert(1)</script>
        [keep](javascript:alert(1))
        ```
        """)
        #expect(result.didSanitize == true)
        #expect(result.blockedHTMLFragmentCount == 2)
        #expect(result.unsafeURIRejectionCount == 2)
    }

    @Test("sanitizer removes active html fragments while preserving readable text")
    func removesActiveHTMLFragmentsWhilePreservingReadableText() {
        let result = RichOutputSanitizer.sanitize(
            "<script>alert(1)</script><div>safe</div><!-- comment --> plain"
        )

        #expect(result.text == "safe plain")
        #expect(result.didSanitize == true)
        #expect(result.blockedHTMLFragmentCount == 4)
        #expect(result.unsafeURIRejectionCount == 0)
    }

    @Test("sanitizer preserves plain comparison operators")
    func preservesPlainComparisonOperators() {
        let result = RichOutputSanitizer.sanitize("alpha < beta && gamma > delta")

        #expect(result.text == "alpha < beta && gamma > delta")
        #expect(result.didSanitize == false)
        #expect(result.blockedHTMLFragmentCount == 0)
        #expect(result.unsafeURIRejectionCount == 0)
    }

    @Test("sanitizer is idempotent")
    func isIdempotent() {
        let once = RichOutputSanitizer.sanitize("<i>Hi</i> [x](file:///tmp/x)")
        let twice = RichOutputSanitizer.sanitize(once.text)

        #expect(once.text == "Hi x")
        #expect(twice == RichOutputSanitizationResult(
            text: "Hi x",
            didSanitize: false,
            blockedHTMLFragmentCount: 0,
            unsafeURIRejectionCount: 0
        ))
    }

    @Test("sanitizer removes complete and orphan tool-call markup outside code fences")
    func removesCompleteAndOrphanToolCallMarkupOutsideCodeFences() {
        let input = """
        before <tool_call>{"name":"search","arguments":{"q":"melix"}}</tool_call> middle <|tool_call>call:terminal.execute{"command":"pwd"} after

        ```text
        <tool_call>{"name":"keep"}</tool_call>
        ```
        """

        let result = RichOutputSanitizer.sanitize(input)

        #expect(result.text == """
        before  middle ```text
        <tool_call>{"name":"keep"}</tool_call>
        ```
        """)
        #expect(result.didSanitize)
        #expect(result.blockedHTMLFragmentCount == 1)
        #expect(result.unsafeURIRejectionCount == 0)
    }

    @Test("streaming tool-call markup sanitizer suppresses split orphan markers")
    func streamingToolCallMarkupSanitizerSuppressesSplitOrphanMarkers() {
        var sanitizer = ToolCallMarkupSanitizer.StreamingState()

        #expect(sanitizer.accept("visible <|tool_") == "visible ")
        #expect(sanitizer.accept(#"call>call:terminal.execute{"command":"pwd"}"#) == "")
        #expect(sanitizer.finish() == "")
    }

    @Test("streaming tool-call markup sanitizer accepts empty deltas")
    func streamingToolCallMarkupSanitizerAcceptsEmptyDeltas() {
        var sanitizer = ToolCallMarkupSanitizer.StreamingState()

        #expect(sanitizer.accept("") == "")
    }

    @Test("streaming tool-call markup sanitizer removes complete single-delta markup")
    func streamingToolCallMarkupSanitizerRemovesCompleteSingleDeltaMarkup() {
        var sanitizer = ToolCallMarkupSanitizer.StreamingState()

        #expect(sanitizer.accept(#"a <tool_call>{"name":"search"}</tool_call> b"#) == "a  b")
        #expect(sanitizer.finish() == "")
    }

    @Test("streaming tool-call markup sanitizer drops partial markers at finish")
    func streamingToolCallMarkupSanitizerDropsPartialMarkersAtFinish() {
        var sanitizer = ToolCallMarkupSanitizer.StreamingState()

        #expect(sanitizer.accept("visible <|tool_") == "visible ")
        #expect(sanitizer.finish() == "")
    }

    @Test("streaming tool-call markup sanitizer resumes after a closed marker")
    func streamingToolCallMarkupSanitizerResumesAfterClosedMarker() {
        var sanitizer = ToolCallMarkupSanitizer.StreamingState()

        #expect(sanitizer.accept(#"a <tool_call>{"name":"search"}"#) == "a ")
        #expect(sanitizer.accept("</tool_call> b") == " b")
        #expect(sanitizer.finish() == "")
    }

    @Test("final text tool-call sanitizer drops partial trailing markers")
    func finalTextToolCallSanitizerDropsPartialTrailingMarkers() {
        #expect(ToolCallMarkupSanitizer.sanitizeFinalText("visible <tool_") == "visible ")
    }

    @Test("final text tool-call sanitizer preserves empty text")
    func finalTextToolCallSanitizerPreservesEmptyText() {
        #expect(ToolCallMarkupSanitizer.sanitizeFinalText("") == "")
    }
}
