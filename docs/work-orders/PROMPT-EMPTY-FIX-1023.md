# PROMPT-EMPTY-FIX-1023

## 問題

沙盒的提示詞欄位在已有 Factory Bible 時，每次輸入都會立即呼叫嚴格的 `projectBible()`。
使用者全選刪除，或逐字刪到空字串時，嚴格驗證會在 React render 期間丟出例外，造成整頁載入失敗。

## 驗收

- 全選提示詞並刪除時，頁面維持可操作。
- 從最後一個字刪到空字串時，頁面維持可操作。
- 空提示詞時生成與加入製片工廠按鈕維持停用。
- 再輸入有效提示詞後，Factory Bible 投影照常套用。
- 前端單元測試、TypeScript、lint 與 production build 通過。

## 進度

### 已完成

- 新增可容納暫時空字串的草稿投影入口；有效提示詞仍走原本的嚴格驗證。
- 提示詞欄位加入既有後端契約的 4,000 字上限。
- 新增空字串、純空白與恢復有效內容的回歸測試。
- `node --test tests/*.test.mjs`：109/109 PASS。
- `npx --no-install tsc --noEmit -p tsconfig.json`：PASS。
- `npm run build`：PASS。
- port 3001 隔離開發站 HTTP smoke：200；測完已停止。

### 未完成

- 瀏覽器互動驗收：本次工作階段沒有已連線的瀏覽器實例，未宣稱目視操作通過。
- `npm run lint` 仍被既存、與本次差異無關的全專案規則錯誤擋住（UI 元件 a11y、既有 React Compiler suppression 等）；本次新增單元測試、TypeScript 與 build 均通過。

### 需要阿寶做的事

- 合併部署後，在提示詞欄位各驗一次「全選後刪除」與「逐字刪到空字串」。
