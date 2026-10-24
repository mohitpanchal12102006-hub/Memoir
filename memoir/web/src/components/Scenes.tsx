import type { ReactNode } from 'react';

const G = (id: string, a: string, b: string): ReactNode => (
  <>
    <defs>
      <linearGradient id={`g-${id}`} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor={a} />
        <stop offset="1" stopColor={b} />
      </linearGradient>
    </defs>
    <rect width="300" height="400" fill={`url(#g-${id})`} />
  </>
);

/** Drawn landscape placeholders. Real photos dropped into /img/ replace them automatically. */
export function SceneDefs() {
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true">
      <symbol id="sc-a" viewBox="0 0 300 400" preserveAspectRatio="xMidYMid slice">
        {G('a', '#d9c7b8', '#8fa3b5')}
        <circle cx="210" cy="150" r="34" fill="#f3e4cf" opacity=".9" />
        <path d="M0 260L70 190L120 240L190 160L300 270V400H0Z" fill="#6d8195" opacity=".55" />
        <path d="M0 310L90 240L150 290L230 220L300 300V400H0Z" fill="#4d6074" opacity=".8" />
        <path d="M0 370L100 320L200 360L300 330V400H0Z" fill="#2f3f4f" />
        <rect y="250" width="300" height="60" fill="#fff" opacity=".12" />
      </symbol>
      <symbol id="sc-b" viewBox="0 0 300 400" preserveAspectRatio="xMidYMid slice">
        {G('b', '#b7c6d3', '#ecdcc8')}
        <path d="M0 215L60 170L110 205L170 150L240 200L300 175V215H0Z" fill="#7b8fa0" />
        <rect y="215" width="300" height="185" fill="#a9b9c4" />
        <path d="M0 215L60 260L110 225L170 280L240 230L300 255V215Z" fill="#6f8393" opacity=".5" />
        <path d="M20 300h80M150 330h110M60 360h90" stroke="#fff" strokeOpacity=".35" strokeWidth="2" />
      </symbol>
      <symbol id="sc-c" viewBox="0 0 300 400" preserveAspectRatio="xMidYMid slice">
        {G('c', '#9fb0a5', '#e4e8e1')}
        <path d="M0 400L25 230L50 400ZM40 400L70 210L100 400ZM90 400L120 240L150 400ZM140 400L170 220L200 400ZM190 400L225 235L260 400ZM240 400L275 215L300 400Z" fill="#7f958b" opacity=".6" />
        <rect y="260" width="300" height="60" fill="#fff" opacity=".2" />
        <path d="M-10 400L30 280L70 400ZM60 400L110 260L160 400ZM150 400L205 285L260 400ZM230 400L285 270L330 400Z" fill="#2f453b" />
      </symbol>
      <symbol id="sc-d" viewBox="0 0 300 400" preserveAspectRatio="xMidYMid slice">
        {G('d', '#f3dfc0', '#dba776')}
        <circle cx="220" cy="120" r="30" fill="#fbefd6" />
        <path d="M0 260C80 220 140 280 300 240V400H0Z" fill="#c98a5a" />
        <path d="M0 320C100 280 180 350 300 300V400H0Z" fill="#a8693f" />
        <path d="M0 370C90 340 200 390 300 355V400H0Z" fill="#7c4a2c" />
      </symbol>
      <symbol id="sc-e" viewBox="0 0 300 400" preserveAspectRatio="xMidYMid slice">
        {G('e', '#1e2a3a', '#4a5d73')}
        <circle cx="90" cy="120" r="44" fill="#efe9d8" opacity=".12" />
        <circle cx="90" cy="120" r="22" fill="#efe9d8" />
        <circle cx="210" cy="70" r="1.5" fill="#fff" />
        <circle cx="250" cy="130" r="1.2" fill="#fff" />
        <circle cx="170" cy="40" r="1.2" fill="#fff" />
        <path d="M0 280C90 230 180 300 300 250V400H0Z" fill="#26384a" />
        <path d="M0 340C110 300 190 360 300 320V400H0Z" fill="#17232f" />
      </symbol>
      <symbol id="sc-f" viewBox="0 0 300 400" preserveAspectRatio="xMidYMid slice">
        {G('f', '#f4d9cf', '#c4cfdc')}
        <circle cx="150" cy="238" r="40" fill="#f9e6d2" />
        <rect y="240" width="300" height="160" fill="#7f9db5" />
        <path d="M110 262h80M125 282h50M95 306h110" stroke="#f9e6d2" strokeOpacity=".55" strokeWidth="2" />
      </symbol>
      <symbol id="sc-p" viewBox="0 0 1200 200" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id="g-p" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#cdbfb2" />
            <stop offset="1" stopColor="#8fa3b5" />
          </linearGradient>
        </defs>
        <rect width="1200" height="200" fill="url(#g-p)" />
        <circle cx="820" cy="80" r="34" fill="#f3e4cf" opacity=".85" />
        <path d="M0 150L180 70L300 120L470 50L640 130L800 90L1000 140L1200 80V200H0Z" fill="#6d8195" opacity=".6" />
        <path d="M0 185L200 120L380 160L560 110L760 170L980 125L1200 170V200H0Z" fill="#3f5266" />
        <rect y="120" width="1200" height="40" fill="#fff" opacity=".1" />
      </symbol>
    </svg>
  );
}

export type SceneKey = 'a' | 'b' | 'c' | 'd' | 'e' | 'f' | 'p';

export function Scene({ k, className }: { k: SceneKey; className?: string }) {
  const vb = k === 'p' ? '0 0 1200 200' : '0 0 300 400';
  const [w, h] = k === 'p' ? [1200, 200] : [300, 400];
  return (
    <svg className={className} viewBox={vb} preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <use href={`#sc-${k}`} width={w} height={h} />
    </svg>
  );
}
