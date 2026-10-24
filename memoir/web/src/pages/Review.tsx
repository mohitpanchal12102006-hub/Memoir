import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, previewUrl, type Detail, type Item } from '../api';
import { fmtDateTime, isoDate, isoTime, REASON_LABEL } from '../lib/format';
import { useApp } from '../state';

type Tab = 'all' | 'missing' | 'mismatch' | 'corrupt' | 'orphans';
type Orphan = { id: number; name: string; folder: string; source: string };
type Neighbor = { id: number; name: string; date: string | null };
const TABS: [Tab, string][] = [['all', 'All'], ['missing', 'Missing'], ['mismatch', 'Mismatch'], ['corrupt', 'Corrupt'], ['orphans', 'Orphan sidecars']];
const SRC_LABEL: Record<string, string> = { sidecar: 'Google sidecar (UTC)', filename: 'File name', exif: 'Embedded' };

export function Review() {
  const { review, refresh, fail, toast } = useApp();
  const [params] = useSearchParams();
  const [tab, setTab] = useState<Tab>('all');
  const [items, setItems] = useState<Item[]>([]);
  const [more, setMore] = useState(false);
  const [orphans, setOrphans] = useState<Orphan[]>([]);
  const [version, setVersion] = useState(0);
  const [activeId, setActiveId] = useState<number | null>(() => (params.get('focus') ? Number(params.get('focus')) : null));
  const [detail, setDetail] = useState<Detail | null>(null);
  const [nbrs, setNbrs] = useState<Neighbor[]>([]);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [date, setDate] = useState('');
  const [time, setTime] = useState('');
  const [tz, setTz] = useState('');
  const [bMode, setBMode] = useState<'set' | 'shift' | 'sequence'>('set');
  const [bTarget, setBTarget] = useState<'selected' | 'filter'>('selected');
  const [bDate, setBDate] = useState('');
  const [bTime, setBTime] = useState('00:00:00');
  const [bTz, setBTz] = useState('');
  const [bMin, setBMin] = useState('60');
  const [bStep, setBStep] = useState('1');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    if (tab === 'orphans') {
      api.get<Orphan[]>('/api/review/orphans').then((r) => live && setOrphans(r)).catch(fail);
    } else {
      api.get<{ items: Item[] }>('/api/review', { reason: tab === 'all' ? undefined : tab, offset: 0, limit: 100 })
        .then((r) => { if (live) { setItems(r.items); setMore(r.items.length === 100); } }).catch(fail);
    }
    return () => { live = false; };
  }, [tab, version, fail]);

  const loadMore = async () => {
    try {
      const r = await api.get<{ items: Item[] }>('/api/review', { reason: tab === 'all' ? undefined : tab, offset: items.length, limit: 100 });
      setItems((p) => [...p, ...r.items]);
      setMore(r.items.length === 100);
    } catch (e) { fail(e); }
  };

  useEffect(() => {
    if (activeId === null && items.length > 0 && !params.get('focus')) setActiveId(items[0].id);
  }, [items, activeId, params]);

  useEffect(() => {
    if (activeId === null) { setDetail(null); return; }
    let live = true;
    api.get<Detail>(`/api/media/${activeId}`).then((d) => {
      if (!live) return;
      setDetail(d);
      const base = d.resolved?.value ?? d.candidates.find((c) => c.value && !c.bad)?.value ?? '';
      setDate(isoDate(base));
      setTime(isoTime(base));
      setTz(d.resolved?.tz && d.resolved.tz !== 'Z' ? d.resolved.tz : '');
    }).catch(fail);
    api.get<Neighbor[]>(`/api/media/${activeId}/neighbors`).then((n) => live && setNbrs(n)).catch(() => undefined);
    return () => { live = false; };
  }, [activeId, version, fail]);

  const nextId = useCallback((dir: 1 | -1) => {
    const i = items.findIndex((x) => x.id === activeId);
    return items[i + dir]?.id ?? null;
  }, [items, activeId]);

  const after = async (msg: string, advance = true) => {
    const next = advance ? (nextId(1) ?? nextId(-1)) : activeId;
    toast(msg, 'ok');
    setSel(new Set());
    setActiveId(next);
    setVersion((v) => v + 1);
    await refresh();
  };

  const post = async (body: Record<string, unknown>, msg: string) => {
    setBusy(true);
    try {
      const r = await api.post<{ updated: number }>('/api/review/resolve', body);
      await after(`${msg} (${r.updated} ${r.updated === 1 ? 'file' : 'files'}).`);
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  const undo = useCallback(async () => {
    try {
      const r = await api.post<{ undone: number }>('/api/review/undo');
      toast(`Undid the last change (${r.undone} files).`, 'ok');
      setVersion((v) => v + 1);
      await refresh();
    } catch (e) { fail(e); }
  }, [fail, toast, refresh]);

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName) || e.metaKey || e.ctrlKey) return;
      if (e.key === 'j' || e.key === 'ArrowDown') { const n = nextId(1); if (n !== null) { e.preventDefault(); setActiveId(n); } }
      if (e.key === 'k' || e.key === 'ArrowUp') { const n = nextId(-1); if (n !== null) { e.preventDefault(); setActiveId(n); } }
      if (e.key === 'u') void undo();
    };
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [nextId, undo]);

  const count = review ? review[tab === 'orphans' ? 'orphans' : tab] : 0;
  const batchBody = (): Record<string, unknown> | null => {
    const target = bTarget === 'selected' ? { ids: [...sel] } : { query: { reason: tab === 'all' ? undefined : tab } };
    if (bTarget === 'selected' && sel.size === 0) { toast('Tick the files you want to change first.', 'error'); return null; }
    if (bMode === 'shift') return { ...target, mode: 'shift', minutes: Number(bMin) };
    if (bMode === 'sequence') return { ...target, mode: 'sequence', date: bDate, time: bTime, tz: bTz || null, step_seconds: Number(bStep) };
    return { ...target, mode: 'set', date: bDate, time: bTime, tz: bTz || null };
  };
  const reasonText = useMemo(() => detail?.reasons.map((r) => REASON_LABEL[r] ?? r) ?? [], [detail]);

  return (
    <>
      <h1 className="title">Needs review</h1>
      <p className="serif m" style={{ fontSize: 24, fontStyle: 'italic', margin: '0 0 8px' }}>Photos whose date is missing, damaged or in doubt. Pick the right one.</p>
      <div className="review">
        <section aria-label="Files to review">
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
            {TABS.map(([t, l]) => (
              <button key={t} className={`chip${tab === t ? ' on' : ''}`} aria-pressed={tab === t}
                onClick={() => { setTab(t); setSel(new Set()); setActiveId(null); }}>
                {l}{review ? ` ${review[t === 'orphans' ? 'orphans' : t]}` : ''}
              </button>
            ))}
          </div>
          {tab !== 'orphans' && (
            <>
              <label className="row m" style={{ fontSize: 13, marginBottom: 8 }}>
                <input type="checkbox" checked={items.length > 0 && sel.size === items.length} onChange={(e) => setSel(e.target.checked ? new Set(items.map((i) => i.id)) : new Set())} /> Select all loaded ({items.length})
              </label>
              <div className="queue">
                {items.length === 0 && <div className="m" style={{ padding: '18px 0' }}>Nothing to review here. 🎉 Well, almost: check the other tabs.</div>}
                {items.map((it) => (
                  <div key={it.id} className={`qrow${it.id === activeId ? ' sel' : ''}`}>
                    <input type="checkbox" aria-label={`Select ${it.name}`} checked={sel.has(it.id)}
                      onChange={() => setSel((s) => { const n = new Set(s); if (n.has(it.id)) n.delete(it.id); else n.add(it.id); return n; })} />
                    <div>
                      <button className="nm" style={{ textAlign: 'left' }} onClick={() => setActiveId(it.id)}>{it.name}</button>
                      <div className="m" style={{ fontSize: 13 }}>{it.reasons.map((r) => REASON_LABEL[r] ?? r)[0] ?? ''}</div>
                    </div>
                  </div>
                ))}
                {more && <button className="btn sm" style={{ margin: '14px 0' }} onClick={() => void loadMore()}>Load more</button>}
              </div>

              <div className="panel" style={{ marginTop: 18, padding: 18 }}>
                <div className="eye" style={{ marginBottom: 10 }}>Change many at once</div>
                <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 12 }}>
                  {([['set', 'Set date'], ['shift', 'Shift by minutes'], ['sequence', 'Space apart']] as const).map(([v, l]) => (
                    <label key={v} className="row"><input type="radio" name="bm" checked={bMode === v} onChange={() => setBMode(v)} /> {l}</label>
                  ))}
                </div>
                <div className="fields" style={{ marginBottom: 12 }}>
                  {bMode !== 'shift' && <>
                    <label>Batch date<input className="fld" type="date" value={bDate} onChange={(e) => setBDate(e.target.value)} /></label>
                    <label>Batch time<input className="fld" value={bTime} onChange={(e) => setBTime(e.target.value)} style={{ width: 90 }} /></label>
                    <label>Batch offset<input className="fld" value={bTz} onChange={(e) => setBTz(e.target.value)} placeholder="+05:30" style={{ width: 80 }} /></label>
                  </>}
                  {bMode === 'shift' && <label>Minutes (+ or -)<input className="fld" value={bMin} onChange={(e) => setBMin(e.target.value)} style={{ width: 90 }} /></label>}
                  {bMode === 'sequence' && <label>Seconds apart<input className="fld" value={bStep} onChange={(e) => setBStep(e.target.value)} style={{ width: 70 }} /></label>}
                </div>
                <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 12 }}>
                  <label className="row"><input type="radio" name="bt" checked={bTarget === 'selected'} onChange={() => setBTarget('selected')} /> Ticked files ({sel.size})</label>
                  <label className="row"><input type="radio" name="bt" checked={bTarget === 'filter'} onChange={() => setBTarget('filter')} /> Everything in this list ({count})</label>
                </div>
                <button className="btn sm pri" disabled={busy} onClick={() => { const b = batchBody(); if (b) void post(b, 'Updated'); }}>Apply to many</button>
              </div>
            </>
          )}
          {tab === 'orphans' && (
            <div>
              <p className="m">These Google JSON files did not match any photo. Usually the photo lives in a ZIP part that is missing. Add the missing part on the Upload page and scan again.</p>
              <div className="queue">
                {orphans.length === 0 && <div className="m">No orphan sidecars.</div>}
                {orphans.map((o) => (
                  <div key={o.id} className="qrow"><div><div className="nm">{o.name}</div><div className="m" style={{ fontSize: 13 }}>{o.folder}</div></div></div>
                ))}
              </div>
            </div>
          )}
        </section>

        <section className="work" aria-label="Workspace">
          {!detail || tab === 'orphans' ? (
            <div className="empty"><div className="serif">{tab === 'orphans' ? 'Orphan sidecars have no photo to fix.' : 'Choose a file on the left.'}</div></div>
          ) : (
            <>
              <div className="serif" style={{ fontSize: 38, fontWeight: 300, marginBottom: 16, overflowWrap: 'anywhere' }}>{detail.name}</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.3fr) minmax(0,1fr)', gap: 32, marginBottom: 26 }}>
                <div className="big"><img src={previewUrl(detail.id, 1600)} alt={`Preview of ${detail.name}`} /></div>
                <div>
                  <div className="eye">Clues</div>
                  <p className="m" style={{ margin: '10px 0 4px' }}>Folder: {detail.folder}</p>
                  {reasonText.map((r) => <p key={r} className="err" style={{ margin: '2px 0' }}>{r}</p>)}
                  {detail.error && <p className="err" style={{ margin: '2px 0' }}>{detail.error}</p>}
                  {nbrs.length > 0 && <>
                    <div className="eye" style={{ marginTop: 14 }}>Nearby in this folder</div>
                    <div className="nbrs">
                      {nbrs.map((n) => (
                        <button key={n.id} title={`${n.name}, ${fmtDateTime(n.date)}`} onClick={() => setActiveId(n.id)}>
                          <img src={previewUrl(n.id, 480)} alt={n.name} />
                        </button>
                      ))}
                    </div>
                    <div className="m" style={{ fontSize: 13, marginTop: 8 }}>{nbrs.map((n) => fmtDateTime(n.date).split(',')[0]).filter((v, i, a) => a.indexOf(v) === i).join(' · ')}</div>
                  </>}
                </div>
              </div>
              <table className="tbl" style={{ marginBottom: 24 }}>
                <thead><tr><th>Source</th><th>Value</th><th>Offset</th><th /></tr></thead>
                <tbody>
                  {detail.candidates.length === 0 && <tr><td colSpan={4} className="m">No date information was found in this file.</td></tr>}
                  {detail.candidates.map((c, i) => (
                    <tr key={i}>
                      <td>{c.source === 'exif' ? c.tag : SRC_LABEL[c.source] ?? c.source}</td>
                      <td className={c.bad ? 'err' : ''}>{c.value ? fmtDateTime(c.value) : 'unreadable'}{c.approx ? ' (time unknown)' : ''}{c.bad ? ' (placeholder)' : ''}</td>
                      <td className="m">{c.tz ?? 'unknown'}</td>
                      <td>{c.value && !c.bad && <button className="chip on" onClick={() => void post({ ids: [detail.id], mode: 'candidate', candidate: i }, 'Used this date')}>Use</button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="fields" style={{ marginBottom: 22 }}>
                <label>Date<input className="fld" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
                <label>Time<input className="fld" value={time} onChange={(e) => setTime(e.target.value)} placeholder="HH:MM:SS" style={{ width: 110 }} /></label>
                <label>Timezone offset<input className="fld" value={tz} onChange={(e) => setTz(e.target.value)} placeholder="+05:30" style={{ width: 110 }} /></label>
              </div>
              <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
                <button className="btn pri" disabled={busy || !date} onClick={() => void post({ ids: [detail.id], mode: 'set', date, time: time || '00:00:00', tz: tz || null }, 'Date saved')}>Apply</button>
                <button className="btn" onClick={() => { const n = nextId(1); if (n !== null) setActiveId(n); }}>Skip</button>
                <button className="btn" onClick={() => void undo()}>Undo</button>
                {detail.manual && <button className="btn" onClick={() => void post({ ids: [detail.id], mode: 'clear' }, 'Manual date removed')}>Clear my date</button>}
              </div>
              <p className="m" style={{ fontSize: 13, marginTop: 18 }}>Keys: J and K move between files, U undoes the last change. <Link to="/timeline">Back to the timeline</Link></p>
            </>
          )}
        </section>
      </div>
    </>
  );
}
