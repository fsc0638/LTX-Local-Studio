"use client";

import { useState } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AlertDialog, AlertDialogTrigger, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from "@/components/ui/alert-dialog";
import { serviceFetch } from "@/lib/service-session";

const copy = {
  "zh-TW": { label: "刪除", title: "刪除此媒體？", note: "將從素材庫及預覽移除，原有下載連結也會失效。成品會連同預覽圖刪除；檔案保留於本機私有回收區，需要復原時請聯絡管理者。", cancel: "保留", confirm: "確認刪除", busy: "刪除中…", failed: "刪除失敗，請確認連線後重試。", inUse: "此素材正在被生成任務使用，請等待任務結束。", active: "任務尚未結束，請先取消並等待停止。", auth: "登入已失效，請重新登入。" },
  en: { label: "Delete", title: "Delete this media?", note: "Remove it from the library and preview and invalidate its download links. Output posters are removed together. Files remain in private local trash; contact the administrator to restore them.", cancel: "Keep", confirm: "Delete media", busy: "Deleting…", failed: "Deletion failed. Check your connection and retry.", inUse: "A generation job is using this asset. Wait for it to finish.", active: "Cancel the active job and wait for it to stop first.", auth: "Your session expired. Sign in again." },
  ja: { label: "削除", title: "このメディアを削除しますか？", note: "素材庫とプレビューから削除され、ダウンロードリンクも無効になります。作品のプレビュー画像も一緒に削除します。ファイルは本機の非公開ごみ箱に保持されます。復元は管理者にお問い合わせください。", cancel: "保持する", confirm: "削除する", busy: "削除中…", failed: "削除できませんでした。接続を確認して再試行してください。", inUse: "生成タスクがこの素材を使用中です。完了までお待ちください。", active: "タスクをキャンセルし、停止してから削除してください。", auth: "ログインの有効期限が切れました。再度ログインしてください。" },
};

export function DeleteMediaButton({ locale, kind, id, name, onDeleted, disabled = false }: {
  locale: keyof typeof copy; kind: "jobs" | "assets"; id: string; name: string; onDeleted: () => void; disabled?: boolean;
}) {
  const text = copy[locale];
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const remove = async () => {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const response = await serviceFetch(`/api/v1/${kind}/${encodeURIComponent(id)}`, { method: "DELETE" });
      if (!response.ok && response.status !== 404) {
        const result = await response.json() as { code?: string };
        throw new Error(result.code === "asset_in_use" ? text.inUse : result.code === "job_active" ? text.active : response.status === 401 || response.status === 403 ? text.auth : text.failed);
      }
      setOpen(false);
      onDeleted();
    } catch (issue) { setError(issue instanceof Error ? issue.message : text.failed); }
    finally { setBusy(false); }
  };
  return <AlertDialog open={open} onOpenChange={(value) => { if (!busy) { setOpen(value); setError(""); } }}>
    <AlertDialogTrigger render={<Button type="button" variant="outline" disabled={disabled} aria-label={`${text.label} ${name}`} className="rounded-none border-[#efc4d0] bg-white text-[10px] text-[#a32e4a] hover:bg-[#fff3f6]" />}><Trash2 className="size-3.5" />{text.label}</AlertDialogTrigger>
    <AlertDialogContent className="rounded-none border border-border bg-white p-6 shadow-xl sm:max-w-md">
      <AlertDialogHeader><AlertDialogTitle className="text-lg font-extrabold">{text.title}</AlertDialogTitle><AlertDialogDescription className="mt-3 text-xs leading-6">{text.note}</AlertDialogDescription></AlertDialogHeader>
      <p className="break-all border-l-2 border-[#e85578] bg-[#fff8fa] p-3 text-xs font-bold">{name}</p>
      {error && <p role="alert" className="text-xs leading-6 text-red-700">{error}</p>}
      <AlertDialogFooter className="m-0 rounded-none border-0 bg-transparent p-0"><AlertDialogCancel disabled={busy} className="rounded-none">{text.cancel}</AlertDialogCancel><AlertDialogAction disabled={busy} onClick={() => void remove()} className="rounded-none bg-[#a32e4a] text-white hover:bg-[#85253c]">{busy ? text.busy : text.confirm}</AlertDialogAction></AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>;
}
