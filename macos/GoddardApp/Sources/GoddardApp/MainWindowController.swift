import AppKit
import WebKit

@MainActor
class MainWindowController: NSWindowController, WKNavigationDelegate {
    var glassWebView: WKWebView?
    private let daemonPort: Int

    init(daemonPort: Int) {
        self.daemonPort = daemonPort
        let contentRect = NSRect(x: 0, y: 0, width: 1400, height: 900)
        let styleMask: NSWindow.StyleMask = [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView]
        let window = NSWindow(contentRect: contentRect, styleMask: styleMask, backing: .buffered, defer: false)
        super.init(window: window)
        setupWindow()
    }

    required init?(coder: NSCoder) { fatalError("not supported") }

    private func setupWindow() {
        guard let window else { return }
        window.title = "Goddard — Aerospace Design Suite"
        window.titlebarAppearsTransparent = true
        window.isMovableByWindowBackground = true
        window.center()

        // NSVisualEffectView — Liquid Glass backdrop
        let effectView = NSVisualEffectView(frame: window.contentView!.bounds)
        effectView.autoresizingMask = [.width, .height]
        effectView.blendingMode = .behindWindow
        effectView.material = .underWindowBackground
        effectView.state = .active
        window.contentView?.addSubview(effectView)

        // WKWebView — transparent, over the effect view
        let config = WKWebViewConfiguration()
        let contentController = config.userContentController
        let bridgeHandler = BridgeHandler()
        contentController.add(bridgeHandler, name: "goddardBridge")

        let webView = WKWebView(frame: window.contentView!.bounds, configuration: config)
        webView.autoresizingMask = [.width, .height]
        // Make the web view transparent so the NSVisualEffectView shows through
        webView.setValue(false, forKey: "drawsBackground")
        webView.underPageBackgroundColor = .clear
        webView.navigationDelegate = self
        window.contentView?.addSubview(webView)
        self.glassWebView = webView

        // Load the local daemon
        let url = URL(string: "http://127.0.0.1:\(daemonPort)/")!
        webView.load(URLRequest(url: url))
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        // Retry after 1 second if daemon isn't ready yet
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in
            guard let self, let url = URL(string: "http://127.0.0.1:\(self.daemonPort)/") else { return }
            webView.load(URLRequest(url: url))
        }
    }
}
