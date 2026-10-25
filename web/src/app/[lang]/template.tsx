import type { ReactNode } from "react";

/** A template remounts on every navigation, which replays the page-enter animation (globals.css). */
export default function Template({ children }: { children: ReactNode }) {
  return <div className="page-enter">{children}</div>;
}
