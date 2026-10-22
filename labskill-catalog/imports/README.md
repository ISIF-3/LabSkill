# 트렌딩 명단 원본

v0.2.0의 `trending-history-expanded.json`은 antonkomarev/github-trending-archive의 고정 커밋 `83e0423605b47c34751141d79deb16ab3942504b`에서 읽은 전역 일간 기록입니다. 요청 범위는 양 끝을 포함한 **2025-10-22~2026-10-22**입니다. 이 커밋에는 2026-10-21까지 365일의 원본이 있으며, 2026-10-22 기록은 아직 게시되지 않았습니다. 대소문자를 구분하지 않고 중복을 합친 명단은 고유 저장소 **1266개**입니다.

JSON에 각 기록의 경로·Git blob 해시·순위·날짜와 중복 제거 결과를 함께 보관하며, 내려받은 원본의 Git blob 해시를 대조합니다. 원본이 없는 날짜를 빈 명단으로 만들지 않습니다. `coverage`의 `expected_days=366`, `available_days=365`, `missing_dates=["2026-10-22"]`를 화면의 `365/366일 기록 · 원본 없는 날짜 1일` 표시에 사용합니다. 날짜별 순위는 일간 순위이며 현재 별 수나 과거 주간 증가량을 추측해 넣지 않습니다.

## 같은 범위 다시 가져오기

저장소 루트에서 Python 3.10 이상과 본인 계정으로 로그인한 GitHub CLI를 사용합니다. 아래 명령은 고정 원본을 읽어 확장 명단 파일을 만듭니다.

```bash
python3.11 development/import_history.py \
  --start 2025-10-22 --end 2026-10-22 \
  --ref 83e0423605b47c34751141d79deb16ab3942504b \
  --root labskill-catalog
```

앱을 다시 시작하면 명단을 기존 카탈로그와 비교해 합칩니다. 기존 정보를 보존하고 추가 정보가 필요한 저장소의 현재 GitHub 자료를 읽어 Python으로 기능을 분류합니다. 모델 호출·모델 토큰 사용은 0입니다. 같은 manifest의 재실행은 처리 진행을 초기화하지 않으며 북마크·컬렉션·개인 메모를 삭제하지 않습니다. 남은 정보 수집은 앱의 **정리 이어가기**에서 계속할 수 있습니다.

과거 명단의 첫 정보 보강에는 New!를 붙이지 않습니다. 이후 신규 등록이나 README·스킬 내용·설명의 실제 변경에는 7일간 New! 표시를 유지합니다. 저장소 코드나 설치 명령은 실행하지 않습니다.

기존 `trending-history-2026-04-18_2026-10-18.json`은 이전 자료로 보존합니다. 확장 파일이 있으면 앱은 이를 우선 사용합니다. 정식 주간 기록은 `../weekly/YYYY-Www.json`에 저장합니다. 같은 주의 수동 갱신은 그 주 파일을 갱신하며 이전 주 파일을 유지합니다.

원본과 고정 커밋의 라이선스: [github-trending-archive](https://github.com/antonkomarev/github-trending-archive), [MIT 라이선스](https://github.com/antonkomarev/github-trending-archive/blob/83e0423605b47c34751141d79deb16ab3942504b/LICENSE). `licenses/antonkomarev-MIT.txt`에도 원본 라이선스 고지를 보관합니다.

모든 저장소의 실제 목록·분류 결과 원본은 계속 `../catalog/catalog.json` 하나입니다. imports 파일은 출처를 보관하는 원본 자료이며 가져오기 명령은 GitHub 원격 저장소에 파일을 올리지 않습니다.
