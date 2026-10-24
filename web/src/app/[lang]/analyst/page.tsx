import type { Metadata } from "next";
import { ChatPanel } from "@/components/analyst/ChatPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { getDictionary, getLocale } from "@/lib/i18n/dictionaries";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.analyst.title, description: dict.analyst.description };
}

export default async function AnalystPage() {
  const locale = await getLocale();
  const dict = await getDictionary();

  return (
    <>
      <PageHeader title={dict.analyst.title} description={dict.analyst.description} />
      <div className="max-w-3xl">
        <ChatPanel locale={locale} dict={dict.analyst} />
      </div>
    </>
  );
}
