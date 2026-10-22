# LabSkill

GitHub 트렌딩과 분야별 도구를 한국어로 탐색하는 로컬 앱입니다. 기능별 목록·검색·분류, 북마크·메모, GitHub 주소 추가를 제공합니다. v0.2.0의 초기 공개 목록은 1286개이며, 이후 추가한 정보와 개인 메모·북마크는 사용하는 컴퓨터에 저장합니다.

**+ 추가** 버튼으로 GitHub 저장소를 등록하고 Python으로 분류합니다. 내 라이브러리에서는 컬렉션과 개인 메모를 관리합니다. 신규 등록이나 실제 내용 변경에는 7일간 New!를 표시하며, 과거 명단의 첫 정보 보강에는 표시하지 않습니다.

과거 트렌딩 기록은 최근 1년인 **2025-10-22~2026-10-22** 범위로 확대했습니다. 고정한 원본에는 2026-10-21까지 365일의 기록과 고유 저장소 1266개가 있으며, 2026-10-22 기록은 아직 게시되지 않았습니다. 화면에 `365/366일 기록 · 원본 없는 날짜 1일`을 표시합니다. 목록은 60개씩 페이지로 탐색하며 검색·필터·총개수는 전체 목록을 기준으로 합니다.

## 다운로드와 실행

[최신 다운로드](https://github.com/ISIF-3/LabSkill/releases/latest)에서 운영체제별 ZIP을 내려받아 쓰기 가능한 폴더에 압축을 풉니다. **현재 배포 방식은 Python 3.10 이상 설치가 필요합니다.** Python을 포함한 설치 프로그램이나 Windows `.exe`는 아닙니다.

| 운영체제 | 실행 방법 | 추가 조건 |
| --- | --- | --- |
| macOS 12 이상·Apple Silicon | `LabSkill.app` 실행 | 앱 옆의 `labskill-catalog/` 폴더 유지 |
| Windows | `LabSkill.bat` 실행 | WebView2 Runtime, `requirements-windows.txt` 설치 필요·실제 Windows GUI 미검증 |

v0.2.0의 설치 의존성은 이전 버전과 같습니다. Python 3.11 등 Python 3.10 이상이 이미 설치되어 있으면 그대로 사용합니다. 기존 목록·북마크·컬렉션·메모를 보존하며, 포트 설정 없이 앱을 평소처럼 실행합니다.

설치·종료·오프라인 실행은 [시작하기](시작하기.md)를 참고하세요. 저장된 목록 탐색에는 GitHub 로그인이 필요하지 않습니다. 새 정보 수집에는 인터넷과 GitHub CLI의 본인 계정 로그인이 필요합니다. 기본 Python 분류는 모델 호출과 모델 토큰 사용이 0이며, Codex나 모델 API를 사용하지 않습니다.

현재 Mac 런처는 Developer ID 서명·Apple 공증을 받은 배포물이 아닙니다. 일반 사용자 배포 전에 서명·공증과 다운로드 후 실행 확인이 필요합니다. [Apple 배포 안내](https://help.apple.com/xcode/mac/current/en.lproj/dev033e997ca.html)

## 소스에서 실행·배포 준비

저장소 소스를 받은 뒤 최초 한 번 실행합니다. 이 명령은 검토한 공개 seed로 **없는 파일만** 초기화하며 기존 개인 목록을 덮어쓰지 않습니다.

```bash
python3.11 development/distribution/package.py --initialize
```

소스에는 빌드된 `LabSkill.app`이 없으므로 Mac에서는 먼저 런처를 빌드해야 합니다. Xcode Command Line Tools가 설치된 macOS에서 실행합니다.

```bash
zsh native/macos/build.sh "$PWD/LabSkill.app"
```

이후 [시작하기](시작하기.md)의 순서대로 실행합니다. Windows는 소스의 `LabSkill.bat`을 사용합니다. ZIP 포함 파일 미리보기와 GitHub Release 등록 절차는 소스 저장소의 [배포 작업 안내](https://github.com/ISIF-3/LabSkill/tree/main/development/distribution)에 있습니다. ZIP을 만들거나 외부에 업로드하는 작업은 자동으로 실행되지 않습니다.

실사용 `catalog/`·`state/`·`cache/`, 수동 추가 원본 `imports/manual/`, 로그와 인증 파일은 Git·다운로드 ZIP에 포함하지 않습니다. 별도로 검토한 공개 seed, 출처·커밋·최근 1년 트렌딩 이력과 원본 라이선스 고지를 포함합니다. 명단 원본은 커밋 `83e0423605b47c34751141d79deb16ab3942504b`로 고정했습니다. 같은 범위의 재실행 명령은 [트렌딩 명단 안내](labskill-catalog/imports/README.md)에 있습니다. 원본 README·SKILL 본문과 모델 원문 응답은 seed에서 제외하고 사용자용 요약·분류·스킬 이름·설명·경로를 유지합니다. 공개 seed에 원문 인용 근거가 없는 항목은 원문을 확인한 근거가 있는 것처럼 표시하지 않습니다.
