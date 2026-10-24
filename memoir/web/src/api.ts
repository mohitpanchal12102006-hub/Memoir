export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function detailText(d: unknown): string {
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) {
    return d.map((x) => (x && typeof x === 'object' && 'msg' in x ? String((x as { msg: unknown }).msg) : String(x))).join(' ');
  }
  if (d && typeof d === 'object') {
    const o = d as { errors?: unknown };
    if (Array.isArray(o.errors)) return o.errors.map(String).join(' ');
  }
  return 'Something went wrong.';
}

type Params = Record<string, string | number | boolean | undefined | null>;

async function request<T>(method: string, path: string, body?: unknown, params?: Params): Promise<T> {
  let url = path;
  if (params) {
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') sp.set(k, String(v));
    }
    const s = sp.toString();
    if (s) url += (url.includes('?') ? '&' : '?') + s;
  }
  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError('Cannot reach the Memoir engine. Is it still running?', 0);
  }
  if (!res.ok) {
    let d: unknown = res.statusText;
    try {
      d = ((await res.json()) as { detail?: unknown }).detail;
    } catch {
      /* keep status text */
    }
    throw new ApiError(detailText(d), res.status);
  }
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string, params?: Params) => request<T>('GET', path, undefined, params),
  post: <T>(path: string, body: unknown = {}) => request<T>('POST', path, body),
  del: <T>(path: string) => request<T>('DELETE', path),
};

// ---------------------------------------------------------------- types
export type Health = { version: string; exiftool: boolean; ffmpeg: boolean; heif: boolean; platform: string; home: string; sep: string };

export type Summary = {
  total: number; images: number; raws: number; videos: number; review: number; ok: number; orphan_sidecars: number;
  pending_scan: number; sources: number; source_bytes: number; unindexed_sources: number; similar_ready: boolean;
};

export type Source = {
  id: number; kind: 'zip' | 'folder'; path: string; size: number; location: 'internal' | 'external';
  part_group: string | null; part_no: number | null; state: string; entries: number; error: string | null;
  media_count: number; scanned_count: number; online: boolean;
};

export type TakeoutSet = { group: string; parts: Source[]; count: number; size: number; highest_part: number; missing: number[] };

export type Job = {
  id: string; type: string; state: 'queued' | 'running' | 'paused' | 'done' | 'error' | 'cancelled'; stage: string; message: string;
  done: number; total: number; bytes_done: number; bytes_total: number; mb_per_sec: number; eta_sec: number | null;
  error: string | null; result: Record<string, unknown>; params: Record<string, unknown>;
};

export type Item = {
  id: number; name: string; folder: string; kind: 'image' | 'raw' | 'video'; ext: string; size: number; status: string;
  date: string | null; date_source: string | null; reasons: string[]; live: boolean; width: number | null; height: number | null;
};

export type Candidate = { source: string; tag: string; value: string | null; tz: string | null; bad?: boolean; approx?: boolean; raw?: string };

export type Detail = Item & {
  candidates: Candidate[]; resolved: { value: string; tz: string | null; source: string; tag: string } | null;
  manual: { value: string; tz: string | null } | null; source_path: string; inner: string; sha256: string | null;
  has_sidecar: boolean; error: string | null; live_video: { id: number; name: string; ext: string } | null;
};

export type ReviewCounts = { all: number; missing: number; mismatch: number; corrupt: number; orphans: number };

export type DupMember = {
  id: number; name: string; folder: string; size: number; width: number | null; height: number | null; has_exif: boolean;
  source: string; source_path: string; inner: string; status: string; excluded: boolean; role: 'keep' | 'remove'; suggested: boolean;
};
export type DupGroup = { id: string; kind: 'exact' | 'similar'; reclaimable: number; members: DupMember[] };
export type DupSummary = {
  exact: { groups: number; extra: number; reclaimable: number };
  similar: { groups: number; extra: number; reclaimable: number };
  folders: { folder: string; files: number; bytes: number; excluded: number }[];
  keep_folders: { folder: string; files: number }[];
};

export type FsEntry = { name: string; path: string; type: 'dir' | 'zip'; size?: number };
export type FsListing = { path: string; parent: string | null; entries: FsEntry[] };

export type ExportOptions = {
  destination: { type: 'folder' | 'zip'; path: string };
  structure: 'flat' | 'year' | 'year-month';
  prefix: boolean;
  include_review: boolean;
  unresolved: 'skip' | 'folder';
  sidecar_tz: string | null;
  date_from: string | null;
  date_to: string | null;
};

export type Preflight = {
  ok: boolean; files: number; bytes: number; free: number; filesystem: string; same_drive: boolean;
  skipped: { needs_review?: number; no_date?: number; removed_duplicates?: number };
  warnings: string[]; errors: string[];
};

export const previewUrl = (id: number, w = 480) => `/api/media/${id}/preview?w=${w}`;
