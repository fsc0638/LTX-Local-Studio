'use client';
/* eslint-disable next/no-img-element -- Private uploaded references are served directly. */

import { useEffect, useState } from 'react';
import { ShieldCheck, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import type { Asset } from '@/components/media-library';
import { serviceFetch } from '@/lib/service-session';

export type CharacterView =
  | 'front'
  | 'left_three_quarter'
  | 'right_three_quarter'
  | 'left_profile'
  | 'right_profile'
  | 'back'
  | 'full_body';
export type CharacterReference = { asset: Asset; view: CharacterView };
export type CharacterDraft = {
  enabled: boolean;
  name: string;
  description: string;
  references: CharacterReference[];
};
export const emptyCharacter: CharacterDraft = {
  enabled: false,
  name: '',
  description: '',
  references: [],
};

const copy = {
  'zh-TW': {
    title: '人物一致性鎖定',
    enabled: '啟用人物鎖定',
    note: '每鏡固定人物描述與 seed，並依分鏡角度選最接近的參照圖。這不是人物訓練；生成後仍要審片。',
    name: '人物名稱',
    description: '不可變的人物設定',
    placeholder:
      '臉型、五官、髮型髮色、膚色、年齡感、體型、服裝與辨識特徵。不要寫動作或場景。',
    add: '把目前圖片加入設定集',
    library: '從素材庫加入其他視角',
    primary: '首鏡基準',
    makePrimary: '設為首鏡基準',
    remove: '移除',
    needs:
      '至少需要名稱、人物設定與一張參照圖。建議正面、左右 3/4、左右側面與全身照；同一服裝、光線與背景越單純越好。',
  },
  en: {
    title: 'Character consistency lock',
    enabled: 'Enable character lock',
    note: 'Keeps identity text and seed fixed, then selects the closest reference angle for each shot. This is not character training; review every render.',
    name: 'Character name',
    description: 'Invariant character definition',
    placeholder:
      'Face shape, features, hair, skin tone, apparent age, build, wardrobe and distinctive traits. Exclude action and scene.',
    add: 'Add current image to set',
    library: 'Add another view from library',
    primary: 'Opening-frame anchor',
    makePrimary: 'Use as opening anchor',
    remove: 'Remove',
    needs:
      'Name, definition and at least one reference are required. Front, left/right 3/4, profiles and full body are recommended with consistent wardrobe and simple lighting.',
  },
  ja: {
    title: '人物一貫性ロック',
    enabled: '人物ロックを有効化',
    note: '人物設定とseedを固定し、各ショットの角度に近い参照画像を選択します。人物学習ではないため、生成後の確認は必要です。',
    name: '人物名',
    description: '変えない人物設定',
    placeholder:
      '顔立ち、髪、肌、年齢感、体格、衣装、識別特徴。動作や場所は書かないでください。',
    add: '現在の画像を設定集へ追加',
    library: '素材から別角度を追加',
    primary: '開始フレーム基準',
    makePrimary: '開始基準に設定',
    remove: '削除',
    needs:
      '人物名、設定、参照画像1枚以上が必要です。正面、左右斜め、左右横顔、全身を同じ衣装と単純な照明で用意するのがおすすめです。',
  },
} as const;

const viewLabels = {
  'zh-TW': {
    front: '正面',
    left_three_quarter: '左 3/4',
    right_three_quarter: '右 3/4',
    left_profile: '左側面',
    right_profile: '右側面',
    back: '背面',
    full_body: '全身',
  },
  en: {
    front: 'Front',
    left_three_quarter: 'Left 3/4',
    right_three_quarter: 'Right 3/4',
    left_profile: 'Left profile',
    right_profile: 'Right profile',
    back: 'Back',
    full_body: 'Full body',
  },
  ja: {
    front: '正面',
    left_three_quarter: '左斜め',
    right_three_quarter: '右斜め',
    left_profile: '左横顔',
    right_profile: '右横顔',
    back: '背面',
    full_body: '全身',
  },
} as const;

export function CharacterLock({
  locale,
  value,
  current,
  primaryId,
  onChange,
  onPrimary,
}: {
  locale: keyof typeof copy;
  value: CharacterDraft;
  current: Asset | null;
  primaryId?: string;
  onChange: (value: CharacterDraft) => void;
  onPrimary: (asset: Asset) => void;
}) {
  const text = copy[locale];
  const [assets, setAssets] = useState<Asset[]>([]);
  useEffect(() => {
    const abort = new AbortController();
    serviceFetch('/api/v1/assets', { signal: abort.signal })
      .then(async (response) =>
        response.ok
          ? (response.json() as Promise<{ assets: Asset[] }>)
          : Promise.reject(),
      )
      .then((result) =>
        setAssets(result.assets.filter((asset) => asset.kind === 'image')),
      )
      .catch(() => undefined);
    return () => abort.abort();
  }, []);
  const addAsset = (asset?: Asset | null) => {
    if (
      !asset ||
      value.references.some((item) => item.asset.id === asset.id) ||
      value.references.length >= Object.keys(viewLabels[locale]).length
    )
      return;
    const used = new Set(value.references.map((item) => item.view));
    const view =
      (Object.keys(viewLabels[locale]) as CharacterView[]).find(
        (item) => !used.has(item),
      ) || 'front';
    onChange({
      ...value,
      enabled: true,
      references: [...value.references, { asset, view }],
    });
  };
  return (
    <section className="space-y-4 border border-[#bfe8e3] bg-[#f5fcfb] p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="size-4 text-[#11786f]" />
          <h3 className="text-xs font-bold">{text.title}</h3>
        </div>
        <Switch
          checked={value.enabled}
          onCheckedChange={(enabled) => onChange({ ...value, enabled })}
        />
      </div>
      <p className="text-[10px] leading-5 text-muted-foreground">{text.note}</p>
      <label className="block text-[10px] font-bold">
        {text.name}
        <Input
          className="mt-2 rounded-none bg-white"
          maxLength={80}
          value={value.name}
          onChange={(event) => onChange({ ...value, name: event.target.value })}
        />
      </label>
      <label className="block text-[10px] font-bold">
        {text.description}
        <Textarea
          className="mt-2 min-h-24 rounded-none bg-white text-xs"
          maxLength={1200}
          placeholder={text.placeholder}
          value={value.description}
          onChange={(event) =>
            onChange({ ...value, description: event.target.value })
          }
        />
      </label>
      <Button
        type="button"
        variant="outline"
        className="w-full rounded-none text-[10px]"
        disabled={
          !current ||
          value.references.some((item) => item.asset.id === current.id) ||
          value.references.length >= Object.keys(viewLabels[locale]).length
        }
        onClick={() => addAsset(current)}
      >
        {text.add}
      </Button>
      <label className="block text-[10px] font-bold">
        {text.library}
        <Select
          value="choose"
          onValueChange={(id) =>
            addAsset(assets.find((asset) => asset.id === id))
          }
        >
          <SelectTrigger className="mt-2 w-full bg-white">
            <SelectValue placeholder={text.library} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="choose" disabled>
              {text.library}
            </SelectItem>
            {assets
              .filter(
                (asset) =>
                  !value.references.some((item) => item.asset.id === asset.id),
              )
              .map((asset) => (
                <SelectItem key={asset.id} value={asset.id}>
                  {asset.name}
                </SelectItem>
              ))}
          </SelectContent>
        </Select>
      </label>
      <div className="space-y-2">
        {value.references.map((item, index) => {
          const used = new Set(
            value.references
              .filter((_, i) => i !== index)
              .map((reference) => reference.view),
          );
          return (
            <article
              key={item.asset.id}
              className="grid grid-cols-[64px_minmax(0,1fr)_auto] gap-3 border border-border bg-white p-2"
            >
              <img
                src={item.asset.url}
                alt={item.asset.name}
                className="h-16 w-16 object-contain"
              />
              <div className="min-w-0">
                <p className="truncate text-[10px] font-bold">
                  {item.asset.name}
                </p>
                <Select
                  value={item.view}
                  onValueChange={(view) =>
                    view &&
                    onChange({
                      ...value,
                      references: value.references.map((reference, i) =>
                        i === index
                          ? { ...reference, view: view as CharacterView }
                          : reference,
                      ),
                    })
                  }
                >
                  <SelectTrigger className="mt-2 h-8 w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(
                      Object.entries(viewLabels[locale]) as [
                        CharacterView,
                        string,
                      ][]
                    )
                      .filter(([view]) => view === item.view || !used.has(view))
                      .map(([view, label]) => (
                        <SelectItem key={view} value={view}>
                          {label}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col items-end justify-between">
                {primaryId === item.asset.id ? (
                  <span className="text-[9px] font-bold text-[#11786f]">
                    {text.primary}
                  </span>
                ) : (
                  <button
                    type="button"
                    className="text-[9px] text-[#e85578] underline"
                    onClick={() => onPrimary(item.asset)}
                  >
                    {text.makePrimary}
                  </button>
                )}
                <button
                  type="button"
                  aria-label={text.remove}
                  disabled={primaryId === item.asset.id}
                  className="disabled:opacity-25"
                  onClick={() =>
                    onChange({
                      ...value,
                      references: value.references.filter(
                        (reference) => reference.asset.id !== item.asset.id,
                      ),
                    })
                  }
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            </article>
          );
        })}
      </div>
      <p className="text-[10px] leading-5 text-muted-foreground">
        {text.needs}
      </p>
    </section>
  );
}
