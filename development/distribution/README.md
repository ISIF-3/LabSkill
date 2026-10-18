# 배포 작업

이 폴더는 검토한 공개 파일로 소스와 운영체제별 다운로드 ZIP을 만드는 도구입니다. 실제 사용 폴더 전체를 압축하지 않습니다. GitHub 저장소 생성·push·Release 게시를 자동으로 수행하지 않습니다.

## 포함 범위

`manifest.json`의 정확한 파일 목록만 사용합니다. 새로운 파일은 목록에 명시적으로 추가해야 합니다. `.gitignore`도 같은 공개 파일만 허용합니다. `public-seed/`는 배포자가 선택한 공개 저장소 791개의 고정 시작 목록·분류표·주간 기록입니다. 현재 사용자 목록으로 자동 재생성하지 않습니다.

실사용 `labskill-catalog/catalog/`, `state/`, `cache/`, `snapshots/`, `imports/manual/`와 개인 인증·로그는 읽거나 복사하지 않습니다. 초기 트렌딩 명단과 원본 라이선스는 지정된 파일만 포함합니다. 원본 README·SKILL 본문, 원문 인용, 모델 응답은 공개 seed에 넣지 않습니다. 스킬 이름·설명·경로와 공개 메타데이터, 요약·분류·커밋·출처·등장 이력은 유지합니다. 북마크·메모는 각 사용자 소유입니다.

## 확인과 ZIP 생성

저장소 루트에서 실행합니다. Python 3.10 이상과 표준 라이브러리만 사용합니다. 아래 두 미리보기 명령은 ZIP을 만들지 않습니다.

```bash
python3.11 -B -m unittest discover -s development/distribution -p 'test_*.py' -v
python3.11 development/distribution/package.py --platform source
python3.11 development/distribution/package.py --platform windows
```

Mac 런처는 macOS에서 Xcode Command Line Tools를 설치한 뒤 소스로 재빌드합니다. 출력 경로는 아직 존재하지 않는 절대 경로여야 합니다. 현재 타깃은 Apple Silicon·macOS 12 이상입니다. Python은 포함하지 않습니다.

```bash
zsh native/macos/build.sh "$PWD/dist/macos/LabSkill.app"
python3.11 development/distribution/package.py --platform macos --macos-app dist/macos/LabSkill.app
```

파일 목록을 확인한 다음 필요한 플랫폼의 명령에 `--write`를 붙이면 `dist/LabSkill-source.zip`, `dist/LabSkill-macos-arm64.zip`, `dist/LabSkill-windows.zip`을 만듭니다. 기존 ZIP을 덮어쓰지 않습니다. 다운로드 ZIP의 목록은 공개 seed로 초기화되어 있습니다. `.app` 내부도 실행 파일·아이콘·Info.plist·서명 고지 등 지정 파일만 포함합니다.

```bash
python3.11 development/distribution/package.py --platform source --write
python3.11 development/distribution/package.py --platform windows --write
python3.11 development/distribution/package.py --platform macos --macos-app dist/macos/LabSkill.app --write
```

Windows ZIP은 Python 스크립트와 `.bat`이며 `.exe`나 설치 프로그램이 아닙니다. Python 3.10 이상, WebView2 Runtime과 `labskill-catalog/requirements-windows.txt`의 설치가 필요합니다. 실제 Windows GUI 동작은 아직 검증하지 않았습니다. Mac 빌드는 로컬용 ad-hoc 서명이며 Developer ID 서명·공증을 대체하지 않습니다. 배포 전에 각 대상 운영체제에서 다운로드·압축 해제·실행·종료·로컬 저장을 확인합니다.

## GitHub에 올리기

저장소 이름·공개 범위를 정한 뒤 검토한 소스를 커밋합니다. `.gitignore`는 기본 차단 후 파일별 허용 방식입니다. 새 공개 파일을 추가할 때는 `manifest.json`과 `.gitignore`를 함께 갱신하고 테스트를 실행합니다. 강제 추가(`git add -f`)로 개인 파일을 포함하지 않습니다.

완성된 OS별 ZIP은 GitHub Releases의 Assets에 첨부하면 됩니다. 아래는 게시 전 검토할 **초안 Release**를 만드는 예시이며 이 도구가 실행하지는 않습니다. `OWNER/REPO`와 버전은 실제 배포 대상으로 바꿉니다.

```bash
gh release create v0.1.0 dist/LabSkill-macos-arm64.zip dist/LabSkill-windows.zip --repo OWNER/REPO --draft --title "LabSkill v0.1.0" --notes-file development/distribution/release-notes.md
```

GitHub가 자동으로 제공하는 Source code ZIP은 저장소 소스입니다. 실행 파일이 포함된 OS별 다운로드 ZIP과 구분합니다. [GitHub Releases 안내](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases), [gh release create](https://cli.github.com/manual/gh_release_create)

향후 Python까지 포함하려면 PyInstaller 같은 도구로 운영체제별 빌드·검증을 추가해야 합니다. 외부 GitHub CLI 의존성도 따로 처리해야 합니다. [PyInstaller 공식 설명](https://pyinstaller.org/en/stable/operating-mode.html), [Apple 서명·공증 안내](https://help.apple.com/xcode/mac/current/en.lproj/dev033e997ca.html)
