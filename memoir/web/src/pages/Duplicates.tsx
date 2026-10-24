import { useCallback, useEffect, useState } from 'react';
import { api, previewUrl, type DupGroup } from '../api';
import { JobProgress } from '../components/JobProgress';
import { fmtBytes, plural } from '../lib/format';
import { useApp } from '../state';

type Mode = 'exclude' | 'quarantine';
type Plan = { files: number; bytes: number; folders: { folder: string; removing: number; bytes: number }[] };
type Result = { excluded: number; quarantined: number; skipped: number; report: string };

export function Duplicates() {
  const { dups, summary, active, startJob, refresh, fail, toast } = useApp();
  const [tab, setTab] = useState<'exact' | 'similar'>('exact');
  const [idx, setIdx] = useState(0);
  const [groups, setGroups] = useState<DupGroup[]>([]);
  const [total, setTotal] = useState(0);
  const [mode, setMode] = useState<Mode>('exclude');
  const [off, setOff] = useState<Set<string>>(new Set());
  const [plan, setPlan] = useState<Plan | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);

  const similarReady = summary?.similar_ready ?? false;
  const scanning = active?.type === 'similar';

  useEffect(() => {
    let live = true;
    api.get<{ groups: DupGroup[]; total: number }>('/api/duplicates', { kind: tab, offset: idx, limit: 1 })
      .then((r) => { if (live) { setGroups(r.groups); setTotal(r.total); } }).catch(fail);
    return () => { live = false; };
  }, [tab, idx, version, fail, dups?.exact.groups]);

  useEffect(() => { setIdx(0); }, [tab]);

  const folders = dups?.folders ?? [];
  const chosen = folders.filter((f) => !off.has(f.folder)).map((f) => f.folder);
  const group = groups[0];

  const choose = useCallback(async (mediaId: number, role: 'keep' | 'remove' | 'auto') => {
    try {
      await api.post('/api/duplicates/choice', { media_id: mediaId, role });
      setVersion((v) => v + 1);
      await refresh();
    } catch (e) { fail(e); }
  }, [fail, refresh]);

  const openPlan = async () => {
    try { setPlan(await api.post<Plan>('/api/duplicates/plan', { folders: chosen })); } catch (e) { fail(e); }
  };

  const apply = async () => {
    setBusy(true);
    try {
      const r = await api.post<Result>('/api/duplicates/apply', { mode, folders: chosen, confirm: true });
      setResult(r);
      setPlan(null);
      toast(`${plural(r.excluded, 'duplicate')} handled.`, 'ok');
      setVersion((v) => v + 1);
      await refresh();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  const undoAll = async () => {
    try { await api.post('/api/duplicates/reset'); toast('All duplicate choices were reset.', 'ok'); setResult(null); setVersion((v) => v + 1); await refresh(); } catch (e) { fail(e); }
  };

  return (
    <>
      <h1 className="title">Duplicates</h1>
      <p className="serif m" style={{ fontSize: 24, fontStyle: 'italic', margin: '0 0 24px' }}>
        {dups ? `${plural(dups.exact.groups, 'group')}, ${plural(dups.exact.extra, 'extra file')}, ${fmtBytes(dups.exact.reclaimable)} reclaimable` : 'Looking for copies…'}
      </p>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <button className={`chip${tab === 'exact' ? ' on' : ''}`} aria-pressed={tab === 'exact'} onClick={() => setTab('exact')}>Exact {dups?.exact.groups ?? 0}</button>
        <button className={`chip${tab === 'similar' ? ' on' : ''}`} aria-pressed={tab === 'similar'} onClick={() => setTab('similar')}>Similar {dups?.similar.groups ?? 0}</button>
        <button className="btn sm" style={{ marginLeft: 'auto' }} onClick={() => void undoAll()}>Undo all removals</button>
      </div>

      <div className="modes" role="radiogroup" aria-label="What should happen to removed copies">
        <button className={`mode${mode === 'exclude' ? ' on' : ''}`} role="radio" aria-checked={mode === 'exclude'} onClick={() => setMode('exclude')}>
          <span className="eye">Default</span><span className="t">Leave out of export</span>
          <span className="m">Your files are not touched. The extra copies are simply not written to your archive. Fully reversible.</span>
        </button>
        <button className={`mode${mode === 'quarantine' ? ' on' : ''}`} role="radio" aria-checked={mode === 'quarantine'} onClick={() => setMode('quarantine')}>
          <span className="eye">Folders only</span><span className="t">Move to quarantine</span>
          <span className="m">Copies in loose folders move to a Memoir quarantine folder. Copies inside ZIP files are left out of the export instead.</span>
        </button>
        <button className="mode" disabled aria-disabled="true" title="Not available in this version">
          <span className="eye">Not available</span><span className="t">Delete from source</span>
          <span className="m">Deleting is not offered in this version. Use quarantine, then delete the folder yourself once you are sure.</span>
        </button>
      </div>

      {tab === 'similar' && !similarReady && (
        <div className="banner" style={{ marginBottom: 22 }}>
          <span>Find photos that look alike but are not identical (resized or re-saved copies). This reads each photo once more.</span>
          <button className="btn pri" disabled={!!active} onClick={() => void startJob({ type: 'similar' })}>Find similar images</button>
        </div>
      )}
      {scanning && active && <div className="panel" style={{ marginBottom: 22 }}><JobProgress job={active} /></div>}

      <div className="dgrid">
        <section className="panel" aria-label="Removal plan by folder">
          <div className="eye" style={{ marginBottom: 8 }}>Removal plan by folder</div>
          {folders.length === 0 && <p className="m">No exact duplicates to remove.</p>}
          {folders.map((f) => (
            <label key={f.folder} className="row" style={{ justifyContent: 'space-between', padding: '14px 0', borderTop: '1px solid var(--hair)' }}>
              <span><input type="checkbox" checked={!off.has(f.folder)} onChange={() => setOff((s) => { const n = new Set(s); if (n.has(f.folder)) n.delete(f.folder); else n.add(f.folder); return n; })} /> {f.folder}</span>
              <span className="m" style={{ fontSize: 13 }}>{plural(f.files, 'file')}, {fmtBytes(f.bytes)}{f.excluded ? `, ${f.excluded} done` : ''}</span>
            </label>
          ))}
          {(dups?.keep_folders ?? []).slice(0, 3).map((k) => (
            <div key={k.folder} style={{ display: 'flex', justifyContent: 'space-between', padding: '14px 0', borderTop: '1px solid var(--hair)' }}>
              <span>{k.folder}</span><span className="m" style={{ fontSize: 13 }}>keeper, {k.files} kept</span>
            </div>
          ))}
          <button className="btn pri" style={{ marginTop: 16, width: '100%' }} disabled={chosen.length === 0} onClick={() => void openPlan()}>Review removal plan</button>
          {result && <p className="ok" style={{ fontSize: 14 }}>Done: {plural(result.excluded, 'file')} handled{result.quarantined ? `, ${result.quarantined} moved to quarantine` : ''}. Report: <span className="mono" style={{ fontSize: 12, overflowWrap: 'anywhere' }}>{result.report}</span></p>}
        </section>

        <section aria-label="Duplicate group">
          {!group ? (
            <div className="empty"><div className="serif">{tab === 'similar' && !similarReady ? 'Run the similar-image search first.' : 'No duplicate groups.'}</div></div>
          ) : (
            <>
              <div className="serif" style={{ fontSize: 34, fontWeight: 300 }}>Group {idx + 1} of {total} <span className="m" style={{ fontSize: 22, fontStyle: 'italic' }}>{group.members[0]?.name}, {tab === 'exact' ? 'exact match' : 'looks alike'}</span></div>
              {group.members.map((m) => (
                <div key={m.id} className="member">
                  <div className="th"><img src={previewUrl(m.id, 480)} alt="" loading="lazy" /></div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className={`role ${m.role}`}>{m.role === 'keep' ? 'Keep' : 'Remove'}{m.excluded ? ' (already left out)' : ''}</div>
                    <div className="serif" style={{ fontSize: 24, margin: '6px 0', overflowWrap: 'anywhere' }}>{m.role === 'remove' ? `Removing from: ${m.folder}` : `${m.folder}/${m.name}`}</div>
                    <div className="m" style={{ fontSize: 14, overflowWrap: 'anywhere' }}>
                      {m.role === 'remove' ? `${m.folder}/${m.name}` : m.source}, {fmtBytes(m.size)}{m.width ? `, ${m.width}×${m.height}` : ''}{m.has_exif ? ', has a camera date' : ''}{m.suggested ? ', suggested keeper' : ''}
                    </div>
                  </div>
                  {tab === 'exact' && m.role === 'remove' && <button className="btn sm" onClick={() => void choose(m.id, 'keep')}>Keep this one instead</button>}
                  {tab === 'similar' && (
                    <button className="btn sm" onClick={() => void choose(m.id, m.role === 'keep' ? 'remove' : 'keep')}>{m.role === 'keep' ? 'Remove this one' : 'Keep it'}</button>
                  )}
                </div>
              ))}
              <div className="hr" style={{ paddingTop: 24, display: 'flex', gap: 14 }}>
                <button className="btn" disabled={idx === 0} onClick={() => setIdx(idx - 1)}>Previous</button>
                <button className="btn pri" disabled={idx + 1 >= total} onClick={() => setIdx(idx + 1)}>Next</button>
              </div>
            </>
          )}
        </section>
      </div>

      {plan && (
        <div className="overlay" role="dialog" aria-modal="true" aria-label="Review removal plan">
          <div className="modal">
            <div className="eye">Before anything happens</div>
            <h2>Review removal plan</h2>
            <p className="m">Mode: {mode === 'exclude' ? 'leave out of the export (originals untouched)' : 'move loose files to quarantine; ZIP copies are left out of the export'}.</p>
            <table className="tbl">
              <thead><tr><th>Folder</th><th>Removing</th><th>Size</th></tr></thead>
              <tbody>{plan.folders.map((f) => <tr key={f.folder}><td>{f.folder}</td><td>{f.removing}</td><td>{fmtBytes(f.bytes)}</td></tr>)}</tbody>
            </table>
            <p className="serif" style={{ fontSize: 24 }}>Total: {plural(plan.files, 'file')}, {fmtBytes(plan.bytes)}</p>
            <p className="m" style={{ fontSize: 13 }}>A report listing every removed and kept file is saved automatically. Every group keeps at least one copy.</p>
            <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
              <button className="btn" onClick={() => setPlan(null)}>Cancel</button>
              <button className="btn pri" disabled={busy || plan.files === 0} onClick={() => void apply()}>Apply plan</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
