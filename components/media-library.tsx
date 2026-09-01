"use client";
/* eslint-disable next/no-img-element, jsx-a11y/media-has-caption -- Private uploaded media is served directly; no caption track is available for arbitrary uploads. */

import { useEffect, useRef, useState } from "react";
import { Download, Upload, ImagePlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { csrfHeader, serviceFetch } from "@/lib/service-session";
import { DeleteMediaButton } from "@/components/delete-media-button";

export type Asset = { id: string; name: string; url: string; kind: "image" | "video" | "audio"; size_bytes: number; width: number; height: number;
  duration_seconds?: number; source_ratio?: string; suggested_aspect_ratio?: string; suggested_dimensions?: {width: number; height: number}; ratio_error_percent?: number };
export const fileCopy = {
  "zh-TW": { upload: "上傳素材", download: "下載檔案", select: "用於圖片生成", uploading: "上傳中", empty: "尚無上傳素材", failed: "上傳或讀取失敗，請確認登入與連線後重試。", limit: "PNG / JPEG / WebP / MP4 · 單檔上限 50 MiB · 素材庫上限 2 GiB", shared: "共用工作區：所有獲准使用者都能查看及下載素材與產出。圖片可用於生成；MP4 目前僅供保存、預覽與下載。", draft: "快速測試 · 384 × 256 / 17 幀", fixed: "此執行器固定使用 BF16、SDPA、8 + 3 步、x2 放大與自動 VAE 分塊；不使用 CFG／負面提示詞。", estimated: "耗時取決於解析度、幀數與模型載入，非固定秒數。", stage: "階段進度（非剩餘時間）", elapsed: "已耗時", gpu: "目前運算裝置", offline: "GPU 未就緒", selected: "參照圖片", remove: "取消選取", tooLarge: "檔案超過 50 MiB 上限。" },
  en: { upload: "Upload media", download: "Download file", select: "Use for image to video", uploading: "Uploading", empty: "No uploaded assets yet", failed: "Upload or loading failed. Check your login and connection, then retry.", limit: "PNG / JPEG / WebP / MP4 · 50 MiB per file · 2 GiB library", shared: "Shared workspace: all allowed users can view and download assets and outputs. Images can condition generation; MP4 files currently support storage, preview and download only.", draft: "Quick test · 384 × 256 / 17 frames", fixed: "This runner uses BF16, SDPA, 8 + 3 steps, x2 upscaling and automatic VAE tiling. CFG and negative prompts are not used.", estimated: "Time depends on resolution, frame count and model loading, not a fixed estimate.", stage: "Stage progress (not time remaining)", elapsed: "Elapsed", gpu: "Current compute device", offline: "GPU unavailable", selected: "Reference image", remove: "Clear selection", tooLarge: "File exceeds the 50 MiB limit." },
  ja: { upload: "素材をアップロード", download: "ダウンロード", select: "画像から動画を生成", uploading: "アップロード中", empty: "アップロードした素材はありません", failed: "アップロードまたは読込に失敗しました。ログインと接続を確認して再試行してください。", limit: "PNG / JPEG / WebP / MP4 · 1ファイル50 MiB · 素材庫2 GiB", shared: "共有ワークスペース：許可された全ユーザーが素材と出力を閲覧・ダウンロードできます。画像は生成に使用可能。MP4は保存・プレビュー・ダウンロードのみ対応。", draft: "クイックテスト · 384 × 256 / 17フレーム", fixed: "BF16、SDPA、8 + 3ステップ、x2拡大、自動VAEタイルを使用。CFGとネガティブプロンプトは未使用です。", estimated: "処理時間は解像度、フレーム数、モデル読込により変わります。", stage: "段階の進捗（残り時間ではありません）", elapsed: "経過時間", gpu: "現在の計算デバイス", offline: "GPU未準備", selected: "参照画像", remove: "選択解除", tooLarge: "ファイルが50 MiBを超えています。" },
};

const API_BASE = "";

export function MediaLibrary({ locale, onSelect, onDelete }: { locale: keyof typeof fileCopy; onSelect: (asset: Asset) => void; onDelete?: (id: string) => void }) {
  const text = fileCopy[locale];
  const [assets, setAssets] = useState<Asset[]>([]);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const request = useRef<XMLHttpRequest | null>(null);
  const deleted = useRef(new Set<string>());

  useEffect(() => {
    const abort = new AbortController();
    serviceFetch(`${API_BASE}/api/assets`, { signal: abort.signal }).then(async (response) => {
      if (!response.ok) throw new Error();
      const data = await response.json() as { assets?: Asset[] };
      setAssets((data.assets || []).filter(asset => !deleted.current.has(asset.id)));
    }).catch(() => { if (!abort.signal.aborted) setError(text.failed); });
    return () => { abort.abort(); request.current?.abort(); };
  }, [text.failed]);

  const upload = (file?: File) => {
    if (!file) return;
    setError("");
    if (file.size > 50 * 1024 * 1024) { setError(text.tooLarge); return; }
    const xhr = new XMLHttpRequest();
    request.current = xhr;
    xhr.open("POST", `${API_BASE}/api/assets?name=${encodeURIComponent(file.name)}`);
    xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    for (const [name, value] of Object.entries(csrfHeader())) xhr.setRequestHeader(name, value);
    xhr.timeout = 210000;
    xhr.upload.onprogress = (event) => { if (event.lengthComputable) setProgress(Math.round(event.loaded / event.total * 100)); };
    xhr.onload = () => {
      setProgress(null);
      try {
        const result = JSON.parse(xhr.responseText);
        if (xhr.status !== 201) throw new Error(result.error || text.failed);
        setAssets((current) => [result, ...current]);
        if (result.kind === "image") onSelect(result);
      } catch (issue) { setError(issue instanceof SyntaxError ? text.failed : issue instanceof Error ? issue.message : text.failed); }
    };
    xhr.onerror = xhr.ontimeout = () => { setProgress(null); setError(text.failed); };
    xhr.onabort = () => setProgress(null);
    setProgress(0);
    xhr.send(file);
  };

  return <section className="mb-6 border border-border bg-white p-5">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <h2 className="text-xs font-extrabold tracking-[0.13em]">{text.upload}</h2>
      <input ref={input} type="file" accept="image/png,image/jpeg,image/webp,video/mp4,audio/wav,audio/mpeg,audio/flac,audio/mp4,audio/ogg" className="hidden" aria-label={text.upload} onChange={(event) => { upload(event.target.files?.[0]); event.target.value = ""; }} />
      <Button variant="outline" disabled={progress !== null} onClick={() => input.current?.click()} className="rounded-none text-xs"><Upload className="size-4" />{text.upload}</Button>
    </div>
    <p className="mt-3 text-[11px] leading-5 text-muted-foreground">{text.limit} · WAV / MP3 / FLAC / M4A / OGG</p>
    <p className="mt-2 border-l-2 border-[#e85578] pl-3 text-[11px] leading-5">{locale === "zh-TW" ? "個人工作區：只顯示此帳號的素材與產出。圖片可用於生成；MP4 目前用於保存、預覽與下載。" : locale === "en" ? "Private workspace: only your account's assets and outputs appear here. Images can condition generation; MP4 supports storage, preview and download." : "個人ワークスペース：このアカウントの素材と作品のみ表示します。画像は生成に使用可能、MP4は保存・プレビュー・ダウンロードに対応。"}</p>
    {progress !== null && <output className="mt-4 block space-y-2 text-xs">{text.uploading} {progress}%<Progress value={progress} /></output>}
    {error && <p role="alert" className="mt-4 text-xs text-red-700">{error}</p>}
    <div className="mt-5 grid gap-4 sm:grid-cols-2">
      {assets.map((asset) => <article key={asset.id} className="min-w-0 border border-border p-3">
        <div className="flex aspect-video items-center bg-[#101211]">{asset.kind === "image" ? <img src={`${API_BASE}${asset.url}`} alt={asset.name} loading="lazy" className="h-full w-full object-contain" /> : asset.kind === "audio" ? <audio src={asset.url} controls preload="metadata" className="w-full" /> : <video src={`${API_BASE}${asset.url}`} controls preload="metadata" className="h-full w-full object-contain" />}</div>
        <p className="mt-3 truncate text-xs font-bold" title={asset.name}>{asset.name}</p>
        <p className="mt-1 text-[10px] text-muted-foreground">{asset.kind === "audio" ? `${asset.duration_seconds?.toFixed(2)}s` : `${asset.width} × ${asset.height}`} · {(asset.size_bytes / 1024 / 1024).toFixed(2)} MiB</p>
        <div className="mt-3 flex flex-wrap gap-3">
          <a href={`${API_BASE}${asset.url}?download=1`} className="inline-flex items-center gap-1 border border-border px-3 py-2 text-[10px] font-bold hover:border-[#e85578]"><Download className="size-3" />{text.download}</a>
          {asset.kind === "image" && <Button onClick={() => onSelect(asset)} variant="outline" className="rounded-none text-[10px]"><ImagePlus className="size-3" />{text.select}</Button>}
          <DeleteMediaButton locale={locale} kind="assets" id={asset.id} name={asset.name} onDeleted={() => { deleted.current.add(asset.id); setAssets(current => current.filter(item => item.id !== asset.id)); onDelete?.(asset.id); }} />
        </div>
      </article>)}
    </div>
    {assets.length === 0 && <p className="py-6 text-center text-xs text-muted-foreground">{text.empty}</p>}
  </section>;
}
