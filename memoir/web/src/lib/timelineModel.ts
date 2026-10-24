export type Day = { d: string; c: number };
export type Row =
  | { type: 'head'; day: string; count: number; key: string }
  | { type: 'tiles'; day: string; start: number; count: number; key: string };

export const PAGE = 200;

/** Flatten the day list into virtual rows: one heading row and then rows of `cols` tiles. */
export function buildRows(days: Day[], cols: number) {
  const rows: Row[] = [];
  const firstRowOfYear: Record<string, number> = {};
  const c = Math.max(1, cols);
  let offset = 0;
  for (const day of days) {
    const year = day.d.slice(0, 4);
    if (!(year in firstRowOfYear)) firstRowOfYear[year] = rows.length;
    rows.push({ type: 'head', day: day.d, count: day.c, key: `h${day.d}` });
    for (let r = 0; r * c < day.c; r++) {
      rows.push({ type: 'tiles', day: day.d, start: offset + r * c, count: Math.min(c, day.c - r * c), key: `t${day.d}-${r}` });
    }
    offset += day.c;
  }
  return { rows, firstRowOfYear, total: offset };
}

export function pagesFor(start: number, count: number): number[] {
  const first = Math.floor(start / PAGE);
  const last = Math.floor((start + Math.max(count, 1) - 1) / PAGE);
  const out: number[] = [];
  for (let p = first; p <= last; p++) out.push(p);
  return out;
}
