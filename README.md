# Dev Diary

自動化的 Claude Code 對話摘要系統。每天自動從 Claude Code session 資料產生摘要，
透過 Cloudflare Pages 呈現。

## 功能

- 每日摘要：自動從 Claude Code 對話產生當日工作紀錄
- 週報：每週六自動匯總整週工作內容
- 雙版本：公開版（僅摘要）+ 完整版（含技術細節，需登入）
- 補跑機制：電腦關機期間遺漏的日期會自動補產

## 架構

- **前端**：Cloudflare Pages（靜態 HTML/CSS/JS）
- **API**：Cloudflare Pages Functions（Google Token 驗證 + KV 讀取）
- **資料儲存**：Cloudflare KV（完整版）、靜態 JSON（公開版）
- **摘要產生**：本機 Python 腳本 + Claude CLI
- **排程**：WSL cron（每天 23:59）

## 技術棧

- Python（uv）
- Cloudflare Pages / Functions / KV
- Google Identity Services（ID Token 驗證）
- jose（JWT 驗證）
