# 註冊後同步 Cloudflare Access

## 功能與邊界

這是可選功能，預設 `LTX_CF_ACCESS_ENABLED=0`。未完成 Cloudflare 授權、清單、原則及身份提供者驗收前，不啟用公開入口。

## 此主機的啟用紀錄（2026-08-30）

管理者明確同意後，已在此主機啟用 `LTX_CF_ACCESS_ENABLED=1`。未購買或升級方案，未更改 DNS、Tunnel 路由或原有管理者原則。

| 項目 | 已設定的值 |
|---|---|
| 對外入口 | `https://ltx.mikamiu.studio` |
| Account | `b47eb7d09ce109a86b1d3422d3764dee` |
| Access 應用 | `LTX Local Studio` / `f99ac9f7-6a6f-4aea-906f-0a1c939b64a9` |
| Team domain | `https://misty-scene-c01b.cloudflareaccess.com` |
| EMAIL 清單 | `ltx-registered-users` / `6d06f449-ea38-4b80-b1c5-2335e397f976` |
| 新 Allow 原則 | `Allow registered LTX users` / `89130a5f-cc60-4d11-bb72-8f70c66278c7`，僅 Include 上述清單 |
| 信箱 OTP | `LTX email verification` / `eb7b1570-7a31-4e8e-aa54-808d64457a75`，`onetimepin` |
| 保留的原則 | `Allow studio owner`，內容未變 |
| 專用帳戶 Token | `ltx-account-email-sync`，僅本帳號 `Zero Trust Write`（編輯器的 Edit） |
| Token 到期 | **2026-11-29 07:59:59 台北時間**，即 `2026-11-28T23:59:59Z` |

建立前查核本帳號僅有這一個 Access 應用。原有 Cloudflare 身份提供者保留，另新增 OTP；應用接受可用身份提供者，但仍由精確信箱 Allow 原則控制資格。沒有 Everyone 或 Bypass。

Token 僅保存在 `data/worker/cloudflare-api-token`，檔案權限 0600、父目錄 0700，已確認被 Git 忽略。此文件不保存秘密內容。**到期前須更換 Token**；失效後新註冊仍可保存於本機，但無法完成同步，讀取清單階段失敗會維持 `pending`。不要在續期時批次重建整份名單。

正式網站 3000 與開發網站 3001 已共用啟用後的 API 8787。啟用前確認 GPU 閒置，重啟後 CUDA 可用、裝置 NVIDIA GB10。帳號及設定備份：`data/backups/cloudflare-enable-20260830.H4oO7Z/`；舊網頁建置保留於 `/tmp/ltx-cf-rollout.SR33w5/previous-dist`（暫存路徑可能於系統清理後消失）。

實際驗收：兩個網站均回報同步啟用；透過 3000 註冊臨時帳號，真正追加至 Cloudflare 清單；沒有偽造 `verified_at`。移除該測試信箱後，本機登入與重複註冊不會加回。外部來源缺少 Access 身份時被 API 拒絕；未登入的正式網址回覆 302 導向 Cloudflare。只移除本次臨時帳號與清單項目，既有帳號與素材不變。

回歸測試：Cloudflare 專項 17 項通過；使用模型虛擬環境執行完整 Python 測試，84 項通過（40.307 秒）。完整測試包含 PyAV／圖片解碼依賴，不應使用缺少這些套件的系統 Python 執行。測試時明確設定 `LTX_CF_ACCESS_ENABLED=0`，以隔離的模擬 Cloudflare 與臨時資料庫驗證，避免觸及真實名單；上述實際同步驗收另行執行。前端沿用已通過建置的版本，沒有更換網站風格或部署到其他雲端平台。

**仍待信箱持有人驗收：** 真實收信 → 輸入 OTP → 使用同信箱的本機帳密登入。沒有代收信、代填驗證碼，也沒有用測試結果宣稱已完成真實收信。現有帳號不會追溯同步；新使用者先在本機受控入口完成註冊。

## 使用者流程

1. 在本機受控入口註冊姓名、帳號、8–128 字元密碼與信箱。
2. 同一筆 SQLite 交易保存帳號及首次同步紀錄，密碼只存雜湊。
3. 後端以專用 Token 呼叫 Cloudflare `PATCH /accounts/{account_id}/gateway/lists/{list_id}`，只送出 `append: [{value: email}]`。
4. 註冊結果顯示同步成功／待重試／需管理者確認，並提供前往公開網址的按鈕。
5. 使用者在 Cloudflare Access 登入頁輸入註冊信箱、要求登入碼並完成驗證，再登入本機帳號。
6. API 驗證 Access JWT 的 RS256 簽章、固定 issuer、AUD、期限與 email；只有同一信箱能配對本機帳號。驗證成功且密碼正確才更新 `verified_at`，不因加入名單就假裝已驗證信箱。

**追加名單不是寄信 API。** Cloudflare 的 OTP 在其登入頁由使用者要求；不直接代收、代填驗證碼，不使用本機 SMTP。保留 `LTX_AUTH_MODE=internal` 時，可信 loopback 入口仍可使用原本內部帳號流程，對外入口則額外強制 Access 身份。
外部尚未獲准的人不能先進到受 Access 保護的註冊頁；本次不設 Everyone／Bypass，不另開未保護的公開註冊入口。
通過外層的既有使用者也不能從外部替其他信箱註冊並自動授權；外部註冊 email 必須與已驗證 Access email 相同。

## Cloudflare 一次性設定

- 使用網域實際所屬帳號，不能沿用連到其他帳號的整合憑證。
- 建立獨立 EMAIL 清單，例如 `ltx-registered-users`。不是 WAF IP 清單。
- 建立一條 Allow 原則，Include 僅引用該 Email list，將原則掛到現有 LTX Access 應用。保留原管理者原則及整個網站、API、素材路徑的保護。
- 確認應用允許 One-time PIN 身份提供者；不能以「Include Login Method = OTP」取代信箱限制，那會放行所有有效信箱。
- 取得應用 AUD、組織 team domain、清單 ID。
- 建立限於該帳號的專用 API Token。優先選可用的細粒度 Zero Trust 清單讀寫權限；不要使用 WAF 的 Account Rule Lists，也不要重用 Tunnel/build Token。
- 2026-08-30 在這個帳號的使用者 Token 與帳戶 Token 編輯器中，均未找到細粒度 Zero Trust 清單權限，僅看到較廣的 `Zero Trust Edit`。若需用此權限，必須先取得管理者同意；它不是只允許編輯 LTX 這一份清單。
- 同步程式本身只使用固定帳號／清單的 GET 與單筆 PATCH；不修改 Access 原則、登入方式、DNS、Tunnel 或付費方案。但程式限制不等於 Token 的授權限制。

## 主機設定

先使用 `python3 scripts/save-cloudflare-token.py`，在終端隱藏輸入 Token；不要放在命令列參數、對話、Git 或瀏覽器前端。預設保存於被 Git 忽略的 `data/worker/cloudflare-api-token`，權限 0600，不覆寫既有秘密。

在忽略於 Git 的 `.env.local` 配置：

```dotenv
LTX_USER_AUTH_ENABLED=1
LTX_AUTH_MODE=internal
LTX_CF_ACCESS_ENABLED=1
LTX_CF_ACCOUNT_ID=實際帳號ID
LTX_CF_EMAIL_LIST_ID=實際EMAIL清單UUID
LTX_CF_PUBLIC_ORIGIN=https://你的公開主機名稱
LTX_CF_TEAM_DOMAIN=https://你的組織.cloudflareaccess.com
LTX_CF_AUDIENCE=應用AUD
LTX_CF_API_TOKEN_FILE=/絕對私有路徑/cloudflare-api-token
```

API 所使用的 Python 需安裝 PyJWT 與 cryptography；這台主機兩者已有安裝。啟用時會驗證配置、秘密檔案權限與依賴；缺少任一項不會偷偷跳過驗證。
API 仍只綁 `127.0.0.1:8787`。公開來源由 `LTX_CF_PUBLIC_ORIGIN` 加入同源帳號請求的精確允許名單；不使用 wildcard。
本機測試 cookie 與外部 HTTPS `__Host-` Secure cookie 分開。使用者可在兩個入口分別登入。
只有真正 loopback 連線、loopback Host／Origin、且沒有 Cloudflare／外部轉送標頭的請求才享有本機例外；不能靠偽造信箱標頭通過外部驗證。

日後換網域，更新 DNS／Tunnel／Access 目的地及 `LTX_CF_PUBLIC_ORIGIN` 即可；不要把其他專案名稱写入 API 契約。若重建 Access 應用，需同時更新 AUD。清單或帳號 ID 變更不會自動把舊帳號重新授權到新目標。

## 同步紀錄與撤權

SQLite `cloudflare_enrollments` 保存 email、user_id、同步目標、狀態、固定錯誤代碼與時間，不含 Token 或密碼。

| 狀態 | 意義 | 自動行為 |
|---|---|---|
| `pending` | 遠端写入尚未開始，例如讀取清單失敗 | API 啟動後每 30 秒檢查，恢復後再次嘗試 |
| `adding` | 已持久化即將写入的意圖 | 不再次寫入；重啟仍停在此狀態時，由管理者核對 |
| `synced` | Cloudflare 已接受追加 | 終態，不從帳號表重建名單，不因登入再次追加 |
| `review` | 写入結果不確定或遭拒絕 | 終態，由管理者在 Cloudflare 核對，不盲目重送 |

只有本功能啟用後的新註冊會建立首次同步紀錄。既有帳號不批次加入，亦不因使用者再次登入而加入。
同步採單筆追加，故不會把其他使用者已在控制台移除的項目寫回。相同信箱的首次同步紀錄會保留，不能透過刪除本機帳號再註冊來重新加入。
管理者可在 Cloudflare「可重複使用的元件 → 清單」維護成員；撤銷資格時，移除該信箱在所有 Allow 原則的資格，並撤銷其既有 Access 工作階段。只刪清單項目不等同已發出的 Access token 立即失效。
撤權會阻止後續外部存取，但不會自動取消已接受的 GPU 工作；取消工作與停用本機帳號仍是獨立操作。擁有本機管理權的人仍可使用 loopback 入口。

## 驗收項目

- 先測本機註冊 → 單筆同步 → 狀態；不能宣稱同步成功就等於真實收信完成。
- 真實收信與 OTP 僅由信箱持有人操作。通過後驗證同信箱帳密登入、Secure cookie、素材與模型 API。
- 測試錯誤簽章、issuer／AUD、過期 JWT、不同信箱、缺少外層身份及未登入全部拒絕。
- 移除測試者的允許資格並撤銷 Access token，確認不能從外部重新取得服務，且本機登入、重啟或其他人註冊不會恢復其允許资格。
- 只清理明確由驗收建立的臨時帳號與 Cloudflare 清單項目，不移除正式使用者。

參考：[OTP](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/)、[單筆追加清單 API](https://developers.cloudflare.com/api/resources/zero_trust/subresources/gateway/subresources/lists/methods/edit/)、[JWT 驗證](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/)、[撤銷工作階段](https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/)。
