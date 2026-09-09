# 待素材／待實測清單

2026-09-09：十六張工單（A1–A2、B0–B4、C1–C4、D1–D5）全部合併上線。依建置原則
（`docs/PRODUCTION_ROADMAP.md`「架構先建、素材後補」），結構都做完並以 fixture／mock 驗過；
下面是需要**真素材、真模型時間、或登入看畫面**才能補跑的項目，從各工單檔彙整。做完一項就在這裡劃掉並註明日期。

## A. 只要一段沒在拍片的 GPU 時段（不需要新素材）

| 項目 | 怎麼跑 | 預期 | 來源 |
|---|---|---|---|

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

| 項目 | 日期 | 結果 | 來源 |
|---|---|---|---|
| Z-Image 真模型冒煙 | 09-09 | PNG 過 QC；暖載 ~45 s、生成 13.3 s；`loads` 1 | D1 |
| Qwen edit 真模型冒煙 | 09-09 | PNG 過 QC；暖載 120 s（估 336 s 是冷載）、生成 34.8 s；切換時 Z-Image 卸載；RAM 86/121 G | D1 |
| D1 驗收三條 | 09-09 | 409 `worker_busy` 雙向 ✓；連續 20 張 `loads` 8→8 ✓；閒置卸載 journal「idle 10.2 min」✓；LTX 驅逐 imagegen 0.49 s | D1 |
| 關鍵格整批 | 09-09 | 3 鏡 432 s（估 414 s，+4%）；`loads` 11→12（Qwen 載一次）；兩鏡綠（CJ 0.873／0.812） | D2 |
| 換臉紅燈 | 09-09 | 第三鏡兩種子皆紅（0.577→0.555）→ `red_retry` 後停等人；退回附理由改走 t2v；核准後 `request.image_id` 換成關鍵格資產、`pinned` 含 image_id、`mode=i2v` | D2 |
| LP 估算誤差 | 09-09 | 估 321.6 s vs 實花 GPU 270.1 s（3 鏡 101–113 s）＝ −16%，< 20% | D4 |
| 組片 | 09-09 | 三鏡採用 take → 06 組片 2.5 s → `ltx-cut-…96e1b3b8f8e4.mp4` 1024×576、147 幀、6.125 s、AAC；manifest 匯回新專案後 3 鏡 `request` 逐一一致、pinned 保留 | D5 |
| 後製放大／清理 | 09-09 | OP-POST02 重啟 ltx-post 後：放大 ×2 → 2048×1152、49 幀、QC 通過、191 s；塗遮罩清理（角落 200×120）→ 15 s、QC 通過、CJ 0.7149 vs 清理前 0.7136（未降）。重送同 take 同參數曾重放先前失敗的 job、且重放成功 job 會多記一個 take —— 已修（5e43a05）：失敗的嘗試換鍵重跑，成功的重放不再多記 take | D3 |

補跑時抓到並已修的問題（都有回歸測試、都已上線）：
- 服務擁有者的專案產關鍵格時被當成帳號查資產 → 「Reference asset is not available」（275b890／96b9e4c）。
- 核准關鍵格後 `request` 多了 `keyframe_id`，工人契約拒收；且帶 `image_id` 必須 `mode=i2v`（eb66872）。
- 後製 `encode()` 的 `-shortest` 讓 49 幀被 2.01 s 音軌截成 48 幀（5cc2350）。
- 關鍵格鏡走圖片幾何 1024×576、純 t2v 鏡落到工人預設 768×512，組片拒絕混尺寸 → 沒指定尺寸的鏡改跟聖經比例（e1bf23d）。
