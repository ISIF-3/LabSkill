LabSkill은 공개 GitHub 도구를 기능별로 탐색하는 로컬 앱입니다. 791개 공개 시작 목록과 6개월 트렌딩 출처·이력을 포함합니다. 이후 추가한 도구와 개인 메모·북마크는 각 사용자의 컴퓨터에 저장합니다.

- macOS ZIP: Apple Silicon·macOS 12 이상, `LabSkill.app` 실행. Python 3.10 이상을 별도로 설치해야 합니다. 현재 Developer ID 서명·Apple 공증을 받은 배포물이 아닙니다.
- Windows ZIP: `LabSkill.bat` 실행. Python 3.10 이상, WebView2 Runtime, `requirements-windows.txt` 설치가 필요합니다. 실제 Windows GUI 실행은 아직 검증하지 않았습니다. `.exe`나 설치 프로그램이 아닙니다.
- 새 GitHub 정보 수집에는 본인의 GitHub CLI 로그인이 필요합니다. 저장된 목록은 오프라인에서도 탐색할 수 있습니다. 기본 분류에는 Codex나 모델 API가 필요하지 않습니다.
- 압축을 쓰기 가능한 폴더에 풀고 앱과 `labskill-catalog/`를 함께 둡니다. 기존 사용자는 자신의 목록·메모·북마크를 별도로 보관하며 새 ZIP으로 기존 데이터 폴더를 덮어쓰지 마세요.

상세 실행 방법은 ZIP의 `시작하기.md`와 `README.md`를 참고하세요.

이번 버전에는 GitHub 링크 직접 추가, Python 분류, 컬렉션과 개인 메모 저장, 내용 변경 후 7일간 New! 표시가 포함됩니다. 실제 Mac 앱 창에서 공개 저장소 링크 추가·컬렉션 생성/이름 변경/삭제·메모 재열기를 확인했습니다. 테스트 추가에는 GitHub API 4회, 모델 호출 0회를 사용했습니다.
