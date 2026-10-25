"use client";

import { Menu, X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import type { Dictionary } from "@/lib/i18n/en";

interface Props {
  labels: Dictionary["nav"];
  brand: ReactNode;
  children: ReactNode;
}

/** Below 1024 px the sidebar becomes a modal dialog, which gives focus trapping and Escape for free. */
export function MobileNav({ labels, brand, children }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const pathname = usePathname();

  useEffect(() => {
    dialogRef.current?.close();
  }, [pathname]);

  return (
    <>
      <button
        type="button"
        aria-label={labels.openMenu}
        onClick={() => dialogRef.current?.showModal()}
        className="grid size-11 place-items-center rounded-lg border border-line bg-surface"
      >
        <Menu aria-hidden="true" size={20} strokeWidth={1.75} />
      </button>
      <dialog
        ref={dialogRef}
        aria-label={labels.label}
        onClick={(event) => {
          if (event.target === dialogRef.current) dialogRef.current?.close();
        }}
        className="m-0 h-dvh max-h-none w-[min(20rem,88vw)] border-r border-line bg-surface-2 p-0 text-ink backdrop:bg-black/50"
      >
        <div className="flex h-full flex-col gap-6 p-4">
          <div className="flex items-center justify-between">
            {brand}
            <button
              type="button"
              aria-label={labels.closeMenu}
              onClick={() => dialogRef.current?.close()}
              className="grid size-11 place-items-center rounded-lg border border-line bg-surface"
            >
              <X aria-hidden="true" size={20} strokeWidth={1.75} />
            </button>
          </div>
          {children}
        </div>
      </dialog>
    </>
  );
}
