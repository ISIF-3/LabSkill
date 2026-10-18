"""Windows desktop window for the shared LabSkill app: python -B -m desktop."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import threading

from app import AppController, create_server, is_existing_app


PORT = 8765
URL = f"http://127.0.0.1:{PORT}/"


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "labskill-catalog"
    return Path(__file__).resolve().parent


def _show_error(message: str):
    if sys.platform == "win32":
        import ctypes
        try:
            ctypes.windll.user32.MessageBoxW(None, message, "LabSkill", 0x10)
            return
        except (AttributeError, OSError):
            pass
    print(message, file=sys.stderr)


def main() -> int:
    try:
        import webview
    except ImportError:
        _show_error("LabSkill 데스크톱 창에 필요한 패키지가 없습니다.\n"
                    "labskill-catalog 폴더에서 다음 명령을 실행하세요:\n"
                    "python -m pip install -r requirements-windows.txt\n"
                    "Microsoft WebView2 Runtime도 필요합니다.")
        return 1

    controller = None
    server = None
    thread = None
    serving = False
    try:
        if not is_existing_app(PORT):
            controller = AppController(_app_root())
            try:
                server = create_server(controller, PORT)
            except OSError as exc:
                if not is_existing_app(PORT):
                    raise RuntimeError(f"{PORT} 포트를 사용할 수 없습니다. 다른 프로그램의 사용 여부를 확인하세요.") from exc
            if server is not None:
                thread = threading.Thread(target=server.serve_forever,
                                          kwargs={"poll_interval": 0.3},
                                          name="labskill-http", daemon=True)
                thread.start()
                serving = True
                controller.refresh()
                controller.start_scheduler()

        profile = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "LabSkill" / "WebView2"
        profile.mkdir(parents=True, exist_ok=True)
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        webview.settings["ALLOW_FILE_URLS"] = False
        webview.create_window("LabSkill", URL, width=1200, height=820,
                              min_size=(800, 600), text_select=True, js_api=None)
        webview.start(gui="edgechromium", private_mode=False, storage_path=str(profile),
                      icon=str(_app_root() / "web/assets/app-icon.ico"))
        return 0
    except Exception as exc:
        _show_error(f"LabSkill을 시작할 수 없습니다.\n{exc}\n"
                    "Windows에서는 Microsoft WebView2 Runtime이 필요합니다.")
        return 1
    finally:
        if controller is not None:
            controller.close()
        if server is not None:
            try:
                if serving:
                    server.shutdown()
            finally:
                server.server_close()
        if serving:
            thread.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
