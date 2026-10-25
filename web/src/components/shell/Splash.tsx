/**
 * The first-visit intro: the logo's bolt draws itself, discharges two energy rings along a current
 * line, and the name and tagline settle in. Pure CSS (globals.css), so it needs no hydration; the
 * theme script marks html[data-splash="done"] once a tab has seen it, so it never replays there.
 */
const BOLT =
  "M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z";

export function Splash({ name, tagline }: { name: string; tagline: string }) {
  const letters = Array.from(name);
  return (
    <div className="splash" aria-hidden="true">
      <div className="splash-stage">
        <div className="splash-mark">
          <span className="splash-line" />
          <span className="splash-ring" />
          <span className="splash-ring splash-ring-2" />
          <span className="splash-tile">
            <svg viewBox="0 0 24 24" className="splash-bolt" fill="none" strokeLinecap="round" strokeLinejoin="round">
              <path d={BOLT} pathLength={1} />
            </svg>
          </span>
        </div>
        <p className="splash-name">
          {letters.map((char, i) => (
            <span key={i} className={i >= letters.length - 2 ? "splash-accent" : undefined}>
              <span style={{ "--i": i } as React.CSSProperties}>{char}</span>
            </span>
          ))}
        </p>
        <p className="splash-tagline">{tagline}</p>
      </div>
    </div>
  );
}
