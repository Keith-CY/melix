import Testing
@testable import AppMain

@Test
@MainActor
func placeholderMenuBarTest() {
    MelixMenuBarApp.main()
    #expect(Bool(true))
}
