import Foundation

struct LauncherPaths {
    let catalog: URL
    var command: URL { catalog.appendingPathComponent("LabSkill.command") }
    var log: URL { catalog.appendingPathComponent("state/launcher.log") }

    init(bundleURL: URL) {
        catalog = bundleURL.deletingLastPathComponent()
            .appendingPathComponent("labskill-catalog", isDirectory: true)
    }
}

enum NavigationDestination {
    case catalog, browser, blocked
}

func navigationDestination(_ url: URL?, isUserLink: Bool) -> NavigationDestination {
    guard let url, url.user == nil, url.password == nil,
          let scheme = url.scheme?.lowercased(), let host = url.host?.lowercased(),
          scheme == "http" || scheme == "https" else { return .blocked }
    if host == "127.0.0.1", url.port == 8765, scheme == "http" { return .catalog }
    guard isUserLink, host != "localhost", host != "::1", host != "[::1]",
          !host.hasPrefix("127.") else { return .blocked }
    return .browser
}

func isLabSkillStatus(_ response: HTTPURLResponse?, body: Data?) -> Bool {
    guard let response, response.statusCode == 200,
          navigationDestination(response.url, isUserLink: false) == .catalog,
          response.value(forHTTPHeaderField: "X-LabSkill-App") == "local-v1",
          let body, body.count <= 65536,
          let status = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
          status["running"] is Bool else { return false }
    return true
}
