#!/bin/sh
# SimpleTavern 更新脚本（Linux/macOS），由后端 /api/update/run 触发
# 用法: ./update.sh <backend_pid> <repo_root>
cd "$(dirname "$0")"
exec python3 update_runner.py "$1" "$2"
