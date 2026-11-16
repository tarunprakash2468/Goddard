import Foundation
import AppKit

class DaemonManager {
    private var process: Process?
    private var port: Int = 8050
    private var healthTimer: Timer?

    func start(onReady: @escaping (Int) -> Void) {
        // Find goddard executable in PATH or venv
        let venvPaths = [
            FileManager.default.homeDirectoryForCurrentUser.path + "/.gemini/antigravity/scratch/Goddard/.venv/bin/goddard",
            "/usr/local/bin/goddard",
            "/opt/homebrew/bin/goddard"
        ]
        // Also check relative to app bundle
        let executablePath = venvPaths.first { FileManager.default.isExecutableFile(atPath: $0) }
            ?? ProcessInfo.processInfo.environment["GODDARD_EXEC"]

        guard let execPath = executablePath else {
            print("[DaemonManager] goddard executable not found, loading UI without daemon")
            DispatchQueue.main.async { onReady(self.port) }
            return
        }

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: execPath)
        proc.arguments = ["serve", "--port", "\(port)"]
        proc.environment = ProcessInfo.processInfo.environment.merging([
            "GODDARD_OFFLINE_MODE": "true",
            "GODDARD_PORT": "\(port)"
        ]) { _, new in new }

        do {
            try proc.run()
            self.process = proc
            print("[DaemonManager] Started goddard daemon PID \(proc.processIdentifier) on port \(port)")
        } catch {
            print("[DaemonManager] Failed to start daemon: \(error)")
            DispatchQueue.main.async { onReady(self.port) }
            return
        }

        // Poll /api/health until ready (up to 15s)
        pollHealth(port: port, attempts: 30) { ready in
            if !ready { print("[DaemonManager] Daemon health check timed out, loading anyway") }
            DispatchQueue.main.async { onReady(self.port) }
        }
    }

    private func pollHealth(port: Int, attempts: Int, completion: @escaping (Bool) -> Void) {
        guard attempts > 0 else { completion(false); return }
        guard let url = URL(string: "http://127.0.0.1:\(port)/api/health") else { completion(false); return }
        URLSession.shared.dataTask(with: url) { data, response, _ in
            if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 {
                completion(true)
            } else {
                DispatchQueue.global().asyncAfter(deadline: .now() + 0.5) {
                    self.pollHealth(port: port, attempts: attempts - 1, completion: completion)
                }
            }
        }.resume()
    }

    func stop() {
        healthTimer?.invalidate()
        process?.interrupt()
        DispatchQueue.global().asyncAfter(deadline: .now() + 2) { [weak self] in
            self?.process?.terminate()
        }
        print("[DaemonManager] Daemon stopped")
    }
}
