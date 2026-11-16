import AppKit
import WebKit

@MainActor
class AppDelegate: NSObject, NSApplicationDelegate {
    static let shared = AppDelegate()

    var windowController: MainWindowController?
    var daemonManager: DaemonManager?

    func applicationDidFinishLaunching(_ notification: Notification) {
        setupMainMenu()
        daemonManager = DaemonManager()
        daemonManager?.start { [weak self] port in
            DispatchQueue.main.async {
                self?.windowController = MainWindowController(daemonPort: port)
                self?.windowController?.showWindow(nil)
            }
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        daemonManager?.stop()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    private func setupMainMenu() {
        let menu = NSMenu()
        let appMenuItem = NSMenuItem()
        menu.addItem(appMenuItem)
        let appMenu = NSMenu()
        appMenuItem.submenu = appMenu
        appMenu.addItem(NSMenuItem(title: "Quit Goddard", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
        
        let viewMenuItem = NSMenuItem(title: "View", action: nil, keyEquivalent: "")
        menu.addItem(viewMenuItem)
        let viewMenu = NSMenu(title: "View")
        viewMenuItem.submenu = viewMenu
        viewMenu.addItem(NSMenuItem(title: "Toggle Copilot", action: #selector(toggleCopilot), keyEquivalent: "k"))
        viewMenu.addItem(NSMenuItem(title: "Re-Simulate", action: #selector(reSimulate), keyEquivalent: "r"))
        viewMenu.addItem(NSMenuItem(title: "Show Diff", action: #selector(showDiff), keyEquivalent: "d"))
        viewMenu.addItem(NSMenuItem(title: "Export Bundle", action: #selector(exportBundle), keyEquivalent: "e"))
        
        NSApp.mainMenu = menu
    }

    @objc func toggleCopilot() {
        windowController?.glassWebView?.evaluateJavaScript("toggleCopilotDrawer()", completionHandler: nil)
    }
    @objc func reSimulate() {
        windowController?.glassWebView?.evaluateJavaScript("triggerResimulateCurrent()", completionHandler: nil)
    }
    @objc func showDiff() {
        windowController?.glassWebView?.evaluateJavaScript("toggleDiffModal()", completionHandler: nil)
    }
    @objc func exportBundle() {
        windowController?.glassWebView?.evaluateJavaScript("triggerExportBundle()", completionHandler: nil)
    }
}
