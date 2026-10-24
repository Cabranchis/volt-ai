import { Database, Globe, Workflow } from "lucide-react";
import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { getDictionary } from "@/lib/i18n/dictionaries";
import { REPO_URL } from "@/lib/site";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.about.title, description: dict.about.description };
}

const STACK = [
  "Python 3.12",
  "pandas",
  "pandera",
  "LightGBM",
  "statsmodels",
  "SHAP",
  "PostgreSQL",
  "Next.js 16",
  "TypeScript",
  "Tailwind CSS 4",
  "Apache ECharts",
  "Vercel AI SDK",
  "Gemini",
  "GitHub Actions",
];

export default async function AboutPage() {
  const dict = await getDictionary();
  const steps = [
    { Icon: Workflow, title: dict.about.pipeline, body: dict.about.pipelineBody },
    { Icon: Database, title: dict.about.database, body: dict.about.databaseBody },
    { Icon: Globe, title: dict.about.web, body: dict.about.webBody },
  ];

  return (
    <>
      <PageHeader title={dict.about.title} description={dict.about.description} />
      <div className="flex flex-col gap-6">
        <Panel title={dict.about.whatTitle}>
          <p className="max-w-[72ch] leading-relaxed text-pretty">{dict.about.what}</p>
        </Panel>

        <Panel title={dict.about.howTitle}>
          <ol className="grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3">
            {steps.map(({ Icon, title, body }) => (
              <li key={title} className="flex flex-col gap-2 bg-surface p-4">
                <Icon aria-hidden="true" size={20} strokeWidth={1.75} className="text-accent-ink" />
                <h3 className="font-semibold">{title}</h3>
                <p className="text-sm text-muted">{body}</p>
              </li>
            ))}
          </ol>
        </Panel>

        <div className="grid gap-6 lg:grid-cols-2">
          <Panel title={dict.about.sourcesTitle}>
            <ul className="flex list-disc flex-col gap-2 pl-5 text-sm leading-relaxed marker:text-faint">
              {dict.about.sources.map((source) => (
                <li key={source}>{source}</li>
              ))}
            </ul>
          </Panel>
          <Panel title={dict.about.careTitle}>
            <ul className="flex list-disc flex-col gap-2 pl-5 text-sm leading-relaxed marker:text-faint">
              {dict.about.care.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </Panel>
        </div>

        <Panel title={dict.about.stackTitle}>
          <ul className="flex flex-wrap gap-2">
            {STACK.map((item) => (
              <li key={item} className="rounded-full border border-line bg-surface-2 px-3 py-1 text-xs font-medium">
                {item}
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title={dict.about.authorTitle}>
          <p className="text-sm text-muted">{dict.about.authorBody}</p>
          {REPO_URL ? (
            <a
              href={REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-3 inline-block text-sm font-medium text-accent-ink underline underline-offset-4"
            >
              {dict.common.github}
            </a>
          ) : null}
        </Panel>
      </div>
    </>
  );
}
