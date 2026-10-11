import { Bell, Camera, ClipboardList, FileText, Mail } from "lucide-react";
import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import scenes from "../content/tryScenes.json";
import { formatDuration, SEVERITY_STYLES } from "../lib/format";
import { bilingual, useLang, useText } from "../lib/i18n";
import { incidentTitle, joinList, severityLabel } from "../lib/terms";
import type { Severity } from "../api/types";
import { Flourish } from "./edition";

// "Try it yourself" on the product page: real detections by SiteSentry's own model on public test photos, and the
// incident, alert and report the system makes from them (src/content/tryScenes.json, built offline from the model
// and ai_reporting's template). Works without the console, so the page shows the product even when the demo is off.

type Scene = (typeof scenes)[number];

const TEXT = bilingual(
  {
    title: "Try it yourself",
    lead: "Pick a photo from a construction site. This is what SiteSentry sees in it, what it records, and what the supervisor gets.",
    pick: "Pick a photo",
    scenes: { vest: "Formwork", hardhat: "Site entrance", machinery: "Earthworks" } as Record<string, string>,
    looking: "Looking…",
    steps: {
      seen: "1 · What the camera sees",
      recorded: "2 · What gets recorded",
      told: "3 · What the supervisor gets",
      report: "4 · The written report",
    },
    found: (things: string) => `Found: ${things}.`,
    lasted: (d: string) => `lasted ${d}`,
    email: {
      from: "SiteSentry alerts",
      subject: (what: string, where: string) => `${what} at ${where}`,
      sentence: (what: string, where: string) => `${what} at ${where}, just now. The photo and a short video are attached.`,
      whatNow: "What to do now",
    },
    showReport: "Show the full report",
    reportNote: "Written here by the built-in template; with AI switched on, Claude writes it from the same facts.",
    next: "Then the supervisor handles it in the console.",
    tour: "See the console",
    credit: "Photos: Roboflow “Construction Site Safety” dataset (CC BY 4.0), test images the model never trained on. Boxes: SiteSentry’s own model.",
  },
  {
    title: "جرّبه بنفسك",
    lead: "اختر صورة من موقع بناء. هذا ما يراه SiteSentry فيها، وما يسجّله، وما يصل إلى المشرف.",
    pick: "اختر صورة",
    scenes: { vest: "القوالب الخشبية", hardhat: "مدخل الموقع", machinery: "أعمال الحفر" },
    looking: "جارٍ الفحص…",
    steps: {
      seen: "١ · ما تراه الكاميرا",
      recorded: "٢ · ما يُسجَّل",
      told: "٣ · ما يصل إلى المشرف",
      report: "٤ · التقرير المكتوب",
    },
    found: (things: string) => `رُصد: ${things}.`,
    lasted: (d: string) => `استمرت ${d}`,
    email: {
      from: "تنبيهات SiteSentry",
      subject: (what: string, where: string) => `${what} في ${where}`,
      sentence: (what: string, where: string) => `${what} في ${where} قبل لحظات. الصورة ومقطع قصير مرفقان.`,
      whatNow: "ما العمل الآن",
    },
    showReport: "عرض التقرير كاملًا",
    reportNote: "كتبه هنا النموذج الثابت؛ وعند تشغيل الذكاء الاصطناعي يكتبه Claude من الحقائق نفسها.",
    next: "ثم يتعامل المشرف معها في لوحة التحكم.",
    tour: "شاهد لوحة التحكم",
    credit: "الصور: مجموعة بيانات Roboflow «Construction Site Safety» (CC BY 4.0)، صور اختبار لم يتدرب عليها النموذج. المربعات: نموذج SiteSentry نفسه.",
  },
);

const PLACE_AR: Record<string, string> = { "Formwork area": "منطقة القوالب", "Site entrance": "مدخل الموقع", Earthworks: "أعمال الحفر" };

function usePrefersReducedMotion() {
  const [reduce] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
  return reduce;
}

/** The photo with the model's boxes, drawn after a short scan so it reads as "looking, then finding". */
function Photo({ scene, lang, ready }: { scene: Scene; lang: "en" | "ar"; ready: boolean }) {
  const t = useText(TEXT);
  return (
    <div className="relative overflow-hidden rounded-2xl bg-ink shadow-2xl shadow-ink/30" style={{ aspectRatio: `${scene.width} / ${scene.height}` }}>
      <img src={scene.image} alt="" className="absolute inset-0 h-full w-full object-cover" />
      {!ready && (
        <>
          <div className="try-scan absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-transparent via-amber-300/35 to-transparent" aria-hidden />
          <span className="absolute start-3 top-3 rounded-full bg-ink/70 px-3 py-1 text-xs font-semibold text-paper">{t.looking}</span>
        </>
      )}
      {ready &&
        scene.boxes.map((b, n) => {
          const [x1, y1, x2, y2] = b.box;
          return (
            <div
              key={n}
              className={`try-box absolute rounded-[3px] border-2 ${b.bad ? "border-red-600" : "border-emerald-500"}`}
              style={{ left: `${x1 * 100}%`, top: `${y1 * 100}%`, width: `${(x2 - x1) * 100}%`, height: `${(y2 - y1) * 100}%`, animationDelay: `${n * 120}ms` }}
            >
              <span
                // a box at the top edge gets its label inside, or the photo's edge would cut it off; labels sit at the
                // box's left in both languages, because the photo itself doesn't flip
                className={`absolute ${y1 < 0.06 ? "top-0 rounded-br-[3px]" : "-top-6 rounded-t-[3px]"} left-[-2px] px-1.5 py-0.5 text-[11px] font-semibold whitespace-nowrap text-white ${
                  b.bad ? "bg-red-700" : "bg-emerald-700"
                }`}
                dir={lang === "ar" ? "rtl" : "ltr"}
              >
                {b.label[lang]}
              </span>
            </div>
          );
        })}
    </div>
  );
}

function Step({ icon, title, children, delay }: { icon: React.ReactNode; title: string; children: React.ReactNode; delay: number }) {
  return (
    <div className="try-step rounded-2xl bg-white p-5 ring-1 ring-ink/[0.08]" style={{ animationDelay: `${delay}ms` }}>
      <p className="flex items-center gap-2 text-xs font-semibold tracking-wide text-ink/70 uppercase">
        {icon}
        {title}
      </p>
      <div className="mt-2">{children}</div>
    </div>
  );
}

export function TryIt() {
  const t = useText(TEXT);
  const { lang } = useLang();
  const reduce = usePrefersReducedMotion();
  const [index, setIndex] = useState(0);
  const [ready, setReady] = useState(reduce);
  const scene = scenes[index];

  // "look" at the new photo for a moment before showing what was found
  useEffect(() => {
    if (reduce) return;
    setReady(false);
    const timer = window.setTimeout(() => setReady(true), 1300);
    return () => window.clearTimeout(timer);
  }, [index, reduce]);

  const what = incidentTitle({ event_type: scene.event_type, metadata: { missing_equipment: scene.missing } });
  const place = lang === "ar" ? (PLACE_AR[scene.location] ?? scene.location) : scene.location;
  const found = joinList([...new Set(scene.boxes.map((b) => b.label[lang]))]);
  const actions = scene.actions[lang];
  const severity = scene.severity as Severity;

  return (
    <section id="try" className="paper-grain relative z-10 scroll-mt-16 bg-paper text-ink" data-surface="light">
      <div className="px-5 py-20 sm:px-8 sm:py-28 lg:pe-12 lg:ps-[17rem]">
        <div className="max-w-3xl">
          <Flourish text={t.title} as="h2" />
          <p className="mt-6 max-w-2xl text-lg leading-8 text-ink/70">{t.lead}</p>
        </div>

        <div
          className="mt-10 flex flex-wrap gap-3"
          role="tablist"
          aria-label={t.pick}
          // arrow keys move between photos (reversed in Arabic, where "next" is to the left), like any tab list
          onKeyDown={(e) => {
            const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
            if (!step) return;
            e.preventDefault();
            const next = (index + (lang === "ar" ? -step : step) + scenes.length) % scenes.length;
            setIndex(next);
            (e.currentTarget.children[next] as HTMLElement | undefined)?.focus();
          }}
        >
          {scenes.map((s, n) => (
            <button
              key={s.key}
              role="tab"
              aria-selected={n === index}
              tabIndex={n === index ? 0 : -1}
              onClick={() => setIndex(n)}
              className={`group flex items-center gap-3 rounded-full py-1.5 ps-1.5 pe-4 text-sm font-semibold transition ${
                n === index ? "bg-ink text-paper" : "bg-white text-ink/70 ring-1 ring-ink/10 hover:text-ink"
              }`}
            >
              <img src={s.image} alt="" className="h-9 w-9 rounded-full object-cover" />
              {t.scenes[s.key]}
            </button>
          ))}
        </div>

        <div className="mt-8 grid gap-8 xl:grid-cols-[1.1fr_1fr] xl:items-start">
          <figure>
            <Photo scene={scene} lang={lang} ready={ready} />
            <figcaption className="mt-3 text-xs leading-5 text-ink/60">{t.credit}</figcaption>
          </figure>

          {/* keyed by scene, so the steps animate in again for each photo */}
          <div key={`${scene.key}-${ready}`} className="space-y-4" aria-live="polite">
            {ready && (
              <>
                <Step icon={<Camera className="h-4 w-4" />} title={t.steps.seen} delay={0}>
                  <p className="text-[15px] text-ink/75">{t.found(found)}</p>
                </Step>
                <Step icon={<ClipboardList className="h-4 w-4" />} title={t.steps.recorded} delay={150}>
                  <p className="inline-flex items-center gap-1.5 text-xs font-semibold text-ink/60">
                    <span className={`h-2 w-2 rounded-full ${SEVERITY_STYLES[severity].dot}`} />
                    {severityLabel(severity)}
                  </p>
                  <p className="mt-1 font-display text-xl font-semibold">{what}</p>
                  <p className="text-sm text-ink/65">
                    {place} · cam_01 · {t.lasted(formatDuration(scene.duration))}
                  </p>
                </Step>
                <Step icon={<Bell className="h-4 w-4" />} title={t.steps.told} delay={300}>
                  <div className="rounded-xl bg-paper p-4">
                    <p className="flex items-center gap-2 text-xs text-ink/65">
                      <Mail className="h-3.5 w-3.5" /> {t.email.from}
                    </p>
                    <p className="mt-1 font-semibold">{t.email.subject(what, place)}</p>
                    <p className="mt-2 text-[15px] leading-relaxed text-ink/75">{t.email.sentence(what, place)}</p>
                    <p className="mt-3 text-sm font-semibold">{t.email.whatNow}</p>
                    <ol className="mt-1 list-decimal space-y-1 ps-5 text-sm leading-relaxed text-ink/75">
                      {actions.slice(0, 2).map((a) => (
                        <li key={a}>{a}</li>
                      ))}
                    </ol>
                  </div>
                </Step>
                <Step icon={<FileText className="h-4 w-4" />} title={t.steps.report} delay={450}>
                  <details className="group">
                    <summary className="cursor-pointer text-sm font-semibold text-amber-700 hover:underline">{t.showReport}</summary>
                    <article className="report mt-3 max-h-80 overflow-auto text-sm leading-6 text-ink/75" dir={lang === "ar" ? "rtl" : "ltr"}>
                      <Markdown>{scene.report[lang]}</Markdown>
                    </article>
                    <p className="mt-2 text-xs text-ink/60">{t.reportNote}</p>
                  </details>
                </Step>
                <p className="try-step flex flex-wrap items-center gap-x-3 gap-y-1 ps-1 pt-2 text-[15px] text-ink/70" style={{ animationDelay: "600ms" }}>
                  {t.next}
                  <a href="#console" className="font-semibold text-amber-700 hover:underline">
                    {t.tour} <span className="flip-rtl inline-block">→</span>
                  </a>
                </p>
              </>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
