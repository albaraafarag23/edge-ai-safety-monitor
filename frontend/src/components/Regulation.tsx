import { BookOpen, ExternalLink } from "lucide-react";
import type { Regulation } from "../api/types";
import { bilingual, useLang, useText } from "../lib/i18n";

const TEXT = bilingual(
  {
    clause: "clause",
    page: (n: number) => `page ${n}`,
    read: "Read the clause",
    pdf: "Official PDF",
    english: "",
  },
  {
    clause: "البند",
    page: (n: number) => `صفحة ${n}`,
    read: "اقرأ نص البند",
    pdf: "الملف الرسمي",
    english: "النص الأصلي بالإنجليزية",
  },
);

/**
 * The code-of-practice clauses a rule enforces (docs/regulations.md): document, clause and heading, the
 * clause's own words one click away, and a link to the official PDF. `compact` is the one-line form for
 * a rule's row in Safety rules; the full form is for an incident's page.
 */
export function Regulations({ items, compact = false }: { items: Regulation[]; compact?: boolean }) {
  const t = useText(TEXT);
  const { lang } = useLang();
  if (!items.length) return null;

  return (
    <ul className={compact ? "mt-1.5 space-y-1" : "space-y-4"}>
      {items.map((c, n) => {
        const heading = (lang === "ar" && c.heading_ar) || c.heading;
        const where = [c.document, `${t.clause} ${c.clause}`].join(" · ");
        return (
          <li key={`${c.document}-${c.clause}-${n}`} className={compact ? "text-xs text-ink/60" : "text-sm text-ink/80"}>
            <details className="group">
              <summary className="flex cursor-pointer list-none items-start gap-1.5 [&::-webkit-details-marker]:hidden">
                <BookOpen className={`mt-0.5 shrink-0 text-ink/45 ${compact ? "h-3 w-3" : "h-4 w-4"}`} aria-hidden />
                <span>
                  <span className="font-medium text-ink/80">{where}</span>
                  {heading && <span> · {heading}</span>}
                  {c.page ? <span className="text-ink/45"> · {t.page(c.page)}</span> : null}
                  <span className="ms-1.5 text-ink/45 underline decoration-ink/20 underline-offset-2 group-open:hidden print:hidden">{t.read}</span>
                </span>
              </summary>
              {c.text && (
                <blockquote
                  dir="ltr"
                  lang="en"
                  className={`mt-2 border-s-2 border-ink/15 ps-3 text-start font-serif italic leading-relaxed text-ink/75 ${compact ? "text-[13px]" : "text-[15px]"}`}
                >
                  {c.text}
                </blockquote>
              )}
              <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 ps-3 text-xs text-ink/50">
                {lang === "ar" && c.text && <span>{t.english}</span>}
                {c.title && <span>{c.title}</span>}
                {c.url && (
                  <a href={c.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline decoration-ink/25 underline-offset-2 hover:text-ink print:no-underline">
                    {t.pdf} <ExternalLink className="h-3 w-3" aria-hidden />
                  </a>
                )}
              </p>
            </details>
          </li>
        );
      })}
    </ul>
  );
}
