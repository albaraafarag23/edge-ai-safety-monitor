/** The overseer's home (one plain sentence, what needs you, every company), the boxes list and the security log. */
import { useQuery } from "@tanstack/react-query";
import { Link, Navigate } from "react-router-dom";
import { bilingual, useLang, useText } from "../../lib/i18n";
import { get, type Box, type CompanySummary, type LogEntry, type Overview } from "../api";
import { Dot, Header, Panel, useLocale, useMe, when } from "../shell";
import { ApprovalCards } from "./Devices";

const TEXT = bilingual(
  {
    noBoxesYet: "No boxes have connected yet.",
    boxesFine: (fine: number, all: number) => `${fine} of ${all} boxes are fine.`,
    allQuiet: "Nothing needs you.",
    needsYou: (approvals: number, silent: number) => {
      const parts = [];
      if (silent) parts.push(`${silent} box${silent === 1 ? " is" : "es are"} silent`);
      if (approvals) parts.push(`${approvals} device${approvals === 1 ? " is" : "s are"} waiting for your approval`);
      return parts.length ? `${parts.join(" and ")}.` : "Nothing needs you right now.";
    },
    needs: "Needs you",
    companies: "Companies",
    allCompanies: "All companies",
    sites: (n: number) => `${n} site${n === 1 ? "" : "s"}`,
    people: (n: number) => `${n} ${n === 1 ? "person" : "people"}`,
    boxes: (n: number) => `${n} box${n === 1 ? "" : "es"}`,
    suspended: "Suspended",
    noCompanies: "No companies yet. Add the first one under Companies.",
    footage: "Health only. Footage and incidents never leave the site.",
    boxesTitle: "Boxes",
    boxesLead: "Each site's Jetson, as it last reported. Boxes connect to the portal in the next step of the build; until then this list stays empty.",
    head: { box: "Box", where: "Company · site", status: "Status", last: "Last check-in" },
    status: { fine: "Fine", silent: "Silent", waiting: "Waiting to be assigned", blocked: "Blocked" },
    unassigned: "Not assigned",
    logTitle: "Security log",
    logLead: "Every sign-in, approval and change, newest first.",
    chainOk: (n: number) => `All ${n} entries check out: none were changed or removed.`,
    chainBroken: (id: number) => `Warning: the log was changed at entry ${id}. Tell SiteSentry at once.`,
    kicker: "Overseer",
  },
  {
    noBoxesYet: "لم يتصل أي جهاز بعد.",
    boxesFine: (fine: number, all: number) => `${fine} من ${all} أجهزة بخير.`,
    allQuiet: "لا شيء يحتاج إليك.",
    needsYou: (approvals: number, silent: number) => {
      const parts = [];
      if (silent) parts.push(silent === 1 ? "جهاز صامت" : `${silent} أجهزة صامتة`);
      if (approvals) parts.push(approvals === 1 ? "جهاز دخول ينتظر موافقتك" : `${approvals} أجهزة دخول تنتظر موافقتك`);
      return parts.length ? `${parts.join("، و")}.` : "لا شيء يحتاج إليك الآن.";
    },
    needs: "يحتاج إليك",
    companies: "الشركات",
    allCompanies: "كل الشركات",
    sites: (n: number) => `${n} ${n === 1 ? "موقع" : n === 2 ? "موقعان" : "مواقع"}`,
    people: (n: number) => `${n} ${n === 1 ? "شخص" : "أشخاص"}`,
    boxes: (n: number) => `${n} ${n === 1 ? "جهاز" : "أجهزة"}`,
    suspended: "موقوفة",
    noCompanies: "لا توجد شركات بعد. أضف أولها من صفحة الشركات.",
    footage: "الحالة فقط. لا تغادر اللقطات والحوادث الموقع.",
    boxesTitle: "الأجهزة",
    boxesLead: "جهاز Jetson في كل موقع، كما أبلغ آخر مرة. تتصل الأجهزة بالبوابة في الخطوة التالية من البناء، وحتى ذلك الحين تبقى القائمة فارغة.",
    head: { box: "الجهاز", where: "الشركة · الموقع", status: "الحالة", last: "آخر اتصال" },
    status: { fine: "بخير", silent: "صامت", waiting: "بانتظار التعيين", blocked: "محظور" },
    unassigned: "غير معيّن",
    logTitle: "سجل الأمان",
    logLead: "كل دخول وموافقة وتغيير، الأحدث أولًا.",
    chainOk: (n: number) => `كل السجلات (${n}) سليمة: لم يُغيَّر أو يُحذف شيء.`,
    chainBroken: (id: number) => `تحذير: تغيّر السجل عند الإدخال ${id}. أبلغ SiteSentry فورًا.`,
    kicker: "المشرف العام",
  },
);

export function Home() {
  const me = useMe();
  if (me.data && me.data.role !== "overseer") return <Navigate to={`/companies/${me.data.company?.id}`} replace />;
  return <OverseerHome />;
}

function OverseerHome() {
  const t = useText(TEXT);
  const { lang } = useLang();
  const overview = useQuery({ queryKey: ["overview"], queryFn: () => get<Overview>("/overview"), refetchInterval: 30_000 });
  const companies = useQuery({ queryKey: ["companies"], queryFn: () => get<CompanySummary[]>("/companies") });
  const o = overview.data;
  const today = new Date().toLocaleDateString(lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB",
    { weekday: "long", day: "numeric", month: "long" });

  return (
    <>
      <Header
        kicker={`${t.kicker} · ${today}`}
        title={!o ? "…" : o.boxes ? t.boxesFine(o.boxes_fine, o.boxes) : t.noBoxesYet}
        lead={o ? t.needsYou(o.approvals.length, o.silent.length) : undefined}
      />
      {o && o.approvals.length > 0 && (
        <section className="flex flex-col gap-3.5" aria-labelledby="needs">
          <h2 id="needs" className="font-display text-xl font-bold">{t.needs}</h2>
          <ApprovalCards items={o.approvals.slice(0, 6)} />
        </section>
      )}
      <Panel title={t.companies} note={<Link to="/companies" className="font-semibold underline">{t.allCompanies}</Link>}>
        {companies.data?.length === 0 && <p className="text-sm text-[#4a4439]">{t.noCompanies}</p>}
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {companies.data?.map((c) => (
            <li key={c.id}>
              <Link to={`/companies/${c.id}`} className="flex h-full flex-col gap-1.5 rounded-xl border border-[#e4ddd0] p-4 hover:border-ink">
                <span className="flex items-center gap-2 font-semibold">
                  <Dot tone={!c.active ? "off" : c.silent_boxes ? "bad" : "good"} /> <bdi>{c.name}</bdi>
                  {!c.active && <span className="text-xs font-semibold text-[#6b6355]">· {t.suspended}</span>}
                </span>
                <span className="text-[13px] text-[#4a4439]">{t.sites(c.sites)} · {t.people(c.people)} · {t.boxes(c.boxes)}</span>
              </Link>
            </li>
          ))}
        </ul>
      </Panel>
      <p className="text-[13px] text-[#6b6355]">{t.footage}</p>
    </>
  );
}

export function Boxes() {
  const t = useText(TEXT);
  const locale = useLocale();
  const boxes = useQuery({ queryKey: ["boxes"], queryFn: () => get<Box[]>("/boxes"), refetchInterval: 30_000 });
  const status = (b: Box) => b.status !== "approved" ? b.status : b.silent ? "silent" : "fine";
  const tone = { fine: "good", silent: "bad", waiting: "warn", blocked: "off" } as const;
  return (
    <>
      <Header title={t.boxesTitle} lead={t.boxesLead} />
      <Panel>
        {boxes.data?.length === 0 ? (
          <p className="text-sm text-[#4a4439]">{t.noBoxesYet}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="text-start text-xs uppercase tracking-wide text-[#6b6355]">
                  {[t.head.box, t.head.where, t.head.status, t.head.last].map((h) => (
                    <th key={h} scope="col" className="px-3 py-2 text-start font-semibold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {boxes.data?.map((b) => (
                  <tr key={b.id} className="border-t border-[#ece8df]">
                    <td className="px-3 py-3 font-semibold" dir="ltr">{b.serial}</td>
                    <td className="px-3 py-3">{b.company ? `${b.company} · ${b.site}` : t.unassigned}</td>
                    <td className="px-3 py-3"><span className="inline-flex items-center gap-2"><Dot tone={tone[status(b)]} />{t.status[status(b)]}</span></td>
                    <td className="px-3 py-3">{when(b.last_checkin, locale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}

export function SecurityLog() {
  const t = useText(TEXT);
  const locale = useLocale();
  const log = useQuery({ queryKey: ["audit"], queryFn: () => get<{ chain: { ok: boolean; entries: number; broken_at?: number } | null; entries: LogEntry[] }>("/audit?limit=200") });
  const chain = log.data?.chain;
  return (
    <>
      <Header title={t.logTitle} lead={t.logLead} />
      {chain && (
        <p role="status" className={`rounded-xl px-4 py-3 text-sm font-medium ${chain.ok ? "bg-[#e8f5ec] text-[#166534]" : "bg-[#fff1e6] text-[#9a3412]"}`}>
          {chain.ok ? t.chainOk(chain.entries) : t.chainBroken(chain.broken_at ?? 0)}
        </p>
      )}
      <Panel>
        <ol className="flex flex-col divide-y divide-[#ece8df]">
          {log.data?.entries.map((e) => (
            <li key={e.id} className="flex flex-col gap-0.5 py-3 sm:flex-row sm:gap-4">
              <span className="shrink-0 text-[13px] tabular-nums text-[#6b6355] sm:w-36">{when(e.at, locale)}</span>
              <span className="text-sm" dir="auto">{e.summary}</span>
            </li>
          ))}
        </ol>
      </Panel>
    </>
  );
}
