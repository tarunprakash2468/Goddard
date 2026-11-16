import AppKit
import WebKit

class BridgeHandler: NSObject, WKScriptMessageHandler {
    private var isMuted = false

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any],
              let action = body["action"] as? String else { return }

        switch action {
        case "haptic":
            let style = (body["style"] as? String) ?? "generic"
            performHaptic(style: style)

        case "playSound":
            if !isMuted, let soundName = body["sound"] as? String {
                playAeroCue(name: soundName)
            }

        case "toggleMute":
            isMuted = (body["muted"] as? Bool) ?? !isMuted

        case "windowControl":
            DispatchQueue.main.async {
                guard let window = NSApp.mainWindow else { return }
                switch body["command"] as? String {
                case "minimize": window.miniaturize(nil)
                case "zoom": window.zoom(nil)
                case "close": window.close()
                default: break
                }
            }

        default:
            break
        }
    }

    private func performHaptic(style: String) {
        let performer = NSHapticFeedbackManager.defaultPerformer
        switch style {
        case "alignment": performer.perform(.alignment, performanceTime: .now)
        case "levelChange": performer.perform(.levelChange, performanceTime: .now)
        default: performer.perform(.generic, performanceTime: .now)
        }
    }

    private func playAeroCue(name: String) {
        // Map sound names to system sounds
        let soundMap: [String: String] = [
            "complete": "Glass",
            "touchdown": "Submarine",
            "alert": "Sosumi",
            "warning": "Basso",
            "click": "Pop"
        ]
        if let systemName = soundMap[name], let sound = NSSound(named: NSSound.Name(systemName)) {
            sound.play()
        }
    }
}
