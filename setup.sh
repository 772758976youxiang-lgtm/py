#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
npm ci --prefix frontend
printf '\n安装完成。运行 python3 dev.py，或双击「启动.command」。\n'
