'use client';
/* eslint-disable jsx-a11y/media-has-caption -- The uploaded music and its user-supplied lyrics are shown together. */
import {
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react';
import {
  Braces,
  Download,
  Film,
  ListPlus,
  Music2,
  Plus,
  RotateCcw,
  Trash2,
  Upload,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { serviceFetch } from '@/lib/service-session';
import type { VideoCapabilities } from '@/lib/video-settings';
import type { Asset } from '@/components/media-library';
import {
  type LrcRow,
  displayedLrcTime,
  formatLrcRows,
  parseLrcRows,
  resetLrcTimes,
  storedLrcTime,
} from '@/lib/lrc-editor';
import {
  parseTimelineImport,
  serializeShotPlan,
} from '@/lib/timeline-import';

type Locale = 'zh-TW' | 'en' | 'ja';
export type Directing = Record<string, string>;
export type Cue = { time: number; action: string; directing: Directing };
export type TimelineDraft = {
  enabled: boolean;
  music: Asset | null;
  audioStart: number;
  audioMode: string;
  lrc: string;
  lrcTimebase: 'output' | 'music';
  cues: Cue[];
  segmentSeconds: number;
};
export const emptyTimeline: TimelineDraft = {
  enabled: false,
  music: null,
  audioStart: 0,
  audioMode: 'soundtrack',
  lrc: '',
  lrcTimebase: 'output',
  cues: [],
  segmentSeconds: 10,
};
export const mvCopy = {
  'zh-TW': {
    title: 'MV 時間軸 / 最長 180 秒',
    enabled: '使用分鏡時間軸',
    single: '單鏡頭生成',
    sequence: '分段生成後組片',
    director: '分鏡／鏡頭／情緒',
    none: '依提示詞／不指定',
    music: '音樂母帶',
    noMusic: '不匯入音樂',
    importMusic: '匯入音樂',
    importLrc: '匯入 LRC',
    importJson: '匯入分鏡 JSON',
    exportJson: '匯出分鏡 JSON',
    jsonHint:
      '可匯入完整 /api/v1/jobs 設定，或只有 {lrc, cues} 的子集，方便其他語言模型產出檔案。匯出會寫成同一份標準格式，可直接再匯入。',
    resetTimes: '重設時間',
    noBaseline: '尚無匯入紀錄可重設，請先匯入 LRC 或 JSON。',
    basisOutput: '時間以成片起點計算',
    basisMusic: '時間以原始音樂計算，顯示值已扣除音樂起點',
    addCue: '設為分鏡',
    cueFromSelection: '選取行合併為一個分鏡',
    selectRow: '選取此行',
    removeRow: '刪除此行',
    ignoredFields: '以下欄位不屬於時間軸，未套用：',
    audioMissing: 'JSON 指定的音樂素材不在你的素材庫，音樂未套用。',
    cueExists: '該時間點已有分鏡。',
    lrc: '歌詞 LRC',
    lrcRows: '解析後逐句時間',
    timebase: 'LRC 秒數基準',
    outputTime: '成片起點',
    musicTime: '原始音樂時間（隨音樂起點自動增減）',
    beforeStart: '早於音樂起點，成片會略過',
    audioStart: '音樂起點（秒）',
    segment: '每鏡最長秒數',
    audioMode: '音樂用途',
    soundtrack: '連續配樂，不驅動嘴型',
    condition: '音訊驅動表演（實驗）',
    warning:
      'LRC 是逐句時間碼，不是音素對齊。音訊驅動會把音樂送入模型，但不保證嘴型、咬字或舞步精準同步；請先測試短段單人正面演出。',
    note: '最長 180 秒由獨立鏡頭組成，並非同一長鏡頭。匯入音樂只編碼一次、連續鋪底；角色連戲需審片。每鏡會受主機幀數限制再切分。',
    cues: '動作與表演時間點',
    add: '新增時間點',
    time: '開始秒數',
    action: '此時間點後的主要動作',
    remove: '移除',
    preview: '預覽分鏡（不生成）',
    loading: '處理中…',
    error: '處理失敗，請檢查格式、登入與連線。',
    plan: '送入模型的分鏡計畫',
    stale: '設定已改變，請重新預覽分鏡。',
    fitMusic: '使用音樂剩餘長度（最多180秒）',
    source: '跟隨參照圖片',
    aligned: '已依圖片比例設定；64px 對齊若有差異，採留邊、不裁切。',
    fullPrompt: '完整鏡頭提示詞',
    imageImport: '直接匯入參照圖片',
    field: {
      shot_size: '景別',
      angle: '人物／相機角度',
      camera: '運鏡',
      emotion: '情緒與微表演',
      performance: '演出方式',
    },
  },
  en: {
    title: 'MV timeline / up to 180 seconds',
    enabled: 'Use shot timeline',
    single: 'Single shot',
    sequence: 'Generate shots and assemble',
    director: 'Shot / camera / emotion',
    none: 'From prompt / unspecified',
    music: 'Music master',
    noMusic: 'No imported music',
    importMusic: 'Import music',
    importLrc: 'Import LRC',
    importJson: 'Import shot JSON',
    exportJson: 'Export shot JSON',
    jsonHint:
      'Accepts a full /api/v1/jobs payload, or just {lrc, cues}, so another language model can generate the file. Export writes that same standard format back.',
    resetTimes: 'Reset times',
    noBaseline: 'Nothing to reset yet. Import an LRC or JSON file first.',
    basisOutput: 'Times are relative to the output start',
    basisMusic: 'Times follow the original music; the music start is already subtracted',
    addCue: 'Make a cue',
    cueFromSelection: 'Merge selected lines into one cue',
    selectRow: 'Select this line',
    removeRow: 'Delete this line',
    ignoredFields: 'These fields are not timeline settings and were not applied:',
    audioMissing: 'The music asset named in the JSON is not in your library; music was not applied.',
    cueExists: 'A cue already exists at that time.',
    lrc: 'LRC lyrics',
    lrcRows: 'Parsed line timing',
    timebase: 'LRC time basis',
    outputTime: 'Output start',
    musicTime: 'Original music time (follows music start)',
    beforeStart: 'Before music start; skipped in output',
    audioStart: 'Music start (seconds)',
    segment: 'Maximum seconds per shot',
    audioMode: 'Music use',
    soundtrack: 'Continuous soundtrack, no lip driving',
    condition: 'Audio-driven performance (experimental)',
    warning:
      'LRC is line timing, not phoneme alignment. Audio conditioning feeds music to the model but cannot guarantee accurate lips, pronunciation or dance. Test a short frontal solo shot first.',
    note: 'Up to 180 seconds of independent shots, not one continuous take. Imported music is encoded once as a continuous master. Review character continuity. The host frame cap may split shots further.',
    cues: 'Action and performance cues',
    add: 'Add cue',
    time: 'Start seconds',
    action: 'Main action after this cue',
    remove: 'Remove',
    preview: 'Preview shot plan (no generation)',
    loading: 'Working…',
    error: 'Unable to process. Check format, login and connection.',
    plan: 'Shot plan sent to the model',
    stale: 'Settings changed; preview the plan again.',
    fitMusic: 'Use remaining music (up to 180s)',
    source: 'Follow reference image',
    aligned:
      'Ratio set from the reference; 64px alignment differences use letterboxing, not cropping.',
    fullPrompt: 'Full shot prompt',
    imageImport: 'Import reference image',
    field: {
      shot_size: 'Shot size',
      angle: 'View angle',
      camera: 'Camera movement',
      emotion: 'Emotion / micro-performance',
      performance: 'Performance',
    },
  },
  ja: {
    title: 'MV タイムライン / 最大180秒',
    enabled: 'ショット時間軸を使用',
    single: '単一ショット',
    sequence: '分割生成して結合',
    director: 'ショット／カメラ／感情',
    none: 'プロンプトに従う／指定なし',
    music: '音楽マスター',
    noMusic: '音楽を選択しない',
    importMusic: '音楽を読み込む',
    importLrc: 'LRCを読み込む',
    importJson: 'ショットJSONを読み込む',
    exportJson: 'ショットJSONを書き出す',
    jsonHint:
      '完全な /api/v1/jobs 設定、または {lrc, cues} だけの部分設定を受け付けます。書き出しも同じ標準形式です。',
    resetTimes: '時間を再設定',
    noBaseline: '再設定できる読み込み履歴がありません。先にLRCかJSONを読み込んでください。',
    basisOutput: '時間は完成尺の開始が基準です',
    basisMusic: '時間は元の音楽が基準で、表示値は音楽の開始秒を差し引いています',
    addCue: 'ショットにする',
    cueFromSelection: '選択行を1つのショットにまとめる',
    selectRow: 'この行を選択',
    removeRow: 'この行を削除',
    ignoredFields: '以下はタイムライン設定ではないため適用していません：',
    audioMissing: 'JSONで指定された音楽素材がライブラリにないため、音楽は適用していません。',
    cueExists: 'その時点には既にショットがあります。',
    lrc: 'LRC歌詞',
    lrcRows: '解析した行の時間',
    timebase: 'LRC時間基準',
    outputTime: '作品の開始',
    musicTime: '元の音楽時間（音楽開始に追従）',
    beforeStart: '音楽開始より前のため作品では省略',
    audioStart: '音楽の開始秒',
    segment: '各ショットの最大秒数',
    audioMode: '音楽の用途',
    soundtrack: '連続BGM・口の動きは制御しない',
    condition: '音声駆動の演技（実験的）',
    warning:
      'LRCは行単位の時刻で、音素の同期ではありません。音声条件はモデルに音楽を渡しますが、口形・発音・ダンスの正確な同期は保証しません。まず短い一人の正面ショットを試してください。',
    note: '最大180秒は独立ショットの結合で、連続した長回しではありません。音楽は一度エンコードして連続配置します。人物の連続性は確認が必要です。ホスト上限によりさらに分割されます。',
    cues: '動作と演技のタイミング',
    add: 'キューを追加',
    time: '開始秒',
    action: 'この時点以降の主な動作',
    remove: '削除',
    preview: 'ショット計画を確認（生成なし）',
    loading: '処理中…',
    error: '処理できません。形式・ログイン・接続を確認してください。',
    plan: 'モデルに渡すショット計画',
    stale: '設定が変わりました。計画を再確認してください。',
    fitMusic: '音楽の残り時間を使用（最大180秒）',
    source: '参照画像に合わせる',
    aligned: '画像の比率を設定。64pxの整列差は余白で調整し、切り抜きません。',
    fullPrompt: 'ショットの全文プロンプト',
    imageImport: '参照画像を読み込む',
    field: {
      shot_size: 'ショットサイズ',
      angle: '視点の角度',
      camera: 'カメラの動き',
      emotion: '感情と微表情',
      performance: '演技',
    },
  },
};

export function DirectingControls({
  locale,
  catalog,
  value,
  onChange,
  compact = false,
}: {
  locale: Locale;
  catalog: VideoCapabilities['directing'];
  value: Directing;
  onChange: (value: Directing) => void;
  compact?: boolean;
}) {
  const text = mvCopy[locale];
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {Object.entries(catalog || {})
        .filter(
          ([key]) =>
            !compact || ['emotion', 'camera', 'performance'].includes(key),
        )
        .map(([key, options]) => (
          <label key={key} className="min-w-0 text-[10px] font-bold">
            <span className="mb-2 block">
              {text.field[key as keyof typeof text.field]}
            </span>
            <Select
              value={value[key] || 'none'}
              onValueChange={(selected) => {
                if (!selected) return;
                const next = { ...value };
                if (selected === 'none') delete next[key];
                else next[key] = selected;
                onChange(next);
              }}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">{text.none}</SelectItem>
                {Object.entries(options).map(([id, option]) => (
                  <SelectItem key={id} value={id}>
                    {option.label[locale]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
        ))}
    </div>
  );
}

type Shot = {
  index: number;
  start_seconds: number;
  duration_seconds: number;
  lyrics: string;
  action: string;
  prompt: string;
};
export function TimelineControls({
  locale,
  catalog,
  value,
  onChange,
  request,
  onDuration,
}: {
  locale: Locale;
  catalog: VideoCapabilities['directing'];
  value: TimelineDraft;
  onChange: Dispatch<SetStateAction<TimelineDraft>>;
  request: Record<string, unknown>;
  onDuration: (seconds: number) => void;
}) {
  const text = mvCopy[locale];
  const [assets, setAssets] = useState<Asset[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [plan, setPlan] = useState<{
    fingerprint: string;
    shots: Shot[];
    warnings: string[];
  } | null>(null);
  const musicInput = useRef<HTMLInputElement>(null);
  const lrcInput = useRef<HTMLInputElement>(null);
  const jsonInput = useRef<HTMLInputElement>(null);
  // Timestamps as they arrived, so "reset times" can restore them without
  // touching lyrics the user has since tidied up.
  const [lrcBaseline, setLrcBaseline] = useState('');
  // Lyrics being typed. Kept aside so clearing a field does not delete the row
  // the moment the LRC text no longer parses.
  const [lyricDrafts, setLyricDrafts] = useState<Record<number, string>>({});
  const [selectedRows, setSelectedRows] = useState<number[]>([]);
  const [notice, setNotice] = useState('');
  const fingerprint = JSON.stringify(request);
  const lrcRows = parseLrcRows(value.lrc);
  useEffect(() => {
    const abort = new AbortController();
    serviceFetch('/api/v1/assets', { signal: abort.signal })
      .then(async (result) => {
        if (!result.ok) throw new Error();
        return result.json() as Promise<{ assets: Asset[] }>;
      })
      .then((data) =>
        setAssets(data.assets.filter((asset) => asset.kind === 'audio')),
      )
      .catch(() => {
        if (!abort.signal.aborted) setError(text.error);
      });
    return () => abort.abort();
  }, [text.error]);
  const uploadMusic = async (file?: File) => {
    if (!file) return;
    setPending(true);
    setError('');
    try {
      if (file.size > 50 * 1024 * 1024) throw new Error('50 MiB maximum');
      const types: Record<string, string> = {
        wav: 'audio/wav',
        mp3: 'audio/mpeg',
        flac: 'audio/flac',
        m4a: 'audio/mp4',
        ogg: 'audio/ogg',
      };
      const mime = types[file.name.split('.').pop()?.toLowerCase() || ''];
      if (!mime) throw new Error('WAV / MP3 / FLAC / M4A / OGG');
      const result = await serviceFetch(
        `/api/v1/assets?name=${encodeURIComponent(file.name)}`,
        { method: 'POST', headers: { 'Content-Type': mime }, body: file },
      );
      const asset = (await result.json()) as Asset & { error?: string };
      if (!result.ok) throw new Error(asset.error || text.error);
      setAssets((current) => [asset, ...current]);
      onChange((current) => ({
        ...current,
        enabled: true,
        music: asset,
        audioStart: 0,
      }));
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : text.error);
    } finally {
      setPending(false);
    }
  };
  const importLrc = async (file?: File) => {
    if (!file) return;
    try {
      if (file.size > 64000) throw new Error('LRC exceeds 64 KB');
      const lrc = new TextDecoder('utf-8', { fatal: true }).decode(
        await file.arrayBuffer(),
      );
      if (lrc.length > 16000) throw new Error('LRC exceeds 16000 characters');
      onChange((current) => ({
        ...current,
        enabled: true,
        lrc,
        lrcTimebase: current.music ? 'music' : 'output',
      }));
      setLrcBaseline(lrc);
      setLyricDrafts({});
      setSelectedRows([]);
      setNotice('');
      setError('');
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : text.error);
    }
  };
  const writeRows = (rows: LrcRow[]) =>
    onChange((current) => ({
      ...current,
      enabled: true,
      lrc: formatLrcRows(rows),
    }));
  // Structural edits invalidate any in-flight typing and row selection.
  const replaceRows = (rows: LrcRow[]) => {
    setLyricDrafts({});
    setSelectedRows([]);
    writeRows(rows);
  };
  const resetTimes = () => {
    const baseline = parseLrcRows(lrcBaseline);
    if (!baseline.length) {
      setError(text.noBaseline);
      return;
    }
    setError('');
    setNotice('');
    replaceRows(resetLrcTimes(lrcRows, baseline));
  };
  // Cue times live on the output timeline, which is what the displayed LRC
  // second already is; a line before the music start is never rendered.
  const addCueAt = (seconds: number) => {
    if (seconds < 0) {
      setError(text.beforeStart);
      return;
    }
    const time = Math.round(seconds * 1000) / 1000;
    if (value.cues.some((cue) => Math.abs(cue.time - time) < 0.0005)) {
      setError(text.cueExists);
      return;
    }
    setError('');
    setNotice('');
    onChange((current) => ({
      ...current,
      enabled: true,
      cues: [...current.cues, { time, action: '', directing: {} }].sort(
        (a, b) => a.time - b.time,
      ),
    }));
  };
  const rowSeconds = (index: number) =>
    displayedLrcTime(lrcRows[index].time, value.audioStart, value.lrcTimebase);
  const cueFromSelection = () => {
    if (!selectedRows.length) return;
    addCueAt(Math.min(...selectedRows.map(rowSeconds)));
    setSelectedRows([]);
  };
  const importJson = async (file?: File) => {
    if (!file) return;
    try {
      if (file.size > 256000) throw new Error('JSON exceeds 250 KB');
      const source = new TextDecoder('utf-8', { fatal: true }).decode(
        await file.arrayBuffer(),
      );
      const imported = parseTimelineImport(source, catalog);
      const music = imported.audioId
        ? (assets.find((asset) => asset.id === imported.audioId) ?? null)
        : null;
      onChange((current) => {
        const nextMusic = music ?? current.music;
        // Music-dependent settings are dropped rather than sent to a worker
        // that would reject the whole job for an unusable combination.
        const timebase =
          imported.lrcTimebase && (imported.lrcTimebase === 'output' || nextMusic)
            ? imported.lrcTimebase
            : current.lrcTimebase;
        const mode =
          imported.audioMode && (imported.audioMode === 'soundtrack' || nextMusic)
            ? imported.audioMode
            : current.audioMode;
        return {
          ...current,
          enabled: true,
          lrc: imported.lrc ?? current.lrc,
          lrcTimebase: timebase,
          cues: imported.cues ?? current.cues,
          audioMode: mode,
          audioStart:
            imported.audioStart !== undefined && nextMusic
              ? imported.audioStart
              : current.audioStart,
          segmentSeconds: imported.segmentSeconds ?? current.segmentSeconds,
          music: nextMusic,
        };
      });
      if (imported.durationSeconds !== undefined) onDuration(imported.durationSeconds);
      if (imported.lrc !== undefined) setLrcBaseline(imported.lrc);
      setLyricDrafts({});
      setSelectedRows([]);
      setError('');
      setNotice(
        [
          imported.audioId && !music ? text.audioMissing : '',
          imported.ignored.length
            ? `${text.ignoredFields} ${imported.ignored.join(', ')}`
            : '',
        ]
          .filter(Boolean)
          .join(' '),
      );
    } catch (issue) {
      setNotice('');
      setError(issue instanceof Error ? issue.message : text.error);
    }
  };
  const exportJson = () => {
    setError('');
    setNotice('');
    const { filename, source } = serializeShotPlan(request);
    const url = URL.createObjectURL(
      new Blob([source], { type: 'application/json' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    // Released on the next task so the download has taken the URL first.
    setTimeout(() => URL.revokeObjectURL(url));
  };
  const preview = async () => {
    setPending(true);
    setError('');
    try {
      const result = await serviceFetch('/api/v1/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: fingerprint,
      });
      const data = (await result.json()) as {
        error?: string;
        resolved_parameters: { segments?: Shot[]; prompt: string };
        configured_duration_seconds: number;
        effective_prompt?: string;
        warnings?: string[];
      };
      if (!result.ok) throw new Error(data.error || text.error);
      const resolved = data.resolved_parameters;
      setPlan({
        fingerprint,
        shots: resolved.segments || [
          {
            index: 1,
            start_seconds: 0,
            duration_seconds: data.configured_duration_seconds,
            lyrics: '',
            action: '',
            prompt: data.effective_prompt || resolved.prompt,
          },
        ],
        warnings: data.warnings || [],
      });
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : text.error);
    } finally {
      setPending(false);
    }
  };
  const cueChange = (index: number, patch: Partial<Cue>) =>
    onChange({
      ...value,
      enabled: true,
      cues: value.cues.map((cue, i) =>
        i === index ? { ...cue, ...patch } : cue,
      ),
    });
  return (
    <section className="border border-border bg-white">
      <header className="flex items-center gap-2 border-b border-border p-5">
        <Film className="size-4 text-[#e85578]" />
        <h2 className="text-xs font-extrabold tracking-[0.12em]">
          {text.title}
        </h2>
      </header>
      <div className="space-y-5 p-5">
        <p className="text-[11px] leading-6 text-muted-foreground">
          {text.note}
        </p>
        <label className="block text-xs font-semibold">
          {text.enabled}
          <Select
            value={value.enabled ? 'sequence' : 'single'}
            onValueChange={(mode) =>
              onChange(
                mode === 'single'
                  ? { ...emptyTimeline }
                  : { ...value, enabled: true },
              )
            }
          >
            <SelectTrigger className="mt-2 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="single">{text.single}</SelectItem>
              <SelectItem value="sequence">{text.sequence}</SelectItem>
            </SelectContent>
          </Select>
        </label>
        <div className="flex flex-wrap gap-2">
          <input
            ref={musicInput}
            type="file"
            accept=".wav,.mp3,.flac,.m4a,.ogg"
            className="hidden"
            aria-label={text.importMusic}
            onChange={(event) => {
              void uploadMusic(event.target.files?.[0]);
              event.target.value = '';
            }}
          />
          <input
            ref={lrcInput}
            type="file"
            accept=".lrc,text/plain"
            className="hidden"
            aria-label={text.importLrc}
            onChange={(event) => {
              void importLrc(event.target.files?.[0]);
              event.target.value = '';
            }}
          />
          <Button
            variant="outline"
            className="rounded-none text-xs"
            disabled={pending}
            onClick={() => musicInput.current?.click()}
          >
            <Music2 />
            {text.importMusic}
          </Button>
          <input
            ref={jsonInput}
            type="file"
            accept=".json,application/json"
            className="hidden"
            aria-label={text.importJson}
            onChange={(event) => {
              void importJson(event.target.files?.[0]);
              event.target.value = '';
            }}
          />
          <Button
            variant="outline"
            className="rounded-none text-xs"
            disabled={pending}
            onClick={() => lrcInput.current?.click()}
          >
            <Upload />
            {text.importLrc}
          </Button>
          <Button
            variant="outline"
            className="rounded-none text-xs"
            disabled={pending}
            onClick={() => jsonInput.current?.click()}
          >
            <Braces />
            {text.importJson}
          </Button>
          <Button
            variant="outline"
            className="rounded-none text-xs"
            disabled={pending || !value.enabled}
            onClick={exportJson}
          >
            <Download />
            {text.exportJson}
          </Button>
        </div>
        <p className="text-[10px] leading-5 text-muted-foreground">
          {text.jsonHint}
        </p>
        {notice && (
          <p className="text-[10px] leading-5 text-amber-800">{notice}</p>
        )}
        <label className="block text-xs font-semibold">
          {text.music}
          <Select
            value={value.music?.id || 'none'}
            onValueChange={(id) =>
              onChange({
                ...value,
                enabled: true,
                music: assets.find((asset) => asset.id === id) || null,
                audioStart: 0,
              })
            }
          >
            <SelectTrigger className="mt-2 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">{text.noMusic}</SelectItem>
              {assets.map((asset) => (
                <SelectItem key={asset.id} value={asset.id}>
                  {asset.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>
        {value.music && (
          <div className="space-y-3 border border-[#bfe8e3] bg-[#f0fbf9] p-3">
            <audio
              controls
              src={value.music.url}
              preload="metadata"
              className="w-full"
            />
            <p className="text-[10px]">
              {value.music.name} · {value.music.duration_seconds?.toFixed(3)}s
            </p>
            <label className="block text-xs">
              {text.audioStart}
              <Input
                className="mt-2 rounded-none"
                type="number"
                min="0"
                step="0.001"
                value={value.audioStart}
                onChange={(event) =>
                  onChange({ ...value, audioStart: Number(event.target.value) })
                }
              />
            </label>
            <Button
              variant="outline"
              className="h-auto whitespace-normal rounded-none text-xs"
              onClick={() =>
                onDuration(
                  Math.floor(
                    Math.min(
                      180,
                      (value.music?.duration_seconds || 0) - value.audioStart,
                    ) * 1000,
                  ) / 1000,
                )
              }
            >
              {text.fitMusic}
            </Button>
            <label className="block text-xs">
              {text.audioMode}
              <Select
                value={value.audioMode}
                onValueChange={(mode) =>
                  mode && onChange({ ...value, audioMode: mode })
                }
              >
                <SelectTrigger className="mt-2 w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="soundtrack">{text.soundtrack}</SelectItem>
                  <SelectItem value="condition">{text.condition}</SelectItem>
                </SelectContent>
              </Select>
            </label>
          </div>
        )}
        <p className="border-l-2 border-[#e85578] pl-3 text-[11px] leading-6">
          {text.warning}
        </p>
        <label className="block text-xs font-semibold">
          {text.segment}
          <Select
            value={String(value.segmentSeconds)}
            onValueChange={(seconds) =>
              seconds &&
              onChange({
                ...value,
                enabled: true,
                segmentSeconds: Number(seconds),
              })
            }
          >
            <SelectTrigger className="mt-2 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[2, 4, 6, 8, 10, 15, 20].map((seconds) => (
                <SelectItem key={seconds} value={String(seconds)}>
                  {seconds}s
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>
        <label className="block text-xs font-semibold">
          {text.lrc}
          <Textarea
            className="mt-2 min-h-32 rounded-none font-mono text-xs"
            maxLength={16000}
            value={value.lrc}
            placeholder={'[00:00.00]Intro\n[00:04.50]Your lyrics'}
            onChange={(event) =>
              onChange({ ...value, enabled: true, lrc: event.target.value })
            }
          />
        </label>
        <label className="block text-xs font-semibold">
          {text.timebase}
          <Select
            value={value.lrcTimebase}
            onValueChange={(timebase) =>
              timebase &&
              onChange({
                ...value,
                lrcTimebase: timebase as 'output' | 'music',
              })
            }
          >
            <SelectTrigger className="mt-2 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="output">{text.outputTime}</SelectItem>
              <SelectItem value="music" disabled={!value.music}>
                {text.musicTime}
              </SelectItem>
            </SelectContent>
          </Select>
        </label>
        {lrcRows.length > 0 && (
          <section className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-xs font-bold">{text.lrcRows}</h3>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  className="h-7 rounded-none px-2 text-[10px]"
                  disabled={!selectedRows.length || value.cues.length >= 60}
                  onClick={cueFromSelection}
                >
                  <ListPlus />
                  {text.cueFromSelection}
                  {selectedRows.length > 0 && ` (${selectedRows.length})`}
                </Button>
                <Button
                  variant="outline"
                  className="h-7 rounded-none px-2 text-[10px]"
                  onClick={resetTimes}
                >
                  <RotateCcw />
                  {text.resetTimes}
                </Button>
              </div>
            </div>
            <p className="text-[10px] text-muted-foreground">
              {value.lrcTimebase === 'music'
                ? `${text.basisMusic} (${value.audioStart}s)`
                : text.basisOutput}
            </p>
            <div className="max-h-80 space-y-2 overflow-y-auto">
              {lrcRows.map((row, index) => {
                const shown = displayedLrcTime(
                  row.time,
                  value.audioStart,
                  value.lrcTimebase,
                );
                const selected = selectedRows.includes(index);
                return (
                  <div
                    key={`${row.time}-${index}`}
                    className="grid grid-cols-[20px_108px_minmax(0,1fr)_auto] items-start gap-3 border border-border bg-[#fafaf8] p-3"
                  >
                    <input
                      type="checkbox"
                      className="mt-5 size-3.5 accent-[#25b6a6]"
                      aria-label={`${text.selectRow}: ${row.text}`}
                      checked={selected}
                      onChange={() =>
                        setSelectedRows((current) =>
                          selected
                            ? current.filter((item) => item !== index)
                            : [...current, index],
                        )
                      }
                    />
                    <label className="text-[9px] font-bold">
                      {text.time}
                      <Input
                        type="number"
                        step="0.001"
                        min={
                          value.lrcTimebase === 'music' ? -value.audioStart : 0
                        }
                        value={shown}
                        className="mt-1 rounded-none bg-white"
                        onChange={(event) => {
                          writeRows(
                            lrcRows.map((item, i) =>
                              i === index
                                ? {
                                    ...item,
                                    time: storedLrcTime(
                                      Number(event.target.value),
                                      value.audioStart,
                                      value.lrcTimebase,
                                    ),
                                  }
                                : item,
                            ),
                          );
                        }}
                      />
                    </label>
                    <div className="min-w-0">
                      <label className="text-[9px] font-bold">
                        {text.lrc}
                        <Input
                          maxLength={500}
                          value={lyricDrafts[index] ?? row.text}
                          className="mt-1 rounded-none bg-white text-xs"
                          onChange={(event) => {
                            const next = event.target.value;
                            setLyricDrafts((current) => ({
                              ...current,
                              [index]: next,
                            }));
                            // An empty line would not parse back, so the row is
                            // kept until it is removed deliberately.
                            if (next.trim()) {
                              writeRows(
                                lrcRows.map((item, i) =>
                                  i === index ? { ...item, text: next } : item,
                                ),
                              );
                            }
                          }}
                        />
                      </label>
                      {shown < 0 && (
                        <p className="mt-1 text-[9px] text-amber-800">
                          {text.beforeStart}
                        </p>
                      )}
                    </div>
                    <div className="mt-4 flex gap-1">
                      <Button
                        variant="ghost"
                        className="size-7 rounded-none p-0"
                        aria-label={`${text.addCue}: ${row.text}`}
                        title={text.addCue}
                        disabled={value.cues.length >= 60}
                        onClick={() => addCueAt(shown)}
                      >
                        <Plus />
                      </Button>
                      <Button
                        variant="ghost"
                        className="size-7 rounded-none p-0"
                        aria-label={`${text.removeRow}: ${row.text}`}
                        title={text.removeRow}
                        onClick={() =>
                          replaceRows(lrcRows.filter((_, i) => i !== index))
                        }
                      >
                        <Trash2 />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold">{text.cues}</h3>
          <Button
            variant="outline"
            className="rounded-none text-xs"
            disabled={value.cues.length >= 60}
            onClick={() =>
              onChange({
                ...value,
                enabled: true,
                cues: [
                  ...value.cues,
                  {
                    time: value.cues.length
                      ? value.cues[value.cues.length - 1].time + 4
                      : 0,
                    action: '',
                    directing: {},
                  },
                ],
              })
            }
          >
            <Plus />
            {text.add}
          </Button>
        </div>
        {value.cues.map((cue, index) => (
          <div
            key={index}
            className="space-y-3 border border-border bg-[#fafaf8] p-3"
          >
            <div className="flex gap-3">
              <label className="flex-1 text-[10px]">
                {text.time}
                <Input
                  type="number"
                  min="0"
                  max="179.999"
                  step="0.001"
                  value={cue.time}
                  className="mt-1 rounded-none"
                  onChange={(event) =>
                    cueChange(index, { time: Number(event.target.value) })
                  }
                />
              </label>
              <Button
                variant="ghost"
                aria-label={text.remove}
                className="self-end"
                onClick={() =>
                  onChange({
                    ...value,
                    cues: value.cues.filter((_, i) => i !== index),
                  })
                }
              >
                <Trash2 />
              </Button>
            </div>
            <label className="block text-[10px]">
              {text.action}
              <Textarea
                className="mt-1 rounded-none text-xs"
                maxLength={600}
                value={cue.action}
                onChange={(event) =>
                  cueChange(index, { action: event.target.value })
                }
              />
            </label>
            <DirectingControls
              locale={locale}
              catalog={catalog}
              compact
              value={cue.directing}
              onChange={(directing) => cueChange(index, { directing })}
            />
          </div>
        ))}
        {error && (
          <p role="alert" className="text-xs text-red-700">
            {error}
          </p>
        )}
        <Button
          variant="outline"
          className="w-full rounded-none text-xs"
          disabled={pending}
          onClick={preview}
        >
          {pending ? text.loading : text.preview}
        </Button>
        {plan && (
          <section className="space-y-2">
            <h3 className="text-xs font-bold">{text.plan}</h3>
            {plan.fingerprint !== fingerprint ? (
              <p className="text-xs text-amber-800">{text.stale}</p>
            ) : (
              <div className="max-h-96 space-y-2 overflow-y-auto">
                {plan.shots.map((shot) => (
                  <article
                    key={shot.index}
                    className="border-l-2 border-[#25b6a6] bg-[#fafaf8] p-3 text-xs"
                  >
                    <strong>
                      S{String(shot.index).padStart(2, '0')} ·{' '}
                      {shot.start_seconds.toFixed(3)}–
                      {(shot.start_seconds + shot.duration_seconds).toFixed(3)}s
                    </strong>
                    <p className="mt-1 whitespace-pre-wrap">
                      {shot.lyrics || shot.action}
                    </p>
                    <details className="mt-2">
                      <summary className="cursor-pointer text-[10px] text-muted-foreground">
                        {text.fullPrompt}
                      </summary>
                      <p className="mt-2 whitespace-pre-wrap leading-6">
                        {shot.prompt}
                      </p>
                    </details>
                  </article>
                ))}
                {plan.warnings.map((warning) => (
                  <p
                    key={warning}
                    className="text-[10px] text-muted-foreground"
                  >
                    {warning}
                  </p>
                ))}
              </div>
            )}
          </section>
        )}
      </div>
    </section>
  );
}
