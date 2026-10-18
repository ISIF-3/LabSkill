import AppKit
import WebKit

@MainActor
final class LauncherDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    private let paths = LauncherPaths(bundleURL: Bundle.main.bundleURL)
    private let catalogURL = URL(string: "http://127.0.0.1:8765/")!
    private var backend: Process?
    private var logHandle: FileHandle?
    private var quitting = false
    private var window: NSWindow!
    private(set) var webView: WKWebView!
    private let loadingLabel = NSTextField(labelWithString: "목록을 불러오는 중…")
    private var waitingForServer = false
    private var serverReady = false
    private var readinessID = UUID()

    func applicationDidFinishLaunching(_ notification: Notification) {
        let menu = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        let open = NSMenuItem(title: "카탈로그 열기", action: #selector(openCatalog(_:)), keyEquivalent: "o")
        open.target = self
        appMenu.addItem(open)
        appMenu.addItem(.separator())
        appMenu.addItem(NSMenuItem(title: "LabSkill 종료", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
        appItem.submenu = appMenu
        menu.addItem(appItem)
        let editItem = NSMenuItem()
        let editMenu = NSMenu(title: "편집")
        for (title, action, key) in [("잘라내기", "cut:", "x"), ("복사", "copy:", "c"),
                                     ("붙여넣기", "paste:", "v"), ("모두 선택", "selectAll:", "a")] {
            editMenu.addItem(NSMenuItem(title: title, action: Selector(action), keyEquivalent: key))
        }
        editItem.submenu = editMenu
        menu.addItem(editItem)
        NSApp.mainMenu = menu
        createWindow()
        connectCatalog()
    }

    @objc private func openCatalog(_ sender: Any?) {
        showWindow()
        guard !waitingForServer else { return }
        if serverReady { webView.load(URLRequest(url: catalogURL)) }
        else { connectCatalog() }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows: Bool) -> Bool {
        showWindow()
        return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    private func createWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1200, height: 820),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "LabSkill"
        window.minSize = NSSize(width: 800, height: 600)
        window.isReleasedWhenClosed = false
        window.center()
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = false
        webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.isHidden = true
        guard let content = window.contentView else { return }
        for view in [webView!, loadingLabel] {
            view.translatesAutoresizingMaskIntoConstraints = false
            content.addSubview(view)
        }
        NSLayoutConstraint.activate([
            webView.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            webView.topAnchor.constraint(equalTo: content.topAnchor),
            webView.bottomAnchor.constraint(equalTo: content.bottomAnchor),
            loadingLabel.centerXAnchor.constraint(equalTo: content.centerXAnchor),
            loadingLabel.centerYAnchor.constraint(equalTo: content.centerYAnchor),
        ])
        showWindow()
    }

    private func showWindow() {
        window.deminiaturize(nil)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func connectCatalog() {
        readinessID = UUID()
        serverReady = false
        loadingLabel.stringValue = "목록을 불러오는 중…"
        loadingLabel.isHidden = false
        webView.isHidden = true
        guard startBackend() else { return }
        waitingForServer = true
        pollServer(until: Date().addingTimeInterval(20), attempt: readinessID)
    }

    private func pollServer(until deadline: Date, attempt: UUID) {
        var request = URLRequest(url: catalogURL.appendingPathComponent("api/status"),
                                 cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 1)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        URLSession.shared.dataTask(with: request) { [weak self] data, response, _ in
            let ready = isLabSkillStatus(response as? HTTPURLResponse, body: data)
            DispatchQueue.main.async {
                guard let self, self.readinessID == attempt, !self.quitting else { return }
                if ready {
                    self.waitingForServer = false
                    self.serverReady = true
                    self.webView.load(URLRequest(url: self.catalogURL))
                } else if Date() >= deadline {
                    self.waitingForServer = false
                    self.showError("카탈로그 서버에 연결하지 못했습니다. 잠시 후 다시 시도하세요.", retry: true)
                } else {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [weak self] in
                        guard let self, self.readinessID == attempt, !self.quitting else { return }
                        self.pollServer(until: deadline, attempt: attempt)
                    }
                }
            }
        }.resume()
    }

    private func startBackend() -> Bool {
        guard backend?.isRunning != true else { return true }
        let files = FileManager.default
        guard files.fileExists(atPath: paths.command.path),
              files.fileExists(atPath: paths.catalog.appendingPathComponent("app.py").path) else {
            showError("앱 옆에 labskill-catalog 폴더가 필요합니다. LabSkill.app과 해당 폴더를 함께 이동하세요.")
            return false
        }
        do {
            try? logHandle?.close()
            logHandle = nil
            try files.createDirectory(at: paths.log.deletingLastPathComponent(), withIntermediateDirectories: true)
            if !files.fileExists(atPath: paths.log.path) {
                guard files.createFile(atPath: paths.log.path, contents: nil) else {
                    throw CocoaError(.fileWriteUnknown)
                }
            }
            let handle = try FileHandle(forWritingTo: paths.log)
            try handle.seekToEnd()
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/bin/zsh")
            process.arguments = ["-l", paths.command.path, "--no-open"]
            process.currentDirectoryURL = paths.catalog
            process.standardInput = FileHandle.nullDevice
            process.standardOutput = handle
            process.standardError = handle
            process.terminationHandler = { [weak self] process in
                DispatchQueue.main.async { self?.processDidExit(process) }
            }
            logHandle = handle
            backend = process
            do {
                try process.run()
            } catch {
                backend = nil
                try? logHandle?.close()
                logHandle = nil
                throw error
            }
            return true
        } catch {
            showError("시작하지 못했습니다: \(error.localizedDescription)", retry: true)
            return false
        }
    }

    private func processDidExit(_ process: Process) {
        guard backend === process else { return }
        backend = nil
        try? logHandle?.close()
        logHandle = nil
        if quitting {
            NSApp.reply(toApplicationShouldTerminate: true)
        } else if process.terminationStatus != 0 {
            readinessID = UUID()
            waitingForServer = false
            serverReady = false
            showError("실행이 중단되었습니다 (코드 \(process.terminationStatus)). Python 3.10 이상이 설치되어 있는지 확인하세요.", retry: true)
        }
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        let destination = navigationDestination(navigationAction.request.url,
                                                isUserLink: navigationAction.navigationType == .linkActivated)
        switch destination {
        case .catalog:
            decisionHandler(.allow)
        case .browser:
            if let url = navigationAction.request.url { NSWorkspace.shared.open(url) }
            decisionHandler(.cancel)
        case .blocked:
            decisionHandler(.cancel)
        }
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        let destination = navigationDestination(navigationAction.request.url,
                                                isUserLink: navigationAction.navigationType == .linkActivated)
        if destination == .catalog { webView.load(navigationAction.request) }
        else if destination == .browser, let url = navigationAction.request.url { NSWorkspace.shared.open(url) }
        return nil
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        loadingLabel.isHidden = true
        webView.isHidden = false
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        navigationFailed(error)
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        navigationFailed(error)
    }

    private func navigationFailed(_ error: Error) {
        guard (error as NSError).code != NSURLErrorCancelled, !quitting else { return }
        serverReady = false
        showError("화면을 불러오지 못했습니다: \(error.localizedDescription)", retry: true)
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let process = backend, process.isRunning else { return .terminateNow }
        guard !quitting else { return .terminateLater }
        quitting = true
        // SIGINT follows the Python server's existing Ctrl+C cleanup path.
        process.interrupt()
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { [weak self, weak process] in
            guard let self, let process, self.quitting, self.backend === process, process.isRunning else { return }
            self.quitting = false
            sender.reply(toApplicationShouldTerminate: false)
            self.showWindow()
            self.showError("아직 실행 중인 작업을 종료하고 있습니다. 잠시 후 다시 종료하세요.")
        }
        return .terminateLater
    }

    private func showError(_ message: String, retry: Bool = false) {
        let alert = NSAlert()
        alert.messageText = "LabSkill을 확인해 주세요"
        alert.informativeText = message + "\n\n실행 기록: " + paths.log.path
        alert.alertStyle = .warning
        alert.addButton(withTitle: retry ? "다시 시도" : "확인")
        if retry { alert.addButton(withTitle: "닫기") }
        NSApp.activate(ignoringOtherApps: true)
        if alert.runModal() == .alertFirstButtonReturn, retry {
            DispatchQueue.main.async { [weak self] in self?.connectCatalog() }
        }
    }
}

#if !NATIVE_SMOKE_TEST
@main
struct LauncherMain {
    @MainActor static func main() {
        let application = NSApplication.shared
        let delegate = LauncherDelegate()
        application.delegate = delegate
        application.setActivationPolicy(.regular)
        withExtendedLifetime(delegate) { application.run() }
    }
}
#endif
