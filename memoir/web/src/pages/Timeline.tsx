import { useWindowVirtualizer } from '@tanstack/react-virtual';
import { useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, previewUrl, type Detail, type Item } from '../api';
import { Atmosphere, HeroImage } from '../components/HeroImage';
import { buildRows, PAGE, pagesFor, type Day } from '../lib/timelineModel';
import { fmtBytes, fmtDateTime, fmtDay, REASON_LABEL } from '../lib/format';
import { useApp } from '../state';

const GAP = 14;
const MIN_TILE = 150;
type Filters = { kind: string; q: string; fmt: string; source: string; status: string };

function useItemStore(filters: Filters) {
  const key = JSON.stringify(filters);
  const store = useMemo(() => ({ cache: new Map<number, Item[]>(), inflight: new Set<number>(), key }), [key]);
  const [, bump] = useReducer((x: number) => x + 1, 0);
  const ensure = useCallback((pages: number[]) => {
    for (const p of pages) {
      if (store.cache.has(p) || store.inflight.has(p)) continue;
      store.inflight.add(p);
      api.get<{ items: Item[] }>('/api/media', { offset: p * PAGE, limit: PAGE, ...filters })
        .then((r) => { store.cache.set(p, r.items); })
        .catch(() => undefined)
        .finally(() => { store.inflight.delete(p); bump(); });
    }
  }, [store, filters]);
  const get = useCallback((i: number): Item | undefined => store.cache.get(Math.floor(i / PAGE))?.[i % PAGE], [store]);
  return { ensure, get, store };
}

function Viewer({ item, onClose }: { item: Item; onClose: () => void }) {
  const [d, setD] = useState<Detail | null>(null);
  useEffect(() => {
    let live = true;
    api.get<Detail>(`/api/media/${item.id}`).then((x) => live && setD(x)).catch(() => undefined);
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', k);
    return () => { live = false; window.removeEventListener('keydown', k); };
  }, [item.id, onClose]);
  return (
    <aside className="drawer" role="dialog" aria-label={`Details for ${item.name}`}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <div className="serif" style={{ fontSize: 28, overflowWrap: 'anywhere' }}>{item.name}</div>
        <button className="btn sm" onClick={onClose}>Close</button>
      </div>
      <img className="big" src={previewUrl(item.id, 1600)} alt={`Preview of ${item.name}`} style={{ marginTop: 16 }} />
      <dl className="kv">
        <dt>Date</dt><dd>{fmtDateTime(item.date)}{item.date_source ? ` (from ${item.date_source})` : ''}</dd>
        <dt>Folder</dt><dd>{item.folder}</dd>
        <dt>Size</dt><dd>{fmtBytes(item.size)}{item.width ? `, ${item.width}×${item.height}` : ''}</dd>
        {d && <><dt>Source</dt><dd>{d.source_path}</dd><dt>Inside</dt><dd>{d.inner}</dd></>}
        {d?.live_video && <><dt>Live Photo</dt><dd>Paired with {d.live_video.name}</dd></>}
        {item.reasons.length > 0 && <><dt>Notes</dt><dd>{item.reasons.map((r) => REASON_LABEL[r] ?? r).join('. ')}</dd></>}
      </dl>
      {d && d.candidates.length > 0 && (
        <table className="tbl"><thead><tr><th>Where the date came from</th><th>Value</th></tr></thead>
          <tbody>{d.candidates.map((c, i) => <tr key={i}><td>{c.tag}</td><td>{c.value ? fmtDateTime(c.value) : 'unreadable'}{c.tz ? ` ${c.tz}` : ''}{c.bad ? ' (ignored)' : ''}</td></tr>)}</tbody></table>
      )}
      {item.status === 'review' && <p><Link className="btn pri" to={`/review?focus=${item.id}`}>Fix this date</Link></p>}
    </aside>
  );
}

export function Timeline() {
  const { summary, sources } = useApp();
  const [q, setQ] = useState('');
  const [dq, setDq] = useState('');
  const [kind, setKind] = useState('');
  const [fmt, setFmt] = useState('');
  const [source, setSource] = useState('');
  const [onlyReview, setOnlyReview] = useState(false);
  const [days, setDays] = useState<Day[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [width, setWidth] = useState(1000);
  const [margin, setMargin] = useState(0);
  const [open, setOpen] = useState<Item | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => { const t = window.setTimeout(() => setDq(q), 300); return () => window.clearTimeout(t); }, [q]);
  const filters = useMemo<Filters>(() => ({ kind, q: dq, fmt, source, status: onlyReview ? 'review' : '' }), [kind, dq, fmt, source, onlyReview]);
  const { ensure, get } = useItemStore(filters);

  useEffect(() => {
    let live = true;
    api.get<{ days: Day[]; total: number }>('/api/timeline/days', filters).then((r) => { if (live) { setDays(r.days); setLoaded(true); } }).catch(() => live && setLoaded(true));
    return () => { live = false; };
  }, [filters, summary?.total]);

  useLayoutEffect(() => {
    const el = listRef.current;
    if (!el) return;
    const measure = () => { setWidth(el.clientWidth || 1000); setMargin(el.getBoundingClientRect().top + window.scrollY); };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [loaded]);

  const cols = Math.max(2, Math.floor((width + GAP) / (MIN_TILE + GAP)));
  const tileW = (width - GAP * (cols - 1)) / cols;
  const tileRow = tileW * (4 / 3) + GAP;
  const model = useMemo(() => buildRows(days, cols), [days, cols]);

  const virt = useWindowVirtualizer({
    count: model.rows.length,
    estimateSize: (i) => (model.rows[i]?.type === 'head' ? 76 : tileRow),
    overscan: 6,
    scrollMargin: margin,
    getItemKey: (i) => model.rows[i]?.key ?? i,
  });
  useEffect(() => { virt.measure(); }, [virt, model, tileRow]);

  const vItems = virt.getVirtualItems();
  const visKey = vItems.length ? `${vItems[0].index}-${vItems[vItems.length - 1].index}` : '';
  useEffect(() => {
    const pages = new Set<number>();
    for (const v of vItems) {
      const r = model.rows[v.index];
      if (r && r.type === 'tiles') pagesFor(r.start, r.count).forEach((p) => pages.add(p));
    }
    ensure([...pages]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visKey, model, ensure]);

  const years = Object.keys(model.firstRowOfYear).sort().reverse();
  const firstRow = vItems.length ? model.rows[vItems[0].index] : undefined;
  const activeYear = firstRow ? ('day' in firstRow ? firstRow.day.slice(0, 4) : '') : '';
  const exts = ['jpg', 'heic', 'png', 'webp', 'dng', 'cr2', 'nef', 'arw', 'mp4', 'mov', 'mkv'];
  const noData = !summary || summary.total === 0;

  return (
    <>
      <HeroImage name="banner" scene="p" alt="A quiet mountain panorama" className="tl-banner" style={{ height: 200, marginTop: 28 }}>
        <Atmosphere sunLeft="calc(68% - 70px)" sunTop={6} />
        <div className="over"><h1>Timeline</h1><div className="sub">A quiet record of every day.</div></div>
      </HeroImage>

      <div className="toolbar">
        <input className="fld" aria-label="Search file names" placeholder="Search file names" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 240 }} />
        {([['', 'All'], ['image', 'Photos'], ['raw', 'RAW'], ['video', 'Video']] as const).map(([v, l]) => (
          <button key={v} className={`chip${kind === v ? ' on' : ''}`} onClick={() => setKind(v)} aria-pressed={kind === v}>{l}</button>
        ))}
        <select className="fld" aria-label="Format" value={fmt} onChange={(e) => setFmt(e.target.value)}>
          <option value="">Any format</option>{exts.map((x) => <option key={x} value={x}>{x.toUpperCase()}</option>)}
        </select>
        <select className="fld" aria-label="Source" value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">All sources</option>
          {sources.map((s) => <option key={s.id} value={s.id}>{s.path.split(/[\\/]/).pop()}</option>)}
        </select>
        <button className={`chip${onlyReview ? ' on' : ''}`} onClick={() => setOnlyReview(!onlyReview)} aria-pressed={onlyReview}>Needs review only</button>
        <span className="m" style={{ marginLeft: 'auto' }}>{model.total.toLocaleString()} items</span>
      </div>
      <div className="hr" />

      {loaded && model.total === 0 ? (
        <div className="empty">
          <div className="serif">{noData ? 'Nothing here yet.' : 'No matches.'}</div>
          <p className="m">{noData ? 'Add your Takeout on the Upload page and run the scan. Your photos will appear here in order.' : 'Try a different filter.'}</p>
          {noData && <Link className="btn pri" to="/">Go to Upload</Link>}
        </div>
      ) : (
        <div className="tl">
          <div ref={listRef} style={{ position: 'relative', height: virt.getTotalSize(), minHeight: 200 }}>
            {vItems.map((v) => {
              const r = model.rows[v.index];
              if (!r) return null;
              const style = { position: 'absolute' as const, top: 0, left: 0, width: '100%', transform: `translateY(${v.start - margin}px)` };
              if (r.type === 'head') {
                return (
                  <div key={r.key} style={style}>
                    <div className="day-head"><span className="d">{fmtDay(r.day)}</span><span className="m">{r.count} {r.count === 1 ? 'item' : 'items'}</span></div>
                  </div>
                );
              }
              return (
                <div key={r.key} style={style}>
                  <div className="tgrid" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
                    {Array.from({ length: r.count }, (_, k) => {
                      const it = get(r.start + k);
                      if (!it) return <div key={k} className="tile skel" />;
                      return (
                        <button key={it.id} className="tile" onClick={() => setOpen(it)} aria-label={`${it.name}, ${fmtDateTime(it.date)}`}>
                          <img src={previewUrl(it.id, 480)} alt="" loading="lazy" />
                          <span className="fmt">{it.live ? 'LIVE' : it.ext}</span>
                          {it.status === 'review' && <span className="flag">REVIEW</span>}
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
          <nav className="rail" aria-label="Jump to year">
            {years.map((y) => (
              <button key={y} className={y === activeYear ? 'on' : ''} onClick={() => virt.scrollToIndex(model.firstRowOfYear[y], { align: 'start' })}>{y}</button>
            ))}
          </nav>
        </div>
      )}
      {open && <Viewer item={open} onClose={() => setOpen(null)} />}
    </>
  );
}
