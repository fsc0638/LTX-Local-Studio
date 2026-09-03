export type LrcRow = { time: number; text: string };

const stamp = /\[(\d{1,3}):([0-5]\d)(?:[.:](\d{1,3}))?\]/g;

export function parseLrcRows(source: string): LrcRow[] {
  const rows: LrcRow[] = [];
  for (const raw of source.replace(/^\uFEFF/, '').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || /^\[(ar|ti|al|by|re|ve|length|offset):/i.test(line)) continue;
    const matches = [...line.matchAll(stamp)];
    const text = line.replace(stamp, '').trim();
    if (!matches.length || !text) continue;
    for (const match of matches) {
      const fraction = match[3] ? Number(`0.${match[3]}`) : 0;
      rows.push({
        time: Number(match[1]) * 60 + Number(match[2]) + fraction,
        text,
      });
    }
  }
  return rows.sort((a, b) => a.time - b.time);
}

export function formatLrcRows(rows: LrcRow[]): string {
  return [...rows]
    .sort((a, b) => a.time - b.time)
    .map((row) => {
      const safe = Math.max(0, Math.round(row.time * 1000) / 1000);
      const minutes = Math.floor(safe / 60);
      const seconds = (safe - minutes * 60).toFixed(3).padStart(6, '0');
      return `[${String(minutes).padStart(2, '0')}:${seconds}]${row.text}`;
    })
    .join('\n');
}

export function displayedLrcTime(
  rowTime: number,
  audioStart: number,
  timebase: string,
): number {
  return (
    Math.round((rowTime - (timebase === 'music' ? audioStart : 0)) * 1000) /
    1000
  );
}

export function storedLrcTime(
  displayedTime: number,
  audioStart: number,
  timebase: string,
): number {
  return (
    Math.round(
      (displayedTime + (timebase === 'music' ? audioStart : 0)) * 1000,
    ) / 1000
  );
}
