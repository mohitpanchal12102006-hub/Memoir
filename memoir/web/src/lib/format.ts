export const plural = (n: number, one: string, many?: string) => `${n.toLocaleString()} ${n === 1 ? one : many ?? one + 's'}`;

export function fmtBytes(n: number): string {
  if (!isFinite(n) || n <= 0) return '0 B';
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n >= 100 || i === 0 ? n.toFixed(0) : n.toFixed(1)} ${u[i]}`;
}

export function fmtDay(d: string): string {
  const [y, m, dd] = d.split('-').map(Number);
  if (!y || !m || !dd) return d;
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(
    new Date(Date.UTC(y, m - 1, dd)),
  );
}

export function fmtDateTime(v: string | null | undefined): string {
  if (!v) return 'No date';
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(v);
  if (!m) return v;
  const day = fmtDay(`${m[1]}-${m[2]}-${m[3]}`);
  return `${day}, ${m[4]}:${m[5]}`;
}

export function fmtEta(sec: number | null | undefined): string {
  if (sec === null || sec === undefined || !isFinite(sec)) return '';
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `about ${Math.round(sec / 60)} min`;
  return `about ${(sec / 3600).toFixed(1)} h`;
}

export function basename(p: string): string {
  const parts = p.split(/[\\/]/);
  return parts[parts.length - 1] || p;
}

export const REASON_LABEL: Record<string, string> = {
  missing: 'No date found',
  placeholder_date: 'Placeholder date (for example 1970)',
  exif_vs_sidecar: 'Embedded date and Google date differ',
  filename_vs_exif: 'Filename date differs from embedded date',
  forward_date: 'WhatsApp name date differs from capture date',
  corrupt: 'File is damaged or unreadable',
  tz_only: 'Likely a timezone difference',
};

export function isoDate(v: string | null | undefined): string {
  return v ? v.slice(0, 10) : '';
}
export function isoTime(v: string | null | undefined): string {
  return v ? v.slice(11, 19) : '';
}
