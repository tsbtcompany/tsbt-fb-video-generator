"""
TSBT Video Generator — Desktop Shortcut Creator
바탕화면에 바로가기(.lnk)를 생성합니다.
"""

import os
import sys

try:
    from win32com.client import Dispatch
except ImportError:
    print("pywin32 필요: py -m pip install pywin32")
    # Fallback: .bat 파일 생성
    desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
    bat_path = os.path.join(desktop, "TSBT Video Generator.bat")
    launcher = os.path.join(os.path.dirname(os.path.abspath(__file__)), "desktop_launcher.py")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(f'@echo off\n')
        f.write(f'start "" /min py "{launcher}"\n')
    print(f"[OK] BAT shortcut created: {bat_path}")
    sys.exit(0)

desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
launcher = os.path.join(os.path.dirname(os.path.abspath(__file__)), "desktop_launcher.py")
lnk_path = os.path.join(desktop, "TSBT Video Generator.lnk")

shell = Dispatch("WScript.Shell")
shortcut = shell.CreateShortCut(lnk_path)
shortcut.Targetpath = sys.executable
shortcut.Arguments = f'"{launcher}"'
shortcut.WorkingDirectory = os.path.dirname(launcher)
shortcut.Description = "TSBT Video Generator Desktop App"
shortcut.save()

print(f"✅ 바탕화면 바로가기 생성 완료: {lnk_path}")
