#!/usr/bin/env python3
"""Start the independent API and frontend development servers with one command."""
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / '.venv' / 'bin' / 'python'


def main():
    if not PYTHON.exists() or not (ROOT / 'frontend/node_modules').exists():
        print('请先运行 ./setup.sh 安装依赖。', flush=True)
        return 1
    for port in (8000, 5173):
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                print(f'端口 {port} 已被占用。请先关闭已有服务，再启动。', flush=True)
                return 1
    processes = []
    def stop(*_):
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        processes.append(subprocess.Popen([str(PYTHON), '-m', 'uvicorn', 'backend.app:app', '--host', '127.0.0.1', '--port', '8000'], cwd=ROOT, start_new_session=True))
        processes.append(subprocess.Popen(['npm', 'run', 'dev'], cwd=ROOT / 'frontend', start_new_session=True))
        print('\nPython 学习工具：http://127.0.0.1:5173\nAPI 文档：http://127.0.0.1:8000/docs\n按 Ctrl+C 停止两个服务。\n', flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(0.3)
    finally:
        stop()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    return 0


if __name__ == '__main__':
    sys.exit(main())
