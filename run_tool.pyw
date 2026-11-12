import os
import sys
import time
import subprocess
import urllib.request
import webbrowser

PORT = 8501
URL = f"http://localhost:{PORT}"
HEALTH_URL = f"{URL}/_stcore/health"
PROJECT_DIR = r"C:\Projects\video-content-checker"


def is_running():
    # Health endpoint chỉ Streamlit mới có; tránh nhầm với app khác chiếm cổng.
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=1) as resp:
            return resp.read().decode().strip() == "ok"
    except Exception:
        return False


def main():
    # 1. Nếu chưa chạy, khởi động Streamlit ngầm bằng pythonw hoàn toàn độc lập
    if not is_running():
        DETACHED_PROCESS = 0x00000008
        CREATE_NO_WINDOW = 0x08000000
        flags = DETACHED_PROCESS | CREATE_NO_WINDOW
        
        pythonw_exe = sys.executable if "pythonw.exe" in sys.executable.lower() else sys.executable.replace("python.exe", "pythonw.exe")
        
        cmd = [
            pythonw_exe,
            "-m", "streamlit", "run", "app.py",
            "--server.headless", "true",
            "--server.port", str(PORT),
            "--server.address", "0.0.0.0"
        ]
        
        subprocess.Popen(
            cmd,
            cwd=PROJECT_DIR,
            creationflags=flags,
            close_fds=True
        )
        
        # Chờ tối đa 8 giây cho server khởi động xong
        for _ in range(16):
            time.sleep(0.5)
            if is_running():
                break

    # 2. Mở trình duyệt mặc định vào URL localhost
    webbrowser.open(URL)


if __name__ == "__main__":
    main()
