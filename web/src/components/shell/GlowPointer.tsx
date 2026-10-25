"use client";

import { useEffect } from "react";

const GLOW = ".glow, .btn-glass, .btn-primary";

/**
 * One pointer listener for every glowing surface (the border glow in globals.css). For the pointer's
 * element and each glowing ancestor it writes how close the pointer is to the edge and at what angle
 * from the centre, throttled to one write per frame. Touch devices never hover, so they skip it.
 */
export function GlowPointer() {
  useEffect(() => {
    if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;
    let frame = 0;
    let event: PointerEvent | null = null;

    const apply = () => {
      frame = 0;
      if (!event || !(event.target instanceof Element)) return;
      for (let el = event.target.closest<HTMLElement>(GLOW); el; el = el.parentElement?.closest<HTMLElement>(GLOW) ?? null) {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        const dx = event.clientX - rect.left - rect.width / 2;
        const dy = event.clientY - rect.top - rect.height / 2;
        const kx = dx === 0 ? Infinity : rect.width / 2 / Math.abs(dx);
        const ky = dy === 0 ? Infinity : rect.height / 2 / Math.abs(dy);
        const edge = Math.min(Math.max(1 / Math.min(kx, ky), 0), 1);
        const angle = (Math.atan2(dy, dx) * 180) / Math.PI + 90;
        el.style.setProperty("--edge-proximity", (edge * 100).toFixed(2));
        el.style.setProperty("--cursor-angle", `${((angle + 360) % 360).toFixed(1)}deg`);
      }
    };
    const onMove = (e: PointerEvent) => {
      event = e;
      if (!frame) frame = requestAnimationFrame(apply);
    };

    document.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      document.removeEventListener("pointermove", onMove);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);
  return null;
}
