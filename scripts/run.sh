#!/bin/bash
# Wrapper script for crontab — 負責準備執行環境，再呼叫 generate.py
#
# crontab 環境的 PATH 極度精簡（通常只有 /usr/bin:/bin），
# 不會 source ~/.bashrc、nvm.sh 等設定，導致 wrangler、claude 等指令找不到。
# 這支腳本在源頭把環境補齊，Python 程式碼就不需要處理路徑問題。

set -euo pipefail

# 載入 nvm（wrangler 裝在 nvm 管理的 node 裡）
export NVM_DIR="$HOME/.nvm"
source "$NVM_DIR/nvm.sh"

# claude CLI 安裝在 ~/.local/bin
export PATH="$HOME/.local/bin:$PATH"

# 切到專案根目錄
cd "$(dirname "$0")/.."

# 載入環境變數（Discord webhook 等）
set -a
source .env
set +a

# 執行主腳本
uv run python scripts/generate.py >> /tmp/dev-diary-cron.log 2>&1
