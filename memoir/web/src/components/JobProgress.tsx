import type { Job } from '../api';
import { fmtBytes, fmtEta } from '../lib/format';
import { useApp } from '../state';

export const STAGE_LABEL: Record<string, string> = {
  index: 'Reading ZIP directories', match: 'Matching sidecars and Live Photos', scan: 'Reading dates and fingerprints',
  similar: 'Comparing similar images', export: 'Exporting', done: 'Finished', '': 'Starting',
};

export function jobPercent(j: Job): number {
  if (j.bytes_total > 0 && j.type !== 'similar') return Math.min(100, (j.bytes_done / j.bytes_total) * 100);
  if (j.total > 0) return Math.min(100, (j.done / j.total) * 100);
  return 0;
}

export function JobProgress({ job, compact = false }: { job: Job; compact?: boolean }) {
  const { jobAction } = useApp();
  const pct = jobPercent(job);
  const live = job.state === 'running' || job.state === 'paused' || job.state === 'queued';
  return (
    <div className="grow" role="status" aria-live="polite">
      <div className="eye">{STAGE_LABEL[job.stage] ?? job.stage}{job.state === 'paused' ? ' (paused)' : ''}</div>
      <div className="track" aria-hidden="true"><div className="fill" style={{ width: `${pct}%` }} /></div>
      <div className="m" style={{ fontSize: 13 }}>
        {job.total > 0 && `${job.done.toLocaleString()} of ${job.total.toLocaleString()} files`}
        {job.bytes_total > 0 && ` · ${fmtBytes(job.bytes_done)} of ${fmtBytes(job.bytes_total)}`}
        {job.mb_per_sec > 0 && ` · ${job.mb_per_sec} MB/s`}
        {job.eta_sec ? ` · ${fmtEta(job.eta_sec)} left` : ''}
      </div>
      {!compact && job.message && <div className="m" style={{ fontSize: 13, marginTop: 4 }}>{job.message}</div>}
      {live && (
        <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
          {job.state === 'paused' ? (
            <button className="btn sm pri" onClick={() => void jobAction(job.id, 'resume')}>Resume</button>
          ) : (
            <button className="btn sm" onClick={() => void jobAction(job.id, 'pause')}>Pause</button>
          )}
          <button className="btn sm" onClick={() => void jobAction(job.id, 'cancel')}>Cancel</button>
        </div>
      )}
      {job.state === 'error' && <div className="err" style={{ marginTop: 10 }}>{job.error}</div>}
    </div>
  );
}
