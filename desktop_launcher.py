"""
TSBT Video Generator — Standalone Desktop App
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PySide6 QWebEngineView로 Streamlit 앱을 완전 독립 데스크탑 앱으로 실행.
Chrome/Edge 불필요 — 자체 Chromium 엔진 내장.
"""

import subprocess
import sys
import time
import os
import atexit
import socket

# ── Config ──────────────────────────────────────────
STREAMLIT_PORT = 8503
APP_DIR = os.path.dirname(os.path.abspath(__file__))
APP_FILE = os.path.join(APP_DIR, "app.py")
APP_URL = f"http://127.0.0.1:{STREAMLIT_PORT}"

_streamlit_proc = None


def _is_port_open(port, timeout=1.0):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except (ConnectionRefusedError, OSError, TimeoutError):
        return False


def _wait_for_server(port, max_wait=30):
    for _ in range(max_wait * 4):
        if _is_port_open(port):
            return True
        time.sleep(0.25)
    return False


def start_streamlit():
    global _streamlit_proc
    cmd = [
        sys.executable, "-m", "streamlit", "run", APP_FILE,
        "--server.port", str(STREAMLIT_PORT),
        "--server.headless", "true",
        "--server.address", "127.0.0.1",
        "--browser.gatherUsageStats", "false",
        "--theme.base", "dark",
    ]
    _streamlit_proc = subprocess.Popen(
        cmd, cwd=APP_DIR,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return _streamlit_proc


def stop_streamlit():
    global _streamlit_proc
    if _streamlit_proc and _streamlit_proc.poll() is None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/pid", str(_streamlit_proc.pid), "/f", "/t"],
                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            _streamlit_proc.terminate()
        try:
            _streamlit_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _streamlit_proc.kill()
        _streamlit_proc = None


def main():
    atexit.register(stop_streamlit)

    # 1. Start Streamlit server
    print("[TSBT] Starting Streamlit server...")
    start_streamlit()

    if not _wait_for_server(STREAMLIT_PORT):
        print("[ERROR] Streamlit did not start in time.")
        stop_streamlit()
        sys.exit(1)
    print("[OK] Server ready!")

    # 2. Launch PySide6 app window
    from PySide6.QtWidgets import QApplication, QFileDialog
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEngineProfile
    from PySide6.QtCore import QUrl, Qt, QStandardPaths
    from PySide6.QtGui import QIcon

    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("TSBT Video Generator")
    qt_app.setOrganizationName("TSBT")

    # Dark title bar (Windows 10/11)
    qt_app.setStyle("Fusion")
    from PySide6.QtGui import QPalette, QColor
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(10, 14, 26))
    palette.setColor(QPalette.WindowText, QColor(224, 230, 240))
    qt_app.setPalette(palette)

    # Download handler — shows "Save As" dialog
    def handle_download(download):
        suggested = download.downloadFileName()
        default_dir = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
        path, _ = QFileDialog.getSaveFileName(
            view, "Save File", os.path.join(default_dir, suggested)
        )
        if path:
            download.setDownloadFileName(os.path.basename(path))
            download.setDownloadDirectory(os.path.dirname(path))
            download.accept()
        else:
            download.cancel()

    # Create web view
    view = QWebEngineView()
    view.setWindowTitle("TSBT Video Generator")
    view.resize(1400, 900)
    view.setMinimumSize(800, 600)
    view.load(QUrl(APP_URL))

    # Connect download handler
    view.page().profile().downloadRequested.connect(handle_download)

    view.show()

    print("[TSBT] Desktop app launched!")

    # Run Qt event loop
    exit_code = qt_app.exec()

    # Cleanup
    stop_streamlit()
    print("[TSBT] Video Generator closed.")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
