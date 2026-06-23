import Testing

@testable import MelixControlPlaneCore

@Suite("UI Sink Escaper")
struct UISinkEscaperTests {
    @Test("html text and attributes escape markup quotes and controls")
    func htmlTextAndAttributesEscapeMarkupQuotesAndControls() {
        let raw = #"""
        <script>alert("x")</script> & 'owner'
        line
        """#

        #expect(
            UISinkEscaper.htmlText(raw)
                == #"&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &#39;owner&#39;&#10;line"#
        )
        #expect(
            UISinkEscaper.htmlAttribute(raw)
                == #"&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &#39;owner&#39;&#10;line"#
        )
    }

    @Test("css strings escape quotes backslashes controls and style terminators")
    func cssStringsEscapeQuotesBackslashesControlsAndStyleTerminators() {
        let raw = "body\"; background:url(javascript:alert(1)); \\ \n</style>"

        #expect(
            UISinkEscaper.cssString(raw)
                == #"body\22 ; background:url(javascript:alert(1)); \5c  \a \3c /style\3e "#
        )
    }

    @Test("css url tokens quote safe urls and block unsafe schemes")
    func cssURLTokensQuoteSafeURLsAndBlockUnsafeSchemes() {
        #expect(
            UISinkEscaper.cssURLToken(#"https://example.test/image a".png?token="secret""#)
                == #"url("https://example.test/image a\22 .png?token=\22 secret\22 ")"#
        )
        #expect(UISinkEscaper.cssURLToken("/assets/model card.png") == #"url("/assets/model card.png")"#)
        #expect(UISinkEscaper.cssURLToken("./model card.png") == #"url("./model card.png")"#)
        #expect(UISinkEscaper.cssURLToken("../model card.png") == #"url("../model card.png")"#)
        #expect(UISinkEscaper.cssURLToken("images/model card.png") == #"url("images/model card.png")"#)
        #expect(UISinkEscaper.cssURLToken("javascript:alert(1)") == #"url("about:blank")"#)
        #expect(UISinkEscaper.cssURLToken("") == #"url("about:blank")"#)
        #expect(UISinkEscaper.cssURLToken(" data:text/html,<svg onload=alert(1)>") == #"url("about:blank")"#)
        #expect(UISinkEscaper.cssURLToken("file:///Users/operator/secret.png") == #"url("about:blank")"#)
    }

    @Test("url components percent encode delimiters and controls")
    func urlComponentsPercentEncodeDelimitersAndControls() {
        #expect(
            UISinkEscaper.urlComponent(#"workspace/alpha beta?token="secret"&email=a@example.test"#)
                == "workspace%2Falpha%20beta%3Ftoken%3D%22secret%22%26email%3Da%40example.test"
        )
    }

    @Test("edge controls and empty values are deterministic")
    func edgeControlsAndEmptyValuesAreDeterministic() {
        #expect(UISinkEscaper.htmlText("") == "")
        #expect(UISinkEscaper.cssString("") == "")
        #expect(UISinkEscaper.htmlText("line\r\t\u{0007}\u{007f}") == "line&#13;&#9;&#7;&#127;")
        #expect(UISinkEscaper.cssString("line\r\u{000C}\u{0007}\u{007f}") == #"line\d \c \7 \7f "#)
    }
}
