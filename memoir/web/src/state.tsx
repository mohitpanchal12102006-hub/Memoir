import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, ApiError, type DupSummary, type Health, type Job, type ReviewCounts, type Source, type Summary, type TakeoutSet } from './api';

type Toast = { id: number; text: string; kind: 'info' | 'error' | 'ok' };

type AppState = {
  health: Health | null;
  summary: Summary | null;
  sources: Source[];
  sets: TakeoutSet[];
  jobs: Job[];
  active: Job | null;
  review: ReviewCounts | null;
  dups: DupSummary | null;
  toasts: Toast[];
  refresh: () => Promise<void>;
  refreshJobs: () => Promise<void>;
  startJob: (body: Record<string, unknown>) => Promise<Job | null>;
  jobAction: (id: string, action: 'pause' | 'resume' | 'cancel') => Promise<void>;
  toast: (text: string, kind?: Toast['kind']) => void;
  fail: (e: unknown) => void;
  exportOpen: boolean;
  setExportOpen: (v: boolean) => void;
};

const Ctx = createContext<AppState | null>(null);

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useApp must be used inside <AppProvider>');
  return v;
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [sets, setSets] = useState<TakeoutSet[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [review, setReview] = useState<ReviewCounts | null>(null);
  const [dups, setDups] = useState<DupSummary | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [exportOpen, setExportOpen] = useState(false);
  const nextId = useRef(1);
  const prevActive = useRef<string | null>(null);
  const activeRef = useRef<Job | null>(null);

  const toast = useCallback((text: string, kind: Toast['kind'] = 'info') => {
    const id = nextId.current++;
    setToasts((t) => [...t, { id, text, kind }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === 'error' ? 9000 : 4500);
  }, []);

  const fail = useCallback((e: unknown) => toast(e instanceof ApiError ? e.message : String(e), 'error'), [toast]);

  const refresh = useCallback(async () => {
    try {
      const [s, src, st, rv] = await Promise.all([
        api.get<Summary>('/api/summary'),
        api.get<Source[]>('/api/sources'),
        api.get<TakeoutSet[]>('/api/takeout-sets'),
        api.get<ReviewCounts>('/api/review/counts'),
      ]);
      setSummary(s);
      setSources(src);
      setSets(st);
      setReview(rv);
      if (activeRef.current?.type !== 'scan') api.get<DupSummary>('/api/duplicates/summary').then(setDups).catch(() => undefined);
    } catch (e) {
      if (e instanceof ApiError && e.status === 0) toast(e.message, 'error');
    }
  }, [toast]);

  const refreshJobs = useCallback(async () => {
    try {
      setJobs(await api.get<Job[]>('/api/jobs'));
    } catch {
      /* the next poll will retry */
    }
  }, []);

  useEffect(() => {
    api.get<Health>('/api/health').then(setHealth).catch(fail);
    void refresh();
    void refreshJobs();
  }, [refresh, refreshJobs, fail]);

  const active = useMemo(() => jobs.find((j) => ['running', 'paused', 'queued'].includes(j.state)) ?? null, [jobs]);
  activeRef.current = active;

  useEffect(() => {
    const every = active ? 1000 : 5000;
    const t = window.setInterval(() => {
      void refreshJobs();
      if (!active) void api.get<Source[]>('/api/sources').then(setSources).catch(() => undefined);
    }, every);
    return () => window.clearInterval(t);
  }, [active, refreshJobs]);

  useEffect(() => {
    const id = active?.id ?? null;
    if (prevActive.current && prevActive.current !== id) {
      const finished = jobs.find((j) => j.id === prevActive.current);
      void refresh();
      if (finished?.state === 'done') toast(`${finished.type === 'export' ? 'Export' : finished.type === 'similar' ? 'Similar-image search' : 'Scan'} finished.`, 'ok');
      else if (finished?.state === 'error') toast(finished.error ?? 'The job failed.', 'error');
      else if (finished?.state === 'cancelled') toast('Job cancelled.');
    }
    prevActive.current = id;
  }, [active, jobs, refresh, toast]);

  // while a scan runs, keep counts fresh
  useEffect(() => {
    if (!active || active.type !== 'scan') return;
    const t = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(t);
  }, [active, refresh]);

  const startJob = useCallback(
    async (body: Record<string, unknown>) => {
      try {
        const j = await api.post<Job>('/api/jobs', body);
        await refreshJobs();
        return j;
      } catch (e) {
        fail(e);
        return null;
      }
    },
    [refreshJobs, fail],
  );

  const jobAction = useCallback(
    async (id: string, action: 'pause' | 'resume' | 'cancel') => {
      try {
        await api.post(`/api/jobs/${id}/${action}`);
        await refreshJobs();
      } catch (e) {
        fail(e);
      }
    },
    [refreshJobs, fail],
  );

  const value: AppState = {
    health, summary, sources, sets, jobs, active, review, dups, toasts, refresh, refreshJobs, startJob, jobAction, toast, fail,
    exportOpen, setExportOpen,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
