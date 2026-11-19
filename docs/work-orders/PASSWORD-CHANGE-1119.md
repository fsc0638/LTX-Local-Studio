# PASSWORD-CHANGE-1119 — 登入後自行修改密碼

日期：2026-11-19。分支：`feat/password-change`。基底：`abd8ae0`。

## 需求與方案

登入後從頂部帳號區選「修改密碼」，輸入舊密碼、新密碼、確認新密碼；顯示／隱藏密碼、錯誤訊息與成功後重新登入提示支援繁中、英文、日文。

沿用既有 `AuthStore`、scrypt、session cookie、CSRF、同源 API client、Dialog 與 Input，不引入新套件／外部認證平台、不改 schema。既有寄信重設流程不適用免 SMTP 的 internal 模式，因此增加已登入使用者端點，而不是重做身分系統。

## 已完成

- [x] `POST /api/auth/change-password`：只接受有效使用者 session；驗證 Origin、CSRF、Cloudflare email match；全域與每帳號速率限制。
- [x] 新密碼8–128字元、兩次一致且不同於舊密碼；舊密碼錯誤回400並保留原 session。
- [x] 在同一交易更換 salted hash、撤銷該帳號所有 session 及 email token；清除目前 cookie，不自動登入、不改其他帳號或素材。
- [x] 換密碼與登入 session 建立以帳號列鎖序列化；等鎖後重查 session，防止並發變更使用失效登入。
- [x] 前端成功後清除表單密碼／記憶體 CSRF、只向其他分頁通知 session change，不將密碼寫入 localStorage。
- [x] internal 模式無 SMTP、未驗證信箱也可依既有登入政策改密碼，不偽造 email verification。
- [x] 帳號 HTTP／資料庫回歸34項通過（包含6項新增密碼修改測試）。
- [x] 完整 Python 回歸465項執行結束：458通過、7跳過、0失敗；用時292.547秒，exit 0。
- [x] Node 測試111項通過（包含2項新增 API client 測試）。
- [x] TypeScript no-emit、3個前端異動檔案 oxlint、`npm run build`（含 prebuild）通過。
- [x] `bash tests/test_git_sync.sh`：8個安全同步情境通過，僅使用拋棄式 origin，不啟停正式服務。

## 驗證指令

Python 使用 LTX venv：

```bash
LTX_TEST_DATABASE_URL='postgresql:///ltx_studio_test?host=/var/run/postgresql' PYTHONPATH=tests "/home/kwayrdc/Documents/Codex/2026-08-28/new-chat-2/work/ltx-2.3/LTX-2/.venv/bin/python" -m unittest test_accounts
LTX_TEST_DATABASE_URL='postgresql:///ltx_studio_test?host=/var/run/postgresql' PYTHONPATH=tests "/home/kwayrdc/Documents/Codex/2026-08-28/new-chat-2/work/ltx-2.3/LTX-2/.venv/bin/python" -m unittest discover -s tests -p 'test_*.py'
node --test tests/*.test.mjs
node node_modules/typescript/bin/tsc --noEmit --incremental false
node node_modules/oxlint/bin/oxlint components/change-password-dialog.tsx components/account-gate.tsx lib/service-session.ts
npm run build
bash tests/test_git_sync.sh
git diff --check
```

完整 Python 回歸：`Ran 465 tests in 292.547s`、`OK (skipped=7)`。未把跳過測試計為通過。檢查日正式服務皆 active，主 checkout 仍為 `main`／`abd8ae0`。

## 未完成與需要阿寶做的事

- 未在真實瀏覽器操作對話框，未使用正式帳號改密碼；需部署後進行 UI／Cloudflare 全流程驗收。
- 主 checkout 保持 main，不改動、不合併、不推送 main；沒有重啟正式服務或修改正式帳密、Cloudflare、網路、模型權重。
- 由阿寶檢視並合併 `feat/password-change` 後，交由既有 `ltx-git-sync` 上線；本次不自行部署。
- 上線後：登入 → 頂部「修改密碼」→ 確認錯誤舊密碼不登出 → 用新密碼完成修改 → 舊裝置登入失效 → 新密碼重新登入。確認其他帳號與原素材不變。

## 回復

此分支無 schema 變動；程式回復應走新的 revert 分支及既有合併流程。已由使用者修改的密碼不應回復為舊密碼；資料庫權限／密碼管理另依明確核准處理。
