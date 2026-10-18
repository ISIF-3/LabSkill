# LabSkill

GitHub 트렌딩과 분야별 도구를 한국어로 탐색하는 로컬 앱입니다. 기능별 목록·검색·분류, 북마크·메모, GitHub 주소 추가를 제공합니다. 초기 공개 목록은 791개이며, 이후 추가한 정보와 개인 메모·북마크는 사용하는 컴퓨터에 저장합니다.

+ 추가 버튼으로 GitHub 저장소를 등록하고 Python으로 분류합니다. 내 라이브러리에서는 컬렉션과 개인 메모를 관리하며, 새로 추가되거나 내용이 바뀐 도구에는 7일간 New!를 표시합니다.

## 다운로드와 실행

[최신 다운로드](https://github.com/ISIF-3/LabSkill/releases/latest)에서 운영체제별 ZIP을 내려받아 쓰기 가능한 폴더에 압축을 풉니다. **현재 배포 방식은 Python 3.10 이상 설치가 필요합니다.** Python을 포함한 설치 프로그램이나 Windows `.exe`는 아닙니다.

| 운영체제 | 실행 방법 | 추가 조건 |
| --- | --- | --- |
| macOS 12 이상·Apple Silicon | `LabSkill.app` 실행 | 앱 옆의 `labskill-catalog/` 폴더 유지 |
| Windows | `LabSkill.bat` 실행 | WebView2 Runtime, `requirements-windows.txt` 설치 필요·실제 Windows GUI 미검증 |

설치·종료·오프라인 실행은 [시작하기](시작하기.md)를 참고하세요. 저장된 목록 탐색에는 GitHub 로그인이 필요하지 않습니다. 새 정보 수집에는 인터넷과 GitHub CLI의 본인 계정 로그인이 필요합니다. 기본 분류에는 Codex나 모델 API를 사용하지 않습니다.

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

실사용 `catalog/`·`state/`·`cache/`, 수동 추가 원본 `imports/manual/`, 로그와 인증 파일은 Git·다운로드 ZIP에 포함하지 않습니다. 별도로 검토한 공개 seed, 출처·커밋·6개월 트렌딩 이력과 원본 라이선스 고지를 포함합니다. 원본 README·SKILL 본문과 모델 원문 응답은 seed에서 제외하고 사용자용 요약·분류·스킬 이름·설명·경로를 유지합니다. 공개 seed에 원문 인용 근거가 없는 항목은 원문을 확인한 근거가 있는 것처럼 표시하지 않습니다.
