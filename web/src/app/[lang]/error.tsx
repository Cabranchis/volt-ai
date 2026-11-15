"use client";

import { useParams } from "next/navigation";
import { ErrorScreen } from "@/components/ui/ErrorScreen";
import { errorLocale } from "@/lib/i18n/errors";

/** A page below the layout failed to read its data. The navigation around it stays usable. */
export default function LangError({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  const { lang } = useParams<{ lang?: string }>();
  // retry() fetches the page again; reset() would only re-render the payload that already failed.
  return <ErrorScreen locale={errorLocale(lang)} retry={retry} />;
}
