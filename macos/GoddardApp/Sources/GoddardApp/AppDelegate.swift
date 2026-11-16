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

        // Backdrop Submenu
        let backdropMenuItem = NSMenuItem(title: "Backdrop", action: nil, keyEquivalent: "")
        let backdropMenu = NSMenu(title: "Backdrop")
        backdropMenuItem.submenu = backdropMenu
        
        let itemGlass = NSMenuItem(title: "Liquid Glass", action: #selector(setBackdropLiquidGlass), keyEquivalent: "1")
        itemGlass.keyEquivalentModifierMask = [.command, .option]
        backdropMenu.addItem(itemGlass)

        let itemSpace = NSMenuItem(title: "Deep Space", action: #selector(setBackdropDeepSpace), keyEquivalent: "2")
        itemSpace.keyEquivalentModifierMask = [.command, .option]
        backdropMenu.addItem(itemSpace)

        let itemStudio = NSMenuItem(title: "Design Studio", action: #selector(setBackdropDesignStudio), keyEquivalent: "3")
        itemStudio.keyEquivalentModifierMask = [.command, .option]
        backdropMenu.addItem(itemStudio)
        
        viewMenu.addItem(backdropMenuItem)

        // Camera Focus Submenu
        let cameraMenuItem = NSMenuItem(title: "Camera Focus", action: nil, keyEquivalent: "")
        let cameraMenu = NSMenu(title: "Camera Focus")
        cameraMenuItem.submenu = cameraMenu

        let camFull = NSMenuItem(title: "Full Vehicle", action: #selector(setCameraFull), keyEquivalent: "0")
        camFull.keyEquivalentModifierMask = [.command, .option]
        cameraMenu.addItem(camFull)

        let camEngines = NSMenuItem(title: "Engine Cluster & Base", action: #selector(setCameraEngines), keyEquivalent: "e")
        camEngines.keyEquivalentModifierMask = [.command, .option]
        cameraMenu.addItem(camEngines)

        let camFins = NSMenuItem(title: "Fins & Aero Surfaces", action: #selector(setCameraFins), keyEquivalent: "f")
        camFins.keyEquivalentModifierMask = [.command, .option]
        cameraMenu.addItem(camFins)

        let camNose = NSMenuItem(title: "Nose Cone & Fairing", action: #selector(setCameraNose), keyEquivalent: "n")
        camNose.keyEquivalentModifierMask = [.command, .option]
        cameraMenu.addItem(camNose)

        viewMenu.addItem(cameraMenuItem)
        viewMenu.addItem(NSMenuItem.separator())

        // Standard Actions
        viewMenu.addItem(NSMenuItem(title: "Toggle Copilot", action: #selector(toggleCopilot), keyEquivalent: "k"))
        viewMenu.addItem(NSMenuItem(title: "Re-Simulate", action: #selector(reSimulate), keyEquivalent: "r"))
        viewMenu.addItem(NSMenuItem(title: "Show Diff", action: #selector(showDiff), keyEquivalent: "d"))
        viewMenu.addItem(NSMenuItem(title: "Export Bundle", action: #selector(exportBundle), keyEquivalent: "e"))
        
        NSApp.mainMenu = menu
    }

    @objc func setBackdropLiquidGlass() {
        windowController?.glassWebView?.evaluateJavaScript("setBackdropMode('liquid-glass')", completionHandler: nil)
    }
    @objc func setBackdropDeepSpace() {
        windowController?.glassWebView?.evaluateJavaScript("setBackdropMode('deep-space')", completionHandler: nil)
    }
    @objc func setBackdropDesignStudio() {
        windowController?.glassWebView?.evaluateJavaScript("setBackdropMode('cad-studio')", completionHandler: nil)
    }

    @objc func setCameraFull() {
        windowController?.glassWebView?.evaluateJavaScript("setCameraFocus('full')", completionHandler: nil)
    }
    @objc func setCameraEngines() {
        windowController?.glassWebView?.evaluateJavaScript("setCameraFocus('engines')", completionHandler: nil)
    }
    @objc func setCameraFins() {
        windowController?.glassWebView?.evaluateJavaScript("setCameraFocus('fins')", completionHandler: nil)
    }
    @objc func setCameraNose() {
        windowController?.glassWebView?.evaluateJavaScript("setCameraFocus('nose')", completionHandler: nil)
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
