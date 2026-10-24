import { useState, type ReactNode } from 'react';
import { Scene, type SceneKey } from './Scenes';

const EXT = ['jpg', 'jpeg', 'png', 'webp', 'avif'];

/** Shows /img/<name>.<ext> if you added one, otherwise a drawn landscape. */
export function HeroImage({ name, scene, alt, className, style, children }: {
  name: string; scene: SceneKey; alt: string; className?: string; style?: React.CSSProperties; children?: ReactNode;
}) {
  const [i, setI] = useState(0);
  const failed = i >= EXT.length;
  return (
    <div className={`imgbox ${className ?? ''}`} style={style}>
      {failed ? (
        <Scene k={scene} className="pan" />
      ) : (
        <img className="pan" src={`/img/${name}.${EXT[i]}`} alt={alt} onError={() => setI(i + 1)} />
      )}
      {children}
    </div>
  );
}

export function Atmosphere({ sunLeft, sunTop }: { sunLeft: string; sunTop: number }) {
  return (
    <>
      <div className="sun" style={{ left: sunLeft, top: sunTop }} />
      <div className="mist" />
      <div className="mist" style={{ bottom: '2%', animationDuration: '21s', animationDirection: 'alternate-reverse' }} />
      {[70, 96, 54].map((t, n) => (
        <svg key={t} className="bird" style={{ top: t, animationDelay: `${-5 * n}s` }} width="26" height="10" viewBox="0 0 26 10" aria-hidden="true">
          <path d="M1 8Q7 0 13 6Q19 0 25 8" fill="none" stroke="#fff" strokeWidth="1.2" />
        </svg>
      ))}
    </>
  );
}
