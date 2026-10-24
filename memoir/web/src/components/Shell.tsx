import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useApp } from '../state';
import { ExportDialog } from './ExportDialog';
import { JobProgress } from './JobProgress';
import { SceneDefs } from './Scenes';
import { Toasts } from './Toasts';

const NUM: Record<string, string> = { '/': '01', '/timeline': '02', '/review': '03', '/duplicates': '04' };

export function Shell() {
  const { sources, review, dups, active, health, setExportOpen } = useApp();
  const loc = useLocation();
  const offline = sources.filter((s) => !s.online).length;
  const showBar = active && !(loc.pathname === '/' && active.type === 'scan');
  return (
    <div className="shell">
      <SceneDefs />
      <div className="num" aria-hidden="true">{NUM[loc.pathname] ?? ''}</div>
      <header className="bar">
        <NavLink to="/" className="logo">Memoir</NavLink>
        <nav className="nav" aria-label="Main">
          <NavLink to="/" end className={({ isActive }) => `nv${isActive ? ' active' : ''}`}>Upload</NavLink>
          <NavLink to="/timeline" className={({ isActive }) => `nv${isActive ? ' active' : ''}`}>Timeline</NavLink>
          <NavLink to="/review" className={({ isActive }) => `nv${isActive ? ' active' : ''}`}>Needs review{review && review.all > 0 ? <b>{review.all}</b> : null}</NavLink>
          <NavLink to="/duplicates" className={({ isActive }) => `nv${isActive ? ' active' : ''}`}>Duplicates{dups && dups.exact.groups > 0 ? <b>{dups.exact.groups}</b> : null}</NavLink>
        </nav>
        <div className="bar-r">
          {offline > 0 && <NavLink to="/" className="pill">{offline} {offline === 1 ? 'drive' : 'drives'} offline</NavLink>}
          <button className="btn pri" onClick={() => setExportOpen(true)}>Export</button>
        </div>
      </header>
      {health && !health.exiftool && (
        <div className="banner warn" role="alert" style={{ marginTop: 20 }}>
          <span>exiftool was not found. It is required to read and write capture dates. Install it from exiftool.org, then restart Memoir.</span>
        </div>
      )}
      <main className="page" key={loc.pathname}>
        <Outlet />
      </main>
      {showBar && active && (
        <div className="jobbar"><JobProgress job={active} compact /></div>
      )}
      <Toasts />
      <ExportDialog />
    </div>
  );
}
