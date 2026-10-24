import { describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '../api';
import { fmtBytes, fmtDateTime, fmtDay, fmtEta, isoDate, isoTime } from '../lib/format';
import { buildRows, PAGE, pagesFor } from '../lib/timelineModel';

describe('format', () => {
  it('formats sizes', () => {
    expect(fmtBytes(0)).toBe('0 B');
    expect(fmtBytes(1536)).toBe('1.5 KB');
    expect(fmtBytes(214 * 1024 ** 3)).toBe('214 GB');
  });
  it('formats dates without timezone shifts', () => {
    expect(fmtDay('2024-03-14')).toBe('14 March 2024');
    expect(fmtDateTime('2023-05-14T11:02:00')).toBe('14 May 2023, 11:02');
    expect(fmtDateTime(null)).toBe('No date');
    expect(isoDate('2023-05-14T11:02:00')).toBe('2023-05-14');
    expect(isoTime('2023-05-14T11:02:00')).toBe('11:02:00');
  });
  it('formats ETA', () => {
    expect(fmtEta(30)).toBe('30s');
    expect(fmtEta(600)).toBe('about 10 min');
    expect(fmtEta(null)).toBe('');
  });
});

describe('timeline model', () => {
  const days = [{ d: '2024-03-14', c: 7 }, { d: '2024-03-13', c: 2 }, { d: '2023-01-01', c: 1 }];
  it('creates a heading and rows of tiles per day', () => {
    const m = buildRows(days, 3);
    expect(m.total).toBe(10);
    expect(m.rows.map((r) => r.type)).toEqual(['head', 'tiles', 'tiles', 'tiles', 'head', 'tiles', 'head', 'tiles']);
    const tiles = m.rows.filter((r) => r.type === 'tiles') as { start: number; count: number }[];
    expect(tiles.map((t) => [t.start, t.count])).toEqual([[0, 3], [3, 3], [6, 1], [7, 2], [9, 1]]);
    expect(m.firstRowOfYear).toEqual({ '2024': 0, '2023': 6 });
  });
  it('maps rows to API pages', () => {
    expect(pagesFor(0, 3)).toEqual([0]);
    expect(pagesFor(PAGE - 1, 3)).toEqual([0, 1]);
  });
  it('handles an empty library', () => {
    expect(buildRows([], 4)).toEqual({ rows: [], firstRowOfYear: {}, total: 0 });
  });
});

describe('api client', () => {
  it('turns FastAPI errors into readable messages', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: { errors: ['Not enough free space.', 'Other.'] } }), { status: 400 })));
    await expect(api.post('/x', {})).rejects.toMatchObject({ message: 'Not enough free space. Other.', status: 400 });
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: [{ msg: 'bad value' }] }), { status: 422 })));
    await expect(api.get('/x')).rejects.toBeInstanceOf(ApiError);
  });
  it('explains when the engine is not running', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('network'); }));
    await expect(api.get('/x')).rejects.toMatchObject({ status: 0 });
  });
  it('sends query parameters and skips empty ones', async () => {
    const f = vi.fn(async (_u: string) => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', f);
    await api.get('/api/media', { offset: 0, q: '', kind: 'video' });
    expect(f.mock.calls[0][0]).toBe('/api/media?offset=0&kind=video');
  });
});
