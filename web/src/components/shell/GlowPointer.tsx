"use client";

import { useEffect } from "react";

const GLOW = ".glow, .btn-glass, .btn-primary";
/** Time constant of the easing, in ms: the glow trails the pointer by about this much. */
const TAU = 70;

interface Glow {
  edge: number;
  angle: number;
  x: number;
  y: number;
  target: { edge: number; angle: number; x: number; y: number };
}

const shortestTurn = (from: number, to: number) => ((((to - from) % 360) + 540) % 360) - 180;

/**
 * One pointer listener for every glowing surface (the border glow in globals.css). For the pointer's
 * element and each glowing ancestor it eases how close the pointer is to the edge, the angle from the
 * centre and the pointer's position inside the element, one write per frame. The values glide towards
 * the pointer and fade out when it leaves, so the glow never jumps. Touch devices never hover, so
 * they skip it.
 */
export function GlowPointer() {
  useEffect(() => {
    if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;
    let stop = () => {};
    let timer = 0;
    // Styles written before React hydrates a surface make its server HTML differ from the client, so
    // the listener starts once the page has loaded and hydration has had a moment to finish.
    const start = () => {
      timer = window.setTimeout(() => (stop = listen()), 500);
    };
    if (document.readyState === "complete") start();
    else window.addEventListener("load", start, { once: true });
    return () => {
      window.removeEventListener("load", start);
      window.clearTimeout(timer);
      stop();
    };
  }, []);
  return null;
}

function listen(): () => void {
    const glows = new Map<HTMLElement, Glow>();
    let frame = 0;
    let last = 0;
    let pointer: PointerEvent | null = null;

    const aim = () => {
      const lit = new Set<HTMLElement>();
      if (pointer && pointer.target instanceof Element) {
        for (
          let el = pointer.target.closest<HTMLElement>(GLOW);
          el;
          el = el.parentElement?.closest<HTMLElement>(GLOW) ?? null
        ) {
          const rect = el.getBoundingClientRect();
          if (rect.width === 0 || rect.height === 0) continue;
          const x = pointer.clientX - rect.left;
          const y = pointer.clientY - rect.top;
          const dx = x - rect.width / 2;
          const dy = y - rect.height / 2;
          const kx = dx === 0 ? Infinity : rect.width / 2 / Math.abs(dx);
          const ky = dy === 0 ? Infinity : rect.height / 2 / Math.abs(dy);
          const edge = Math.min(Math.max(1 / Math.min(kx, ky), 0), 1) * 100;
          const angle = (Math.atan2(dy, dx) * 180) / Math.PI + 90;
          let glow = glows.get(el);
          if (!glow) {
            // First touch: start from where the pointer is, with the glow off, so it fades in.
            glow = { edge: 0, angle, x, y, target: { edge, angle, x, y } };
            glows.set(el, glow);
          }
          glow.target = { edge, angle, x, y };
          lit.add(el);
        }
      }
      for (const [el, glow] of glows) if (!lit.has(el)) glow.target.edge = 0;
    };

    const tick = (now: number) => {
      frame = 0;
      const k = 1 - Math.exp(-Math.min(now - last, 64) / TAU);
      last = now;
      let moving = false;
      for (const [el, glow] of glows) {
        const t = glow.target;
        glow.edge += (t.edge - glow.edge) * k;
        glow.angle += shortestTurn(glow.angle, t.angle) * k;
        glow.x += (t.x - glow.x) * k;
        glow.y += (t.y - glow.y) * k;
        el.style.setProperty("--edge-proximity", glow.edge.toFixed(2));
        el.style.setProperty(
          "--cursor-angle",
          `${((glow.angle + 360) % 360).toFixed(1)}deg`,
        );
        el.style.setProperty("--mx", `${glow.x.toFixed(1)}px`);
        el.style.setProperty("--my", `${glow.y.toFixed(1)}px`);
        if (t.edge === 0 && glow.edge < 0.05) {
          el.style.setProperty("--edge-proximity", "0");
          glows.delete(el);
        } else if (
          Math.abs(t.edge - glow.edge) > 0.05 ||
          Math.abs(shortestTurn(glow.angle, t.angle)) > 0.1
        ) {
          moving = true;
        }
      }
      if (moving || pointer) frame = requestAnimationFrame(tick);
    };
    const wake = () => {
      if (!frame) {
        last = performance.now();
        frame = requestAnimationFrame(tick);
      }
    };

    const onMove = (e: PointerEvent) => {
      pointer = e;
      aim();
      wake();
    };
    const onLeave = () => {
      pointer = null;
      aim();
      wake();
    };
    // Scrolling moves surfaces under a still pointer.
    const onScroll = () => {
      if (pointer) {
        aim();
        wake();
      }
    };

    document.addEventListener("pointermove", onMove, { passive: true });
    document.documentElement.addEventListener("pointerleave", onLeave);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      document.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("pointerleave", onLeave);
      window.removeEventListener("scroll", onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
}
