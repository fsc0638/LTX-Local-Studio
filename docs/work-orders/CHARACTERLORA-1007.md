# CHARACTERLORA-1007 · 人物 LoRA Registry 與 UI

## 目標

正式 Studio 以安全 registry ID 選擇人物／服裝 LoRA，Factory Bible 可繼承，API 主機端解析私有權重與 trigger token，生成 provenance 可追溯。

## 已完成

- [x] 建立 host-side Character LoRA Registry，驗證核准狀態、kind、模型／模式、強度範圍、SHA-256 與安全路徑。
- [x] 新增 `GET /api/v1/character-loras`，公開 catalog 不回傳權重路徑或 trigger token。
- [x] `/api/v1/jobs` 支援 `identity_lora` 與 `wardrobe_lora` 的 `{id,strength}`，server-side 注入 trigger。
- [x] LTX 2.5 launcher 以 repeatable `--lora` 載入人物與服裝權重。
- [x] Job provenance 記錄 LoRA ID、版本、strength 與 weight SHA-256。
- [x] 沙盒與 Factory Bible 新增 Identity／Wardrobe selector 與強度滑桿。
- [x] Bible 投影、匯出／匯入與未生成鏡頭重新投影保留 LoRA 欄位。
- [x] 完整回歸：Python 456 tests PASS（7 skipped）、Node 108/108 PASS、TypeScript PASS、production build PASS、`git diff --check` PASS。

## 未完成

- [ ] 使用阿寶提供的正式角色 LoRA 權重建立第一筆 approved registry entry。
- [ ] 真 GPU 疊加 Distilled＋Identity（及 Wardrobe）LoRA smoke 與品質 A/B。
- [ ] 合併 main 後部署正式站與重啟 API（需另行核准）。

## 本工單異動

- Registry／API：`character_lora_registry.py`、`local_backend.py`、`worker_contract.py`、`worker_schema.py`
- 推論：`scripts/run-ltx-2.5-fast.sh`
- UI／Factory：`app/page.tsx`、`components/production-factory.tsx`、`lib/production-factory.ts`
- 文件／測試：`docs/CHARACTER_LORA_REGISTRY.md`、`docs/WORKER_API.md`、`tests/test_character_lora_registry.py`、`tests/test_ltx25_fast.py`、`tests/production-factory.test.mjs`

## 驗證結果

- `LTX_TEST_DATABASE_URL='postgresql:///ltx_studio_test?host=/var/run/postgresql' .../.venv/bin/python -m unittest discover -s tests -p 'test_*.py'`：456 PASS，7 skipped。
- `node --test tests/*.test.mjs`：108 PASS。
- `npx --no-install tsc --noEmit -p tsconfig.json`：PASS。
- `npm run build`：PASS。
- `git diff --check`：PASS。

## 待素材測試

- 正式 `.safetensors`、metadata、保留驗證圖／影片與人工驗收表。
- 驗收無 LoRA、Identity、Identity＋reference、Identity＋reference＋Pose/A2V、Identity＋Wardrobe；固定其他參數。

## 需要阿寶做的事

- 程式分支通過後由阿寶 fast-forward 合併；正式服務重啟另行核准。
- 提供角色資產包所在 GB10 絕對路徑，才能開始訓練與建立第一筆 registry entry。
