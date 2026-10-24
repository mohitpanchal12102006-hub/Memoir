import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type Source, type TakeoutSet } from '../api';
import { Atmosphere, HeroImage } from '../components/HeroImage';
import { FolderPicker } from '../components/FolderPicker';
import { JobProgress } from '../components/JobProgress';
import { basename, fmtBytes } from '../lib/format';
import { useApp } from '../state';

const FORMATS = ['JPG', 'HEIC', 'RAW', 'DNG', 'CR3', 'NEF', 'ARW', 'MP4', 'MOV', 'MKV', 'AV1', 'WEBM'];

function partClass(src: Source | undefined, scanning: boolean, firstOpen: boolean): string {
  if (!src) return 'miss';
  if (!src.online || src.state === 'offline') return 'off';
  if (src.state === 'error') return 'err';
  if (src.state === 'queued') return '';
  if (src.media_count > 0 && src.scanned_count >= src.media_count) return 'ok';
  if (scanning && firstOpen) return 'go';
  return 'idx';
}

function SetPanel({ set, scanning }: { set: TakeoutSet; scanning: boolean }) {
  const byNo = new Map(set.parts.map((p) => [p.part_no, p]));
  let openSeen = false;
  const segs = Array.from({ length: set.highest_part }, (_, i) => {
    const src = byNo.get(i + 1);
    const incomplete = !!src && src.state === 'indexed' && src.scanned_count < src.media_count;
    const first = incomplete && !openSeen;
    if (first) openSeen = true;
    return { n: i + 1, cls: partClass(src, scanning, first), src };
  });
  return (
    <div>
      <div className="eye">Takeout set</div>
      <div className="serif" style={{ fontSize: 34, margin: '8px 0' }}>{set.count} {set.count === 1 ? 'part' : 'parts'}, {fmtBytes(set.size)}</div>
      <div className="parts" role="img" aria-label={`Parts: ${segs.map((s) => `${s.n} ${s.cls || 'waiting'}`).join(', ')}`}>
        {segs.map((s) => <i key={s.n} className={`sg ${s.cls}`} title={`Part ${s.n}: ${s.src ? s.src.state : 'missing'}`} />)}
      </div>
      {set.missing.length > 0 ? (
        <div className="err">Part {set.missing.join(', ')} is missing. Some photo dates from Google may stay unmatched until you add it.</div>
      ) : (
        <div className="m">All parts up to {set.highest_part} are present.</div>
      )}
    </div>
  );
}

export function Upload() {
  const { summary, sources, sets, active, health, startJob, refresh, toast, fail, jobs } = useApp();
  const [pick, setPick] = useState(false);
  const [pasted, setPasted] = useState('');
  const [relinkFor, setRelinkFor] = useState<number | null>(null);
  const [relinkPath, setRelinkPath] = useState('');

  const addPaths = async (paths: string[]) => {
    try {
      const r = await api.post<{ added: Source[]; errors: { path: string; error: string }[] }>('/api/sources', { paths });
      if (r.added.length) toast(`Added ${r.added.length} ${r.added.length === 1 ? 'source' : 'sources'}.`, 'ok');
      r.errors.forEach((e) => toast(`${e.path}: ${e.error}`, 'error'));
      await refresh();
    } catch (e) {
      fail(e);
    }
  };

  const scanning = active?.type === 'scan';
  const lastScan = jobs.find((j) => j.type === 'scan');
  const grouped = new Set(sets.flatMap((s) => s.parts.map((p) => p.id)));
  const others = sources.filter((s) => !grouped.has(s.id));
  const needsScan = !!summary && (summary.pending_scan > 0 || summary.unindexed_sources > 0);
  const started = !!summary && summary.total > 0;
  const demo = sources[0]?.path ?? '/Volumes/SSD/takeout-*.zip';
  const cmd = useMemo(() => {
    const c = `$ memoir index ${demo}`;
    return c.length > 56 ? `${c.slice(0, 53)}...` : c;
  }, [demo]);

  return (
    <>
      <section className="hero">
        <div>
          <div className="eye">01 · Upload</div>
          <h1>Keep every moment,<br /><i>in its place.</i></h1>
          <div className="rule" />
          <p>Takeout archives, ZIP parts and folders, read quietly in place. Nothing leaves this computer.</p>
        </div>
        <HeroImage name="hero" scene="a" alt="A calm mountain landscape at dawn" style={{ height: 400 }}>
          <Atmosphere sunLeft="calc(70% - 70px)" sunTop={43} />
          <div className="caption">Take your time.</div>
        </HeroImage>
      </section>

      <section>
        <div className="term" aria-label="Example command">
          <span key={cmd} className="typ" style={{ ['--n' as string]: cmd.length, animationTimingFunction: `steps(${cmd.length})` }}>{cmd}</span>
          <span className="cur" />
        </div>
        <div className="tick" aria-hidden="true"><div className="trk">{[...FORMATS, ...FORMATS].map((f, i) => <span key={i}>{f}</span>)}</div></div>
      </section>

      {needsScan && !active && (
        <section className="banner">
          <span>{started ? 'A previous scan was not finished. It continues where it stopped.' : 'Sources added. Start the scan to read every date.'}</span>
          <button className="btn pri" onClick={() => void startJob({ type: 'scan' })} disabled={!health?.exiftool}>{started ? 'Resume scan' : 'Start scan'}</button>
        </section>
      )}

      <section className="panel" style={{ marginTop: 22 }}>
        <div className="grid2">
          <div>
            <h2>Add your photos</h2>
            <p className="m">Choose the ZIP parts of your Takeout (or a folder that contains them). ZIP files are read in place and never extracted to disk.</p>
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
              <button className="btn pri" onClick={() => setPick(true)}>Choose ZIP parts or folders</button>
            </div>
          </div>
          <form onSubmit={(e) => { e.preventDefault(); const p = pasted.split('\n').map((x) => x.trim()).filter(Boolean); if (p.length) { void addPaths(p); setPasted(''); } }}>
            <label className="eye" htmlFor="paste">Or paste paths, one per line</label>
            <textarea id="paste" className="fld box" rows={3} value={pasted} onChange={(e) => setPasted(e.target.value)}
              placeholder={`Example: D:${health?.sep ?? '/'}Takeout${health?.sep ?? '/'}takeout-20240101T000000Z-001.zip`} style={{ marginTop: 8, resize: 'vertical' }} />
            <button className="btn sm" type="submit" style={{ marginTop: 10 }} disabled={!pasted.trim()}>Add paths</button>
          </form>
        </div>
      </section>

      {sets.map((s) => (
        <section key={s.group} className="panel" style={{ marginTop: 22 }}><SetPanel set={s} scanning={!!scanning} /></section>
      ))}

      {sources.length > 0 && (
        <section className="panel" style={{ marginTop: 22 }}>
          <div className="eye" style={{ marginBottom: 6 }}>Sources</div>
          {[...sets.flatMap((s) => s.parts), ...others].map((s) => (
            <div key={s.id}>
              <div className="srow">
                <span style={{ overflowWrap: 'anywhere' }}>
                  <span className="serif" style={{ fontSize: 20 }}>{basename(s.path)}</span>
                  <span className="m" style={{ fontSize: 13, display: 'block' }}>{s.path}</span>
                </span>
                <span className="tag">{s.location === 'external' ? 'External drive' : 'Laptop'}</span>
                <span className={s.online ? 'm' : 'err'} style={{ fontSize: 13 }}>
                  {!s.online ? 'Offline' : s.state === 'error' ? 'Damaged' : s.state === 'queued' ? 'Waiting' : `${s.scanned_count.toLocaleString()} of ${s.media_count.toLocaleString()} read`}
                  {s.size > 0 && ` · ${fmtBytes(s.size)}`}
                </span>
                <span style={{ display: 'flex', gap: 8 }}>
                  {!s.online && <button className="btn sm" onClick={() => { setRelinkFor(relinkFor === s.id ? null : s.id); setRelinkPath(''); }}>Re-link</button>}
                  <button className="btn sm" disabled={!!active} onClick={async () => {
                    try { await api.del(`/api/sources/${s.id}`); await refresh(); } catch (e) { fail(e); }
                  }}>Remove</button>
                </span>
              </div>
              {s.error && <div className="err" style={{ fontSize: 13 }}>{s.error}</div>}
              {relinkFor === s.id && (
                <form style={{ display: 'flex', gap: 10, padding: '0 0 14px' }} onSubmit={async (e) => {
                  e.preventDefault();
                  try { await api.post(`/api/sources/${s.id}/relink`, { path: relinkPath }); setRelinkFor(null); toast('Re-linked.', 'ok'); await refresh(); } catch (er) { fail(er); }
                }}>
                  <input className="fld box" aria-label="New location" placeholder="New location of this file or folder" value={relinkPath} onChange={(e) => setRelinkPath(e.target.value)} />
                  <button className="btn sm pri" type="submit">Re-link</button>
                </form>
              )}
            </div>
          ))}
        </section>
      )}

      {(active && active.type === 'scan') && (
        <section className="panel" style={{ marginTop: 22 }}><JobProgress job={active} /></section>
      )}
      {!active && lastScan?.state === 'error' && <section className="banner warn" role="alert" style={{ marginTop: 22 }}>{lastScan.error}</section>}

      {summary && summary.total > 0 && (
        <section style={{ marginTop: 32 }}>
          <div className="hr" />
          <div className="stats" style={{ padding: '30px 0' }}>
            <div className="stat"><div className="n">{summary.images.toLocaleString()}</div><div className="eye m">Images</div></div>
            <div className="stat"><div className="n">{summary.raws.toLocaleString()}</div><div className="eye m">RAW</div></div>
            <div className="stat"><div className="n">{summary.videos.toLocaleString()}</div><div className="eye m">Video</div></div>
            <div className="stat"><div className="n">{summary.review.toLocaleString()}</div><div className="eye m">Need review</div></div>
          </div>
          <div style={{ display: 'flex', gap: 14 }}>
            <Link className="btn pri" to="/timeline">Open timeline</Link>
            {summary.review > 0 && <Link className="btn" to="/review">Fix dates ({summary.review})</Link>}
          </div>
        </section>
      )}

      {pick && <FolderPicker mode="sources" title="Choose ZIP parts or folders" onClose={() => setPick(false)} onPick={(p) => { setPick(false); void addPaths(p); }} />}
    </>
  );
}
