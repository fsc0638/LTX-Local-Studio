# 待素材／待實測清單

2026-09-09：十六張工單（A1–A2、B0–B4、C1–C4、D1–D5）全部合併上線。依建置原則
（`docs/PRODUCTION_ROADMAP.md`「架構先建、素材後補」），結構都做完並以 fixture／mock 驗過；
下面是需要**真素材、真模型時間、或登入看畫面**才能補跑的項目，從各工單檔彙整。做完一項就在這裡劃掉並註明日期。

## A. 只要一段沒在拍片的 GPU 時段（不需要新素材）

| 項目 | 怎麼跑 | 預期 | 來源 |
|---|---|---|---|
| Z-Image 真模型冒煙 | 生成頁或 02 關鍵格送一張 `z-image-turbo`（23 GB、~13 s） | PNG 過 QC；`/health.loads`=1 | D1（09-08 曾送出，撞到自鎖已修；修後尚未再跑） |
| Qwen edit 真模型冒煙 | 送一張 `qwen-image-edit-2509`（61 GB、載入 ~6 min、~26 s／張） | PNG 過 QC；`/health.loads`=1 | D1 |
| D1 驗收三條 | LTX job 進行中送 imagegen → 409 `worker_busy`；反向亦然；連續 20 張 `loads` 仍 1；閒置 10 分鐘後 `/health.loaded` 空 | 對應規格 | D1 |
| 關鍵格整批 | 有參照圖的專案 → 02「產生全部關鍵格」 | 24 鏡 ≈ 336 s＋24×26 s；`loads` 只加 1 | D2 |
| 換臉紅燈 | 上一列混入另一角色的參照 | 該鏡紅燈、不自動進 03、核准後 `image_id` 更新且籤「來自關鍵格」 | D2 |
| 後製放大／清理 | 05 對核准 take 放大 ×2、塗遮罩清理 | 新 take 過 QC；清理後 CJ 不低於清理前（要有臉的素材） | D3 |
| LP 估算誤差 | 跑過幾個真 job 累積 `runtime_seconds` 後，看工站頁預估 vs 實花 | 誤差 < 20% | D4 |
| 組片 | 一個所有鏡都有採用 take 的真專案 → 06 組片 → 下載 MP4 與 manifest → 匯回 00 | 成品播放正常；匯入後每鏡 request 一致 | D5 |

先查 `GET /api/internal/active-jobs` 的 `ltx` 為 0 再做真模型項目。

## B. 需要素材（阿寶提供）

| 項目 | 需要什麼 | 怎麼跑 | 預期 | 來源 |
|---|---|---|---|---|
| 門檻校準 | `calibration/<角色>/` ≥2 角色、每個 ≥10 張，放主 checkout（已 gitignore） | `HF_HOME=/opt/studio/models/hf TORCH_HOME=/opt/studio/models/torch /opt/studio/venvs/vision/bin/python infra/gb10/tools/calibrate_embeddings.py --root "/home/kwayrdc/LTX Local Studio/calibration" --out calibration_report.json`，再到 00 匯入 | 04 的「未校準」banner 消失；臉太少則顯示「臉部線仍為暫定」 | C4 |
| 補幀 | RIFE 權重解壓到 `/opt/studio/tools/rife/train_log/`（作者雲端連結，見該目錄 README） | 服務 `/health.rife_available` 變 true；05 按補幀 | 24 fps → 48 fps 過 QC | D3 |

## C. 登入後看畫面（各頁尚未由人確認）

02 關鍵格、05 後製、06 組片、工站頁（04 審片已於 C3 合併後可看）。要看的重點寫在各工單檔的待實測表。

## 已補跑

（做完一項搬到這裡，附日期與結果。）
