import { useEffect, useState } from 'react';
import { api, type ExportOptions, type Preflight } from '../api';
import { fmtBytes, plural } from '../lib/format';
import { useApp } from '../state';
import { FolderPicker } from './FolderPicker';
import { JobProgress } from './JobProgress';

type ExportRow = { id: number; created: number; dest: string; state: string; total: number; done: number };
const TZ_RE = /^[+-]\d{2}:\d{2}$/;

export function ExportDialog() {
  const { exportOpen, setExportOpen, jobs, active, startJob, health, fail } = useApp();
  const [step, setStep] = useState(0);
  const [type, setType] = useState<'folder' | 'zip'>('folder');
  const [path, setPath] = useState(() => localStorage.getItem('memoir.dest') ?? '');
  const [structure, setStructure] = useState<ExportOptions['structure']>('year-month');
  const [prefix, setPrefix] = useState(true);
  const [includeReview, setIncludeReview] = useState(false);
  const [unresolved, setUnresolved] = useState<'skip' | 'folder'>('skip');
  const [tz, setTz] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [pf, setPf] = useState<Preflight | null>(null);
  const [checking, setChecking] = useState(false);
  const [browse, setBrowse] = useState(false);
  const [prev, setPrev] = useState<ExportRow[]>([]);
  const [localErr, setLocalErr] = useState('');

  const exportJob = jobs.find((j) => j.type === 'export');
  const running = active?.type === 'export';

  useEffect(() => {
    if (!exportOpen) return;
    if (running) setStep(3);
    api.get<ExportRow[]>('/api/exports').then((r) => setPrev(r.filter((x) => x.state === 'interrupted'))).catch(() => undefined);
  }, [exportOpen, running]);

  if (!exportOpen) return null;

  const options = (): ExportOptions => ({
    destination: { type, path: path.trim() }, structure, prefix, include_review: includeReview, unresolved,
    sidecar_tz: tz.trim() || null, date_from: from || null, date_to: to || null,
  });

  const runPreflight = async () => {
    setLocalErr('');
    if (!path.trim()) return setLocalErr('Choose a destination first.');
    if (tz.trim() && !TZ_RE.test(tz.trim())) return setLocalErr('Timezone must look like +05:30 or -08:00.');
    localStorage.setItem('memoir.dest', path.trim());
    setChecking(true);
    try {
      setPf(await api.post<Preflight>('/api/export/preflight', options()));
      setStep(2);
    } catch (e) {
      fail(e);
    } finally {
      setChecking(false);
    }
  };

  const start = async () => {
    const j = await startJob({ type: 'export', options: options() });
    if (j) setStep(3);
  };

  const resume = async (id: number) => {
    const j = await startJob({ type: 'export', options: {}, resume_id: id });
    if (j) setStep(3);
  };

  const sep = health?.sep ?? '/';
  const labels = ['Destination', 'Organize', 'Check', 'Export'];
  const finished = exportJob && !running && step === 3;
  const res = exportJob?.result as { done?: number; failed?: number; embed_failed?: number; report?: string } | undefined;

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Export">
      <div className="modal">
        <div className="eye">Export</div>
        <h2>Write your organized archive</h2>
        <div className="steps" aria-label="Steps">
          {labels.map((l, i) => <span key={l} className={i === step ? 'on' : ''}>{i + 1}. {l}</span>)}
        </div>

        {step === 0 && (
          <div>
            <div style={{ display: 'flex', gap: 24, marginBottom: 18 }}>
              <label className="row"><input type="radio" name="dt" checked={type === 'folder'} onChange={() => setType('folder')} /> A folder</label>
              <label className="row"><input type="radio" name="dt" checked={type === 'zip'} onChange={() => setType('zip')} /> One ZIP file</label>
            </div>
            <label className="eye" htmlFor="dest" style={{ display: 'block', marginBottom: 6 }}>{type === 'folder' ? 'Destination folder' : 'ZIP file to create'}</label>
            <div style={{ display: 'flex', gap: 12 }}>
              <input id="dest" className="fld box" value={path} onChange={(e) => setPath(e.target.value)}
                placeholder={type === 'folder' ? `Example: E:${sep}Memoir Archive` : `Example: E:${sep}memoir-archive.zip`} />
              <button className="btn sm" onClick={() => setBrowse(true)}>Browse</button>
            </div>
            <p className="m" style={{ fontSize: 14 }}>
              Originals are never changed or re-encoded. Memoir copies each file, writes the capture date into it, and sets its file times.
              Choose a drive other than the one your ZIP files are on if you can.
            </p>
            {prev.length > 0 && (
              <div className="banner" style={{ marginTop: 16 }}>
                <span>An earlier export to {prev[0].dest} stopped at {prev[0].done} of {prev[0].total} files.</span>
                <button className="btn sm pri" onClick={() => void resume(prev[0].id)}>Resume it</button>
              </div>
            )}
            {localErr && <div className="err" role="alert">{localErr}</div>}
            <div style={{ display: 'flex', gap: 12, marginTop: 22 }}>
              <button className="btn pri" onClick={() => { if (!path.trim()) setLocalErr('Choose a destination first.'); else { setLocalErr(''); setStep(1); } }}>Next</button>
              <button className="btn" onClick={() => setExportOpen(false)}>Close</button>
            </div>
          </div>
        )}

        {step === 1 && (
          <div>
            <div className="panel" style={{ padding: 18, marginBottom: 18 }}>
              <div className="eye" style={{ marginBottom: 8 }}>Three layers keep your order everywhere</div>
              <label className="row"><input type="checkbox" checked disabled /> 1. Write the capture date inside every file</label>
              <label className="row" style={{ marginTop: 6 }}><input type="checkbox" checked disabled /> 2. Set file created and modified times</label>
              <label className="row" style={{ marginTop: 6 }}><input type="checkbox" checked={prefix} onChange={(e) => setPrefix(e.target.checked)} /> 3. Start each file name with the date and time</label>
            </div>
            <div className="eye" style={{ marginBottom: 8 }}>Folders</div>
            <div style={{ display: 'flex', gap: 22, flexWrap: 'wrap', marginBottom: 18 }}>
              {([['flat', 'One folder'], ['year', 'By year'], ['year-month', 'By year and month']] as const).map(([v, l]) => (
                <label key={v} className="row"><input type="radio" name="st" checked={structure === v} onChange={() => setStructure(v)} /> {l}</label>
              ))}
            </div>
            <div className="fields" style={{ marginBottom: 18 }}>
              <label>Timezone for Google dates
                <input className="fld" value={tz} onChange={(e) => setTz(e.target.value)} placeholder="+05:30" style={{ width: 120 }} aria-describedby="tzhelp" />
              </label>
              <label>From date<input className="fld" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
              <label>To date<input className="fld" type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
            </div>
            <p id="tzhelp" className="m" style={{ fontSize: 13, marginTop: -6 }}>
              Google stores photo times in UTC. Enter your timezone (for example +05:30) so files without their own camera time show the local time. Leave blank to keep UTC.
              The date range is optional and lets you export just a part of the archive.
            </p>
            <label className="row" style={{ marginBottom: 8 }}><input type="checkbox" checked={includeReview} onChange={(e) => setIncludeReview(e.target.checked)} /> Include files that still need review (using their best guess)</label>
            <label className="row"><input type="checkbox" checked={unresolved === 'folder'} onChange={(e) => setUnresolved(e.target.checked ? 'folder' : 'skip')} /> Put files with no date in an “_Unsorted” folder</label>
            {localErr && <div className="err" role="alert" style={{ marginTop: 10 }}>{localErr}</div>}
            <div style={{ display: 'flex', gap: 12, marginTop: 22 }}>
              <button className="btn" onClick={() => setStep(0)}>Back</button>
              <button className="btn pri" disabled={checking} onClick={() => void runPreflight()}>{checking ? 'Checking' : 'Check before exporting'}</button>
            </div>
          </div>
        )}

        {step === 2 && pf && (
          <div>
            <div className="stats" style={{ marginBottom: 18 }}>
              <div className="stat"><div className="n">{pf.files.toLocaleString()}</div><div className="eye m">Files</div></div>
              <div className="stat"><div className="n">{fmtBytes(pf.bytes)}</div><div className="eye m">To copy</div></div>
              <div className="stat"><div className="n">{fmtBytes(pf.free)}</div><div className="eye m">Free ({pf.filesystem})</div></div>
            </div>
            <div className="track" aria-hidden="true"><div className="fill" style={{ width: `${pf.free > 0 ? Math.min(100, (pf.bytes / pf.free) * 100) : 100}%` }} /></div>
            <ul className="m" style={{ fontSize: 14, paddingLeft: 18 }}>
              {(pf.skipped.removed_duplicates ?? 0) > 0 && <li>{plural(pf.skipped.removed_duplicates ?? 0, 'duplicate')} {pf.skipped.removed_duplicates === 1 ? 'is' : 'are'} left out.</li>}
              {(pf.skipped.needs_review ?? 0) > 0 && <li>{plural(pf.skipped.needs_review ?? 0, 'file')} that {pf.skipped.needs_review === 1 ? 'needs' : 'need'} review {pf.skipped.needs_review === 1 ? 'is' : 'are'} left out.</li>}
              {(pf.skipped.no_date ?? 0) > 0 && <li>{plural(pf.skipped.no_date ?? 0, 'file')} without a date {pf.skipped.no_date === 1 ? 'is' : 'are'} left out.</li>}
            </ul>
            {pf.warnings.map((w) => <div key={w} className="banner" style={{ marginBottom: 10 }}>{w}</div>)}
            {pf.errors.map((w) => <div key={w} className="banner warn" role="alert" style={{ marginBottom: 10 }}>{w}</div>)}
            <div style={{ display: 'flex', gap: 12, marginTop: 22 }}>
              <button className="btn" onClick={() => setStep(1)}>Back</button>
              <button className="btn pri" disabled={!pf.ok} onClick={() => void start()}>Start export</button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div>
            {running && active && <JobProgress job={active} />}
            {finished && exportJob && (
              <div>
                {exportJob.state === 'done' && (
                  <>
                    <div className="serif" style={{ fontSize: 30 }}>Export complete</div>
                    <p className="m">{plural(res?.done ?? 0, 'file')} written{res?.failed ? `, ${res.failed} failed` : ''}.
                      {res?.embed_failed ? ` ${res.embed_failed} files are in formats where the date could not be embedded (they still have the date in their name and file times).` : ''}</p>
                    {res?.report && <p className="m mono" style={{ fontSize: 12, overflowWrap: 'anywhere' }}>Report: {res.report}</p>}
                  </>
                )}
                {exportJob.state === 'error' && <div className="err" role="alert">{exportJob.error}</div>}
                {exportJob.state === 'cancelled' && <p className="m">Export cancelled. You can resume it later from the first step.</p>}
              </div>
            )}
            <div style={{ display: 'flex', gap: 12, marginTop: 22 }}>
              <button className="btn" onClick={() => setExportOpen(false)}>{running ? 'Hide (keeps running)' : 'Close'}</button>
              {!running && <button className="btn" onClick={() => setStep(0)}>New export</button>}
            </div>
          </div>
        )}
      </div>
      {browse && (
        <FolderPicker mode="dir" title="Choose the destination folder" onClose={() => setBrowse(false)}
          onPick={(p) => { setPath(type === 'zip' ? `${p[0].replace(/[\\/]$/, '')}${sep}memoir-archive.zip` : p[0]); setBrowse(false); }} />
      )}
    </div>
  );
}
