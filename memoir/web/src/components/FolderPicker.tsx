import { useCallback, useEffect, useState } from 'react';
import { api, ApiError, type FsListing } from '../api';
import { fmtBytes } from '../lib/format';

export function FolderPicker({ mode, title, onClose, onPick }: {
  mode: 'sources' | 'dir'; title: string; onClose: () => void; onPick: (paths: string[]) => void;
}) {
  const [listing, setListing] = useState<FsListing | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [typed, setTyped] = useState('');

  const go = useCallback(async (p: string, fallback = true) => {
    setLoading(true);
    setErr('');
    try {
      const l = await api.get<FsListing>('/api/fs', { path: p });
      setListing(l);
      setTyped(l.path);
      if (l.path) localStorage.setItem('memoir.lastPath', l.path);
    } catch (e) {
      if (p && fallback) {
        await go('', false);
      }
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void go(localStorage.getItem('memoir.lastPath') ?? '');
  }, [go]);

  const toggle = (p: string) =>
    setSel((s) => {
      const n = new Set(s);
      if (n.has(p)) n.delete(p);
      else n.add(p);
      return n;
    });

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label={title}>
      <div className="modal">
        <div className="eye">Browse this computer</div>
        <h2>{title}</h2>
        <form onSubmit={(e) => { e.preventDefault(); void go(typed); }} style={{ display: 'flex', gap: 12, margin: '14px 0' }}>
          <input className="fld box" aria-label="Folder path" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Type or paste a folder path" />
          <button className="btn sm" type="submit">Go</button>
        </form>
        {err && <div className="err" role="alert" style={{ marginBottom: 10 }}>{err}</div>}
        <div className="fs-list" aria-busy={loading}>
          {listing?.parent !== null && listing?.parent !== undefined && (
            <div className="fs-row" onClick={() => void go(listing.parent ?? '')} role="button" tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter') void go(listing.parent ?? ''); }}>
              <span className="serif" style={{ fontSize: 20 }}>.. up one level</span>
            </div>
          )}
          {listing?.entries.map((en) => (
            <div key={en.path} className="fs-row">
              {mode === 'sources' && (
                <input type="checkbox" aria-label={`Select ${en.name}`} checked={sel.has(en.path)} onChange={() => toggle(en.path)} />
              )}
              <span style={{ flex: 1 }} onClick={() => (en.type === 'dir' ? void go(en.path) : mode === 'sources' && toggle(en.path))}
                role="button" tabIndex={0}
                onKeyDown={(e) => { if (e.key === 'Enter') { if (en.type === 'dir') void go(en.path); else if (mode === 'sources') toggle(en.path); } }}>
                <span className="serif" style={{ fontSize: 20 }}>{en.name}</span>
              </span>
              <span className="tag">{en.type === 'dir' ? 'folder' : 'zip'}</span>
              {en.size ? <span className="m" style={{ fontSize: 13 }}>{fmtBytes(en.size)}</span> : null}
            </div>
          ))}
          {listing && listing.entries.length === 0 && <div className="fs-row m">No folders or ZIP files here.</div>}
        </div>
        <div style={{ display: 'flex', gap: 12, marginTop: 20, flexWrap: 'wrap' }}>
          {mode === 'sources' ? (
            <>
              <button className="btn pri" disabled={sel.size === 0} onClick={() => onPick([...sel])}>Add selected ({sel.size})</button>
              <button className="btn" disabled={!listing?.path} onClick={() => listing?.path && onPick([listing.path])}>Use this folder{listing?.entries.some((e) => e.type === 'zip') ? ' (adds its ZIP parts)' : ''}</button>
            </>
          ) : (
            <button className="btn pri" disabled={!listing?.path} onClick={() => listing?.path && onPick([listing.path])}>Choose this folder</button>
          )}
          <button className="btn" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
