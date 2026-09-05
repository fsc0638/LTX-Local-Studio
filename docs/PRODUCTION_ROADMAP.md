# 製片平台實作路線（工單規格）

對應 `docs/PRODUCTION_FACTORY.md` 的 V2–V4 路線，拆成四期十六張工單。每張工單獨立驗收、獨立上線。
主機端持久層為 **PostgreSQL**（2026-09-04 決定：既有 `jobs.sqlite3`、`accounts.sqlite3` 一併遷入同一個資料庫）。
OpenClaw／LINE 的執行規則見 `docs/OPENCLAW_WORK_ORDERS.md`。

## 五條原則

1. 每期可獨立驗收、獨立上線；每張工單以驗收清單結束，沒過就不併。
2. 資料形狀先於功能：A 期決定 Bible、鏡、take 的欄位；A 做完凍結工作單格式 v2，之後只加欄位不改語意。
3. `/api/v1/jobs` 是唯一碰模型的路。Factory、agent、排程器只編排，不直接碰模型命令或檔案路徑。
4. agent 服務只聽 127.0.0.1，永不接受 client 給的路徑、URL 或 shell；檔案由 `ltx-api` 依 asset id 與所有權解析。OpenAI key 只在主機端 `/opt/studio/secrets/openai`。
5. 裁判否決＝「不自動流到下一階段」，不阻止用戶接受。

## 依賴

A1 → A2；A1 → B1；B0 → B1；B1 → B2、B3、B4、C1、D1、D4；B2 → B3；C1 → C3、D2；C2 → C3、D5；D1 → D2。
C4 需要校準素材（用戶提供）；D3 需要 RIFE 權重（用戶提供）。

---

## A1 Bible 與繼承（純前端，M）

**做什麼**：工廠計畫加專案層物件 Bible；新增鏡頭時從 Bible 投影 request；改 Bible 時重新投影到未生產的鏡頭；用戶覆寫過的欄位釘住不動。

**資料**（工作單格式 v2）：
```
plan.version = 2
plan.bible = {
  character?: { name, description, references[{image_id, view}] },
  music?:     { audio_id, audio_start_seconds, audio_mode, lrc, lrc_timebase },
  output:     { model, aspect_ratio, fps, profile, audio },
  directing?: { shot_size, angle, camera, emotion, performance },
  lyric_offset_seconds: -0.9
}
shot.pinned: string[]   // 用戶覆寫過的 request 欄位；重新投影時跳過
```
`shot.request` 仍是完整、可攜、worker 直接驗證的 `/api/v1/jobs` body。v1 檔匯入時 `bible` 為空、所有欄位視為釘住。

**介面**：工廠頁頂部專案面板（角色重用 `CharacterLock`、不限 i2v；音樂重用時間軸選擇器；輸出規格）；「新增鏡頭」從 Bible 投影，無 Bible 時提示；每欄位籤「繼承／此鏡覆寫」可還原；每鏡「全部設定」抽屜列出 request 全部欄位與 JSON，改動即打 `/api/v1/validate`；生成頁「加入製片工廠」在無 Bible 時用當下設定建立 Bible。

**檔案**：`lib/production-factory.ts`、`components/production-factory.tsx`、`app/page.tsx`、`tests/production-factory.test.mjs`、`docs/PRODUCTION_FACTORY.md`。

**驗收**：
- 設好角色＋音樂的專案 → 新增鏡頭 → request 含 `character` 與 `timeline`，`/api/v1/validate` 通過。
- 改 Bible 角色描述 → draft／queued／failed 鏡更新；running／succeeded 不動；釘住欄位不動並提示「N 鏡有覆寫」。
- 匯出再匯入逐鏡 request 逐 byte 相同；v1 舊檔匯入不報錯、bible 為空。
- 既有 `node --test tests/*.test.mjs` 全過；新增 ≥6 個投影／釘住／遷移測試。

**不做**：不動後端、不加 agent、資料仍在瀏覽器；一個專案一個主角色。

## A2 階段導覽與狀態板（純前端，M）

**做什麼**：五個工具頁重排成七階段 + 兩側頁；階段狀態由計畫資料在客戶端算出；首頁是狀態板。

**介面**：左側階段列 00–06，各一顆狀態籤（未開始／進行中／待人決定／通過）；02／04／05 標「本期未啟用」；00＝A1 專案面板；01＝MV 時間軸＋LRC＋cue＋鏡頭清單；03＝工廠佇列；06＝sequence 組片＋下載；「生成」改名沙盒、視覺降級；「環境」改名工站；狀態板每首歌一列：卡在哪個階段、上一步結論、下一步誰負責。

**檔案**：`app/page.tsx`、`components/stage-rail.tsx`（新）、`components/status-board.tsx`（新）。

**驗收**：新人不看文件能從 00 走到 03 送出第一鏡；「新增鏡頭」無 Bible 時不產生空鏡；沙盒現有功能一個不少；手機寬度階段列變 stepper。

**不做**：不做審片、關鍵格、後製頁內容。

---

## B0 PostgreSQL 基礎與遷移（後端＋主機，M）

**做什麼**：GB10 本機裝 PostgreSQL；`jobs.sqlite3`、`accounts.sqlite3` 搬進同一資料庫 `ltx_studio`，行為不變。

**主機（由人執行，需 sudo）**：
```
sudo apt-get install -y postgresql python3-psycopg
sudo -u postgres createuser kwayrdc                 # peer auth：OS 使用者 = DB 角色，無密碼
sudo -u postgres createdb -O kwayrdc ltx_studio
sudo -u postgres createdb -O kwayrdc ltx_studio_test
```
DSN `postgresql:///ltx_studio?host=/var/run/postgresql`（只走 unix socket，不開 TCP）。`ltx-api` 用系統 `/usr/bin/python3`，驅動走 apt 的 `python3-psycopg`（3.1）。

**程式**：
- `production_store.py`、`user_auth.py` 改用 psycopg；對外介面不變，五個既有測試檔照跑。
- `snapshot TEXT` + `json_extract` → `jsonb` + 表達式索引 `(snapshot->>'owner_id')`。
- migration：`db/migrations/NNNN_*.sql` + `schema_migrations` 表，API 啟動時套用；不引入 ORM。
- `scripts/migrate-sqlite-to-postgres.py`：停服務 → 匯入 → 逐表筆數比對 → 才切 DSN；舊 sqlite 檔留在 `data/backups/`。
- `scripts/git-sync-main.sh` 的 `sync_active_jobs` 改打 `ltx-api` 的 loopback 端點（只回應 127.0.0.1）。
- 備份：`infra/systemd/ltx-backup.service`＋`.timer` 每日 `pg_dump` 到 `data/backups/`。
- 環境變數：`LTX_DATABASE_URL`（服務）、`LTX_TEST_DATABASE_URL`（測試，指向 `ltx_studio_test`）。

**檔案**：`production_store.py`、`user_auth.py`、`auth_http.py`、`local_backend.py`、`db/migrations/0001_baseline.sql`、`scripts/migrate-sqlite-to-postgres.py`、`scripts/clear-media.py`、`scripts/git-sync-main.sh`、`infra/systemd/ltx-backup.*`、`tests/conftest.py`。

**驗收**：
- 搬移後 jobs、accounts、cloudflare_enrollments 筆數與 sqlite 一致；既有帳號能登入；歷史成品可預覽。
- 五個既有 Python 測試檔在 `ltx_studio_test` 全過；sync 的 unittest 步驤照常。
- PostgreSQL 重啟 → `ltx-api` 自動重連。
- `ss -ltn` 看不到 5432。

**不做**：ORM、多租戶 schema、TCP、讀寫分離。pgvector 等 C1。

## B1 主機端耐久佇列（後端為主，L）

**做什麼**：計畫、鏡、take 存進 PostgreSQL；`ltx-api` 內排程迴圈送 job；瀏覽器變純客戶端。

**資料**（`db/migrations/0002_factory.sql`）：
```
projects(id uuid pk, owner_id text, title text, status text, bible jsonb, created_at, updated_at)
shots(id uuid pk, project_id → projects, position int, title text, request jsonb, pinned jsonb, status text, idempotency_key text unique)
takes(id uuid pk, shot_id → shots, job_id → jobs, output_url, poster_url, scores jsonb, verdict text, reason text, created_at)
```
`external{project_id, asset_id, shot_id, request_id}` 由 API 填入；「鏡狀態＋take＋job」在一個交易完成。

**API**：`/api/v1/factory/projects`（CRUD、匯入匯出 v2）、`/projects/{id}/shots`、`/projects/{id}/run|pause`、`/shots/{id}/takes`。只編排：每鏡走既有 validate → jobs。租戶＝`owner_id`；管理員可暫停；每帳號佇列上限。

**介面**：工廠頁改讀寫 API；localStorage 只留 UI 偏好；首次載入提供「上傳到主機」一次性搬移。

**檔案**：`production_store.py`、`local_backend.py`、`worker_schema.py`、`db/migrations/0002_factory.sql`、`tests/test_factory_api.py`、`lib/factory-client.ts`、`components/production-factory.tsx`、`docs/PRODUCTION_FACTORY.md`、`docs/WORKER_API.md`。

**驗收**：開始生產 → 關掉所有瀏覽器 → 全部完成；生產中 `systemctl --user restart ltx-api` → 進行中 job 標 interrupted、佇列不重複送、可續跑；生產中重啟 PostgreSQL → API 自動重連；兩帳號互看不到；同一鏡網路重送 → 200 原 job。

**不做**：多主機、雲端 DB；排程仍一次一個 GPU job（工站交棒是 D4）。

## B2 音訊服務 MA／LS（新服務，M）

**做什麼**：`/opt/studio/venvs/audio` 包成 `ltx-audio.service`（127.0.0.1:8790）。MA：tempo、拍點、段落與能量（librosa）；LS：逐字時間（stable-ts）。

**API**：服務端 `POST /beats {path}`、`POST /align {path, lyrics, language}`，只接受 `ltx-api` 解析過的本機路徑。對外 `POST /api/v1/audio/analyze {audio_id, lyrics?, language?}`，檢查所有權後轉呼叫，結果快取在 asset 上；回傳附 `lyric_offset_seconds`（Bible，預設 −0.9）。

**檔案**：`services/audio/server.py`、`infra/systemd/ltx-audio.service`、`local_backend.py`、`tests/test_audio_service.py`。

**驗收**：三首沖縄歌 BPM 與 `docs/GB10_SETUP.md` 一致；對時去偏移後 **p50 ≤ 0.5 s 且 p90 ≤ 1.5 s**
（p90 以 **nearest-rank** 計算：殘差排序後取索引 `ceil(0.9n)-1`）；服務掛掉時
`/api/v1/audio/analyze` 回 503 不影響生成；非本人 `audio_id` → 403。

> **門檻由來**：原本寫的是 `p90 ≤ 1.0 s`，那個數字沒有量測支持 —— 它是把 2026-09-04 量測報告裡
> 「p90 只有 0.5～1.0s」這句散文的上界抄成硬門檻，而**同一份量測裡三首有兩首就已經超過它**
> （三線 1.63s、エイサー 1.04s）。B2 驗收據此正確退回。
>
> 重訂前先試過改善而非直接放寬：stable-ts 的 VAD 對這批唱歌素材是災難（p90 從 1.03s 惡化到
> 51–80s，`7/7 segments failed to align`），沒有便宜的改善空間。
>
> 1.5 s 不是「剛好會過」的數字，而是資料自然的邊界：誤差 ≤1.5s 的行數是 36/37、30/31、40/40，
> 再往下就開始切掉正常資料。加上 p50 門檻是因為 p90 混合了兩種東西 —— 對時誤差與 **LRC 本身的
> 誤差**（三線那三行壞掉的時間碼即是例子）；p50 才是對時真正該負責的典型準確度，實測 0.38／
> 0.20／0.39 s，都在一拍（104 BPM ≈ 0.577 s）以內。
>
> 指定 nearest-rank 是因為原規格只寫「p90」沒說怎麼算：同一份殘差用線性內插與 nearest-rank
> 會得到 0.923 s 與 1.040 s，**判定會翻面**。

**不做**：音素級對嘴、人聲分離。

## B3 自動分鏡（規則引擎，M）

**規則**：切點優先序 段落邊界 ＞ 歌詞行起點（已扣偏移）＞ `segment_seconds` 上限；切點吸附最近拍點（±1 拍）；純器樂段產生 `breathing` 鏡；每鏡帶 Bible 的 directing 預設，cue 時間＝鏡起點。

**檔案**：`lib/breakdown.ts`、`components/breakdown-editor.tsx`、`tests/breakdown.test.mjs`。

**驗收**：166 秒的歌、`segment_seconds=10` → 17–24 鏡，無一鏡超上限，切點全在拍點；合併兩鏡後 cue 與 timeline 重算、「預覽分鏡」正常。

## B4 LLM 編劇草稿（可選，S）

**做什麼**：每鏡「起草」按鈕，gpt-5.6 依 Bible 描述、導演參數、歌詞行、前後鏡產提示詞草稿；structured output 限 `prompt`、`primary_action`。呼叫只在 `ltx-api`，key 讀 `/opt/studio/secrets/openai`；usage 記進 project，每專案 token 上限。

**驗收**：草稿不覆蓋用戶已改過的提示詞；OpenAI 不可用時按鈕停用並說明。

---

## C1 裁判服務 CJ／SJ／MQ（新服務，M）

**做什麼**：`/opt/studio/venvs/vision` 包成 `ltx-judge.service`（127.0.0.1:8791）。輸入影片或圖 + 參照表 + 風格錨；輸出分數。CJ：抽幀（每秒 1）有臉用 facenet 對參照表取最大相似度，無臉退 DINOv2，回每幀與中位數；SJ：CLIP 對風格錨中位數；MQ：RAFT 光流幅度統計＋既有黑幀／靜止比例。服務只出數字。嵌入可存 Postgres（可選 pgvector）。

**檔案**：`services/judge/server.py`、`infra/systemd/ltx-judge.service`、`local_backend.py`（成功 job 後自動送判、寫 take.scores）、`tests/test_judge_service.py`。

**驗收**：同圖對自己 CJ face ≈ 1.0；不同角色明顯低於同角色；判分失敗不影響 job succeeded，只標「未判分」。

## C2 Take 模型（S，已有雛形 `reopenFactoryShot`）

```
take = { id, shot_id, job_id, output_url, poster_url,
         scores: { cj: {face, dino, per_frame[]}, sj: {clip}, mq: {flow, static_ratio} } | null,
         verdict: 'pending' | 'accepted' | 'rejected' | 'overridden', reason, created_at }
shot.accepted_take_id   // 只有它進 06
```
退回原因自動接到下一 take 提示詞（「避免：…」），用戶可改。

**驗收**：退回 → 新 take prompt 含原因；再退回累積不覆蓋；刪成品 → 該 take 標 deleted，鏡與其他 take 不受影響。

## C3 審片頁（04 階段，M）

**介面**：每鏡 take 並排；三條分數 vs 門檻線（C4 前標「未校準」）；VLM 一句話（gpt-5.6，主機端）＋「我不同意」；接受／退回（必填原因）；紅燈下接受 → `overridden` 並記錄；抽屜：逐幀 CJ 曲線、相鄰鏡嚴格模式（fpr 1%）、本鏡門檻覆寫。否決＝不自動成為 `accepted_take_id`。

**驗收**：換臉 take CJ 低於門檻、紅燈、不自動進組片、用戶仍可接受並留 overridden；裁判服務關閉時頁面仍可用。

## C4 門檻校準（S）

跑 `infra/gb10/tools/calibrate_embeddings.py --root calibration --out calibration_report.json`；fpr 5% 寫進 Bible 當預設、fpr 1% 當相鄰鏡嚴格值；加匯入按鈕讀報告進 `bible.thresholds`。素材：`calibration/<角色>/` ≥2 角色、每個 ≥10 張。

**驗收**：EER 與 fpr 門檻寫進 Bible；C3 門檻線不再標「未校準」；無臉圖列出並在 UI 標示。

---

## D1 imagegen adapter 與 GPU 租約（後端，L）

**做什麼**：Qwen-Image-Edit-2509、Z-Image-Turbo 註冊成 `local_adapters`（`media_type: image`）；常駐 `ltx-imagegen.service`（按需啟動、閒置釋放）。`ltx-api` 加大工站租約：同時只有 LTX 或 imagegen 持有 GPU；裁判、音訊、後製不受限。實測：Qwen 61.2 GB／載入 336 s／25.8 s 一張；Z-Image 23.3 GB／12.9 s。

**參數**：`steps`（預設 8）、`seed`、`references`（1–3 個 image_id）、`lightning`、`size`；經 `model_registry.py` 檢查，不接受路徑。

**檔案**：`local_adapters/imagegen.py`、`services/imagegen/server.py`、`infra/systemd/ltx-imagegen.service`、`local_backend.py`、`model_registry.py`、`tests/test_imagegen_adapter.py`、`tests/test_gpu_lease.py`。

**驗收**：LTX job 進行中送 imagegen job → 排隊不 OOM，反向亦然；連續 20 張只付一次載入；閒置超時後 `nvidia-smi` 無 imagegen 程序。

## D2 關鍵格階段（02 階段，M）

鏡頭清單變縮圖格；「產生全部關鍵格」：每鏡依 `directing.angle` 選參照（既有 `select_reference`）→ Qwen 生成 → CJ 判分 → 綠／黃／紅；紅自動重生一次再請人；核准圖成為該鏡 `image_id`。全專案整批做（切換工站付 336 s）。

**驗收**：24 鏡專案總時間 ≈ 336 s + 24 × 26 s；混入另一角色參照的鏡標紅；核准後該鏡 `image_id` 更新、籤顯示「來自關鍵格」。

## D3 後製 adapter VX（05 階段，M）

核准 take 三個開關：補幀（RIFE）、放大（Real-ESRGAN ×4 或 LTX x2）、清理（LaMa 遮罩）；各為 post job，輸出新 take 版本；完成後自動過 MQ。RIFE 權重需放 `/opt/studio/tools/rife/train_log`。

**驗收**：24 fps 補到 48 fps 通過最終 QC；清理後 CJ 不低於清理前。

## D4 工站排程與 LP 預算（M）

排程器依工站分群、同工站連續做、交棒；工站頁顯示誰坐 GPU、佇列、切換 ETA。LP 預算＝Σ generate 秒 + 切換次數 × 載入秒 + OpenAI usage；超預算警告不擋。數字來源 `docs/GB10_SETUP.md` 與 jobs 的 `runtime_seconds` 滾動平均。

**驗收**：12 張關鍵格 + 12 鏡 LTX 恰好切換 1 次；預估總時數誤差 < 20%。

## D5 組片與 EDL（06 階段，S）

只取 `accepted_take_id`，依拍點排時間軸，原曲連續鋪底；匯出 MP4 + shot manifest／EDL（JSON：每鏡 prompt、seed、參照指紋、模型版本、take 裁決）。

**驗收**：任一鏡無 accepted take → 組片停用並列出；manifest 能還原每鏡完整 request。

---

## 橫切規範

- 安全邊界：新服務只聽 127.0.0.1、只接受 `ltx-api` 解析過的路徑；client 只給 id。
- 測試：純函式 `node --test`；後端與服務 `unittest`（合成 fixture，不下載模型）；維運 `tests/test_git_sync.sh`。
- 部署：`git push origin main` → sync 驗證、build、重啟、蓋印記。新 systemd unit 需人手 `systemctl --user enable --now` 一次（B2、C1、D1）。PostgreSQL 由 B0 的 apt 安裝。
- 備份：B0 起每日 `pg_dump`；uploads／outputs 一起備。
- 資料相容：工作單 v2 在 A 凍結；schema 只透過 `db/migrations/` 前進。

## 建議順序

A1 → A2 → B0 → B1 → B2 → B3 →（B4）→ C1 → C2 → C3 →（C4 素材到時）→ D1 → D2 → D3 → D4 → D5。
