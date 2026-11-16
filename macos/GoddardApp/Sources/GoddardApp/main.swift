import AppKit

// NSApplication.shared must be called on the main thread.
// AppDelegate is @MainActor-isolated; we construct it via
// MainActor.assumeIsolated which is safe here because
// NSApplicationMain / CommandLine entry always begins on the main thread.
let app = NSApplication.shared
let delegate = AppDelegate.shared
app.delegate = delegate
app.run()
