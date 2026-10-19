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

func backendFailureMessage(status: Int32) -> String? {
    switch status {
    case 0:
        return nil
    case 69:
        return "Python 3.10 이상을 찾지 못했습니다. 설치 여부를 확인하세요."
    case 98:
        return "LabSkill 전용 포트 18765가 이미 사용 중입니다. 실행 중인 앱을 확인한 뒤 다시 시도하세요."
    default:
        return "실행이 중단되었습니다 (코드 \(status)). 실행 로그를 확인하세요."
    }
}

func navigationDestination(_ url: URL?, isUserLink: Bool) -> NavigationDestination {
    guard let url, url.user == nil, url.password == nil,
          let scheme = url.scheme?.lowercased(), let host = url.host?.lowercased(),
          scheme == "http" || scheme == "https" else { return .blocked }
    if host == "127.0.0.1", url.port == 18765, scheme == "http" { return .catalog }
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
