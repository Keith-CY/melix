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
}
