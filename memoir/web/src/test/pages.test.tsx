import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { AppProvider } from '../state';

const source = (id: number, no: number | null, state = 'indexed') => ({
  id, kind: 'zip', path: `/data/takeout-20231001T000000Z-00${no}.zip`, size: 50e9, location: 'external', part_group: '20231001T000000Z',
  part_no: no, state, entries: 100, error: null, media_count: 100, scanned_count: 100, online: true,
});
const item = (id: number, status = 'ok') => ({
  id, name: `IMG_${id}.jpg`, folder: 'Photos from 2023', kind: 'image', ext: 'jpg', size: 1000, status, date: '2023-05-14T11:02:00',
  date_source: 'exif', reasons: status === 'review' ? ['missing'] : [], live: false, width: 64, height: 48,
});
const detail = { ...item(7, 'review'), candidates: [{ source: 'sidecar', tag: 'photoTakenTime', value: '2023-05-14T05:32:00', tz: 'Z' }],
  resolved: null, manual: null, source_path: '/data/a.zip', inner: 'Takeout/x.jpg', sha256: 'abc', has_sidecar: true, error: null, live_video: null };

const routes: Record<string, unknown> = {
  '/api/health': { version: '1', exiftool: true, ffmpeg: true, heif: true, platform: 'Linux', home: '/h', sep: '/' },
  '/api/summary': { total: 120, images: 100, raws: 5, videos: 15, review: 3, ok: 117, orphan_sidecars: 0, pending_scan: 0, sources: 2, source_bytes: 1e11, unindexed_sources: 0, similar_ready: false },
  '/api/sources': [source(1, 1), source(2, 3)],
  '/api/takeout-sets': [{ group: '20231001T000000Z', parts: [source(1, 1), source(2, 3)], count: 2, size: 1e11, highest_part: 3, missing: [2] }],
  '/api/review/counts': { all: 3, missing: 2, mismatch: 1, corrupt: 0, orphans: 0 },
  '/api/duplicates/summary': { exact: { groups: 1, extra: 1, reclaimable: 2048 }, similar: { groups: 0, extra: 0, reclaimable: 0 },
    folders: [{ folder: 'Goa trip', files: 1, bytes: 2048, excluded: 0 }], keep_folders: [{ folder: 'Photos from 2023', files: 1 }] },
  '/api/jobs': [],
  '/api/exports': [],
  '/api/timeline/days': { days: [{ d: '2023-05-14', c: 2 }], total: 2 },
  '/api/media': { items: [item(1), item(2, 'review')], offset: 0 },
  '/api/review': { items: [item(7, 'review')], offset: 0 },
  '/api/media/7': detail,
  '/api/media/7/neighbors': [],
  '/api/review/orphans': [],
  '/api/duplicates': { total: 1, groups: [{ id: 'e-1', kind: 'exact', reclaimable: 2048, members: [
    { id: 1, name: 'IMG_1.jpg', folder: 'Photos from 2023', size: 2048, width: 64, height: 48, has_exif: true, source: 'a.zip', source_path: '/a.zip', inner: 'x', status: 'ok', excluded: false, role: 'keep', suggested: true },
    { id: 2, name: 'IMG_1.jpg', folder: 'Goa trip', size: 2048, width: 64, height: 48, has_exif: true, source: 'a.zip', source_path: '/a.zip', inner: 'y', status: 'ok', excluded: false, role: 'remove', suggested: false }] }] },
};

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = url.split('?')[0];
    if (path in routes) return new Response(JSON.stringify(routes[path]), { status: 200 });
    return new Response(JSON.stringify({ detail: `no mock for ${path}` }), { status: 404 });
  }));
  localStorage.clear();
});
afterEach(cleanup);

const mount = (path: string) => render(<AppProvider><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></AppProvider>);

describe('pages render against the API', () => {
  it('Upload shows the Takeout set with the missing part', async () => {
    mount('/');
    expect(await screen.findByText(/Keep every moment/)).toBeTruthy();
    expect(await screen.findByText(/Part 2 is missing/)).toBeTruthy();
    expect(screen.getByText('Choose ZIP parts or folders')).toBeTruthy();
    await waitFor(() => expect(screen.getAllByText('External drive').length).toBeGreaterThan(0));
    expect(screen.getByText('Open timeline')).toBeTruthy();
  });

  it('Nav shows live counts', async () => {
    mount('/');
    expect(await screen.findByText('Needs review')).toBeTruthy();
    await waitFor(() => expect(document.querySelector('.nv b')?.textContent).toBe('3'));
  });

  it('Timeline renders its banner and toolbar', async () => {
    mount('/timeline');
    expect(await screen.findByText('A quiet record of every day.')).toBeTruthy();
    expect(screen.getByLabelText('Search file names')).toBeTruthy();
    expect(screen.getByText('Needs review only')).toBeTruthy();
  });

  it('Review loads the workspace and sends a fix', async () => {
    mount('/review?focus=7');
    expect(await screen.findByText('IMG_7.jpg', { selector: '.serif' })).toBeTruthy();
    expect(await screen.findByText('Google sidecar (UTC)')).toBeTruthy();
    const f = fetch as unknown as ReturnType<typeof vi.fn>;
    routes['/api/review/resolve'] = { updated: 1, batch: 1 };
    fireEvent.change(screen.getByLabelText('Date'), { target: { value: '2023-05-14' } });
    fireEvent.click(screen.getByText('Apply'));
    await waitFor(() => {
      const call = f.mock.calls.find((c) => String(c[0]).includes('/api/review/resolve'));
      expect(call).toBeTruthy();
      expect(JSON.parse((call![1] as RequestInit).body as string)).toMatchObject({ ids: [7], mode: 'set', date: '2023-05-14' });
    });
  });

  it('Duplicates shows which folder a copy is removed from, and asks before applying', async () => {
    mount('/duplicates');
    expect(await screen.findByText('Removing from: Goa trip')).toBeTruthy();
    expect(screen.getByText('Delete from source')).toBeTruthy();
    routes['/api/duplicates/plan'] = { files: 1, bytes: 2048, folders: [{ folder: 'Goa trip', removing: 1, bytes: 2048 }] };
    fireEvent.click(screen.getByText('Review removal plan'));
    expect(await screen.findByText('Total: 1 file, 2.0 KB')).toBeTruthy();
    const f = fetch as unknown as ReturnType<typeof vi.fn>;
    expect(f.mock.calls.some((c) => String(c[0]).includes('/api/duplicates/apply'))).toBe(false);
  });

  it('Export dialog walks through the steps and shows preflight problems', async () => {
    mount('/');
    await screen.findByText(/Keep every moment/);
    fireEvent.click(screen.getByText('Export'));
    fireEvent.click(await screen.findByText('Next'));
    expect(await screen.findByText('Choose a destination first.')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Destination folder'), { target: { value: '/out' } });
    fireEvent.click(screen.getByText('Next'));
    fireEvent.change(await screen.findByPlaceholderText('+05:30'), { target: { value: 'IST' } });
    fireEvent.click(screen.getByText('Check before exporting'));
    expect(await screen.findByText('Timezone must look like +05:30 or -08:00.')).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText('+05:30'), { target: { value: '+05:30' } });
    routes['/api/export/preflight'] = { ok: false, files: 5, bytes: 1000, free: 10, filesystem: 'vfat', same_drive: false, skipped: { needs_review: 2 },
      warnings: ['The destination is formatted as FAT32.'], errors: ['Not enough free space on the destination drive.'] };
    fireEvent.click(screen.getByText('Check before exporting'));
    expect(await screen.findByText('Not enough free space on the destination drive.')).toBeTruthy();
    expect((screen.getByText('Start export') as HTMLButtonElement).disabled).toBe(true);
  });
});
