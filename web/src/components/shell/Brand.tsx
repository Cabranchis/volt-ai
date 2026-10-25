import { Zap } from "lucide-react";
import Link from "next/link";
import type { Locale } from "@/lib/i18n/config";

export function Brand({ locale, name }: { locale: Locale; name: string }) {
  return (
    <Link href={`/${locale}`} className="flex min-h-11 items-center gap-2.5 rounded-lg" aria-label={name}>
      <span className="grid size-8 place-items-center rounded-lg bg-accent text-on-accent">
        <Zap aria-hidden="true" size={18} strokeWidth={2.25} />
      </span>
      <span className="text-lg font-semibold tracking-tight">{name}</span>
    </Link>
  );
}
