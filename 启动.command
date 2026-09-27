#!/bin/zsh
cd "$(dirname "$0")"
if [[ ! -f .venv/bin/python || ! -d frontend/node_modules ]]; then
  ./setup.sh || exit 1
fi
python3 dev.py
