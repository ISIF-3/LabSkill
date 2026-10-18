import Foundation

@main
struct LauncherPathsTests {
    static func main() {
        for parent in ["/tmp/skill finder", "/tmp/한글 폴더/relocated"] {
            let paths = LauncherPaths(bundleURL: URL(fileURLWithPath: parent + "/LabSkill.app"))
            precondition(paths.catalog.path == parent + "/labskill-catalog")
            precondition(paths.command.path == parent + "/labskill-catalog/LabSkill.command")
            precondition(paths.log.path == parent + "/labskill-catalog/state/launcher.log")
        }
        let cases: [(String, Bool, NavigationDestination)] = [
            ("http://127.0.0.1:8765/", false, .catalog),
            ("http://127.0.0.1:8765/?search=한국어#saved", true, .catalog),
            ("https://github.com/openai/codex", true, .browser),
            ("https://github.com/openai/codex", false, .blocked),
            ("http://127.0.0.1:8000/", true, .blocked),
            ("http://localhost:8765/", true, .blocked),
            ("https://127.0.0.1:8765/", true, .blocked),
            ("file:///etc/passwd", true, .blocked),
            ("javascript:alert(1)", true, .blocked),
            ("data:text/html,test", true, .blocked),
            ("http://name@127.0.0.1:8765/", true, .blocked),
        ]
        for (address, isUserLink, expected) in cases {
            precondition(navigationDestination(URL(string: address), isUserLink: isUserLink) == expected,
                         "Unsafe navigation routing: " + address)
        }
        precondition(navigationDestination(nil, isUserLink: true) == .blocked)
        let statusURL = URL(string: "http://127.0.0.1:8765/api/status")!
        let validResponse = HTTPURLResponse(url: statusURL, statusCode: 200, httpVersion: nil,
                                            headerFields: ["X-LabSkill-App": "local-v1"])!
        precondition(isLabSkillStatus(validResponse, body: Data("{\"running\":false}".utf8)))
        precondition(!isLabSkillStatus(validResponse, body: Data("{}".utf8)))
        let unrelatedResponse = HTTPURLResponse(url: statusURL, statusCode: 200,
                                                httpVersion: nil, headerFields: nil)!
        precondition(!isLabSkillStatus(unrelatedResponse, body: Data("{\"running\":false}".utf8)))
        print("PASS: relative paths, navigation policy, and server identity validation")
    }
}
