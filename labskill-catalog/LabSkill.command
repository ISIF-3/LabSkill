#!/bin/zsh -l
# Double-click in Finder; use the same CLI login and tools as your login shell.
cd -- "${0:A:h}" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$HOME/.npm-global/bin:$PATH"
for candidate in python3.11 python3.12 python3.13 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
    exec "$candidate" -B -m app "$@"
  fi
done
print 'LabSkill에는 Python 3.10 이상이 필요합니다. 설치 후 다시 실행하세요.'
read -r '?Enter를 누르면 닫힙니다. '
exit 69
