"""Single Windows entry point. Open the browser only after server readiness."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:8514'


def ready():
    try:
        with urllib.request.urlopen(URL + '/_stcore/health', timeout=1) as response:
            return response.status == 200 and response.read(100).strip() == b'ok'
    except (OSError, ValueError):
        return False


def open_browser():
    if not webbrowser.open(URL):
        print('Open this address in your browser: ' + URL)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', nargs='?', default='app',
                        choices=['app', 'verify', 'test', 'setup', 'demo', 'api'])
    action = parser.parse_args().action
    os.chdir(ROOT)
    if not (ROOT / '.env').exists():
        shutil.copyfile(ROOT / '.env.example', ROOT / '.env')
    commands = {
        'verify': ['legal_studio.doctor', '--live'],
        'test': ['pytest', '-q'],
        'setup': ['pip', 'install', '-r', 'requirements.txt'],
        'api': ['uvicorn', 'legal_studio.api:app', '--host', '127.0.0.1', '--port', '8800'],
    }
    if action in commands:
        return subprocess.call([sys.executable, '-m', *commands[action]])
    if ready():
        print('An application is already running. Opening its browser page.')
        open_browser()
        return 0
    env = os.environ.copy()
    if action == 'demo':
        env.update(DEMO_MODE='1', ENABLE_LLM='0')
    process = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', str(ROOT / 'ui.py'),
                                '--server.address', '127.0.0.1', '--server.port', '8514',
                                '--server.headless', 'true'], env=env)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return process.returncode or 1
            if ready():
                open_browser()
                print('Keep this window open while using the app. Ctrl+C stops it.')
                return process.wait()
            time.sleep(0.3)
        print('The application did not become ready within 60 seconds.')
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    raise SystemExit(main())
