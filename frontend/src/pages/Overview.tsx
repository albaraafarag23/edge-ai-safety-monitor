import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, BarChart3, Camera as CameraIcon, CameraOff, Check, Hand, ShieldCheck, Siren, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, mediaUrl } from "../api/client";
import { keys, useCameras, useIncidents, useSetStatus, useStats } from "../api/queries";
import type { Incident, IncidentStatus } from "../api/types";
import { CameraFeed } from "../components/CameraFeed";
import { splitInitial } from "../components/edition";
import { Card, EmptyState, ErrorState, Spinner, StatusBadge } from "../components/ui";
import { useAuth } from "../lib/auth";
import { SEVERITY_STYLES, timeAgo } from "../lib/format";
import { bilingual, LOCALES, plural, useLang, useText, type Lang } from "../lib/i18n";
import { useLive } from "../lib/live";
import { incidentTitle, joinParts, severityLabel, usePluginText } from "../lib/terms";

// The console's front page answers one question in plain words: does anything need me right now?
// Each card says what to do and can be handled in one tap. Counts and charts are on the Analytics page.
const TEXT = bilingual(
  {
    greeting: (hour: number): string =>
      hour < 5 ? "Working late" : hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening",
    watching: "Watching live",
    reconnecting: "Reconnecting…",
    allClear: "All clear.",
    allClearHint: "Nothing is waiting for you. SiteSentry keeps watching.",
    allClearNoCamera: "Nothing is waiting for you. The camera is off, so nothing new can come in until it's back.",
    urgentWaiting: (n: number) => (n === 1 ? "1 urgent incident is waiting." : `${n} urgent incidents are waiting.`),
    urgentHint: "Start with these. Everything else can wait.",
    waiting: (n: number) => (n === 1 ? "1 incident is waiting for you." : `${n} incidents are waiting for you.`),
    waitingHint: "Nothing urgent. Have a look when you can.",
    reviewUrgent: "Review urgent incidents",
    review: "Review incidents",
    siteClear: "Site is clear",
    cameraLive: (online: number, total: number): string =>
      total === 1 ? (online ? "Camera live" : "Camera offline") : online === total ? "All cameras live" : "Some cameras offline",
    noCameras: "No cameras connected yet",
    seesNow: (camera: string, location: string | null) => `What ${camera}${location ? ` at ${location}` : ""} sees right now.`,
    cameraOff: "The camera is off",
    cameraOffHint: "It's switched off or not connected. SiteSentry starts watching again by itself as soon as it's back.",
    handleFirst: "Handle these first",
    seeAllOpen: "See all open",
    nothingOpen: "Nothing to handle",
    nothingOpenHint: "New incidents show up here the moment they're detected.",
    moreLikeIt: (n: number) => (n === 1 ? "and 1 more like it" : `and ${n} more like it`),
    whatToDo: "What to do",
    onIt: "I'm on it",
    done: "Done",
    closeAll: (n: number) => `Close all ${n}`,
    someoneOnIt: "Someone is on it",
    isOnIt: (who: string) => `${who} is on it`,
    failed: "That didn't work. Try again.",
    recent: "Recent activity",
    viewAll: "View all",
    noIncidents: "No incidents yet",
    noIncidentsHint: "New incidents appear here as soon as they're detected.",
    todayMostly: (what: string) => `Most common today: ${what.toLowerCase()}.`,
    todayQuiet: "No incidents so far today.",
    seeNumbers: "Charts and numbers",
    since: {
      lead: (ago: string) => `Since you were last here (${ago}): `,
      nothing: "nothing new.",
      news: (n: number, waiting: number): string =>
        `${n === 1 ? "1 new incident" : `${n} new incidents`}${waiting ? `, ${waiting} still waiting` : ", all handled"}.`,
      see: "See them",
      close: "Close",
    },
    welcome: {
      title: "Welcome to SiteSentry",
      intro: "A camera watches the site and tells you when someone is at risk. Here is how this page works:",
      tips: [
        ["The top line", "tells you whether anything needs you right now."],
        ["Handle these first", "lists what to deal with, with the next step for each. Tap “I'm on it” when you go, and “Done” once it's sorted."],
        ["The menu", "has the live camera, the full incident history, and the safety rules the camera checks."],
      ] as [string, string][],
      gotIt: "Got it",
    },
  },
  {
    greeting: (hour: number) => (hour < 5 ? "تعمل حتى وقت متأخر" : hour < 12 ? "صباح الخير" : "مساء الخير"),
    watching: "مراقبة مباشرة",
    reconnecting: "جارٍ إعادة الاتصال…",
    allClear: "كل شيء على ما يرام.",
    allClearHint: "لا شيء بانتظارك. يواصل SiteSentry المراقبة.",
    allClearNoCamera: "لا شيء بانتظارك. الكاميرا مطفأة، فلن يصل جديد حتى تعود.",
    urgentWaiting: (n: number) =>
      plural("ar", n, {
        one: "حادثة عاجلة بانتظارك.",
        two: "حادثتان عاجلتان بانتظارك.",
        few: `${n} حوادث عاجلة بانتظارك.`,
        other: `${n} حادثة عاجلة بانتظارك.`,
      }),
    urgentHint: "ابدأ بهذه، وكل ما عداها يمكنه الانتظار.",
    waiting: (n: number) =>
      plural("ar", n, {
        one: "حادثة واحدة بانتظارك.",
        two: "حادثتان بانتظارك.",
        few: `${n} حوادث بانتظارك.`,
        other: `${n} حادثة بانتظارك.`,
      }),
    waitingHint: "لا شيء عاجل. ألقِ نظرة حين يتسنى لك.",
    reviewUrgent: "مراجعة الحوادث العاجلة",
    review: "مراجعة الحوادث",
    siteClear: "الموقع آمن",
    cameraLive: (online: number, total: number) =>
      total === 1 ? (online ? "الكاميرا تعمل" : "الكاميرا غير متصلة") : online === total ? "كل الكاميرات تعمل" : "بعض الكاميرات غير متصلة",
    noCameras: "لا توجد كاميرات متصلة بعد",
    seesNow: (camera: string, location: string | null) => `ما تراه ${camera}${location ? ` في ${location}` : ""} الآن.`,
    cameraOff: "الكاميرا مطفأة",
    cameraOffHint: "إنها مطفأة أو غير متصلة. يعود SiteSentry إلى المراقبة تلقائيًا فور عودتها.",
    handleFirst: "ابدأ بهذه",
    seeAllOpen: "كل الحوادث المفتوحة",
    nothingOpen: "لا شيء يحتاج إلى متابعة",
    nothingOpenHint: "تظهر الحوادث الجديدة هنا فور رصدها.",
    moreLikeIt: (n: number) =>
      plural("ar", n, { one: "وحادثة أخرى مثلها", two: "وحادثتان أخريان مثلها", few: `و${n} حوادث أخرى مثلها`, other: `و${n} حادثة أخرى مثلها` }),
    whatToDo: "ما العمل",
    onIt: "أتولّى الأمر",
    done: "تم",
    closeAll: (n: number) => `إغلاق الكل (${n})`,
    someoneOnIt: "هناك من يتولّى الأمر",
    isOnIt: (who: string) => `${who} يتولّى الأمر`,
    failed: "لم ينجح ذلك. حاول مرة أخرى.",
    recent: "آخر ما حدث",
    viewAll: "عرض الكل",
    noIncidents: "لا توجد حوادث بعد",
    noIncidentsHint: "تظهر الحوادث الجديدة هنا فور رصدها.",
    todayMostly: (what: string) => `أكثر ما رُصد اليوم: ${what}.`,
    todayQuiet: "لا حوادث حتى الآن اليوم.",
    seeNumbers: "الرسوم والأرقام",
    since: {
      lead: (ago: string) => `منذ زيارتك الأخيرة (${ago}): `,
      nothing: "لا جديد.",
      news: (n: number, waiting: number) =>
        `${plural("ar", n, { one: "حادثة جديدة", two: "حادثتان جديدتان", few: `${n} حوادث جديدة`, other: `${n} حادثة جديدة` })}${waiting ? `، منها ${waiting} بانتظارك` : "، وكلها عولجت"}.`,
      see: "عرضها",
      close: "إغلاق",
    },
    welcome: {
      title: "مرحبًا بك في SiteSentry",
      intro: "تراقب كاميرا الموقع وتنبّهك حين يكون أحد في خطر. هكذا تعمل هذه الصفحة:",
      tips: [
        ["السطر العلوي", "يخبرك إن كان هناك ما يحتاج إليك الآن."],
        ["ابدأ بهذه", "تعرض ما يجب التعامل معه مع الخطوة التالية لكل حادثة. اضغط «أتولّى الأمر» حين تذهب، و«تم» حين تنتهي."],
        ["القائمة", "فيها الكاميرا المباشرة وسجل الحوادث كاملًا وقواعد السلامة التي تتحقق منها الكاميرا."],
      ] as [string, string][],
      gotIt: "فهمت",
    },
  },
);

/** Large serif heading with an amber initial (the whole first word in Arabic). */
function InitialTitle({ text, lang }: { text: string; lang: Lang }) {
  const [initial, rest] = splitInitial(text, lang);
  return (
    <h2 className="font-serif text-3xl tracking-tight sm:text-4xl">
      <span className={`leading-none text-amber-600 italic ${lang === "ar" ? "text-[1.1em]" : "text-[1.3em]"}`}>{initial}</span>
      {rest}
    </h2>
  );
}

/** The time, updated each minute (seconds ticking by are just noise here). */
function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 15_000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

/** The previous visit's time (this browser only), and records this one. Read once per page load. */
function usePreviousVisit(userId: number | undefined): Date | null {
  const key = `sitesentry.lastVisit.${userId ?? ""}`;
  // read once; saving happens in the effect, after the read (React may run this initializer twice)
  const [previous] = useState<Date | null>(() => {
    try {
      const saved = localStorage.getItem(key);
      return saved ? new Date(saved) : null;
    } catch {
      return null;
    }
  });
  useEffect(() => {
    if (userId === undefined) return;
    try {
      localStorage.setItem(key, new Date().toISOString());
    } catch {
      // private window: no "since you were last here", which is fine
    }
  }, [key, userId]);
  return previous;
}

/** "Since you were last here (3 hours ago): 12 new incidents, 5 still waiting." After 30 minutes away. */
function SinceLastVisit() {
  const t = useText(TEXT).since;
  const { user } = useAuth();
  const previous = usePreviousVisit(user?.id);
  const [closed, setClosed] = useState(false);
  const away = previous ? Date.now() - previous.getTime() : 0;
  const hours = Math.round((away / 3_600_000) * 100) / 100;
  const show = !!previous && away > 30 * 60_000 && !closed;
  const fresh = useIncidents({ hours: show ? hours : 0.01, limit: 1 });
  const waiting = useIncidents({ hours: show ? hours : 0.01, status: "open", limit: 1 });
  if (!show || !fresh.data || !waiting.data) return null;
  return (
    <div className="mb-6 flex items-start gap-3 rounded-2xl bg-white px-5 py-4 text-[15px] text-ink/80 ring-1 ring-ink/[0.08]">
      <p className="flex-1">
        {t.lead(timeAgo(previous.toISOString()))}
        <span className="font-semibold text-ink">{fresh.data.total ? t.news(fresh.data.total, waiting.data.total) : t.nothing}</span>
        {waiting.data.total > 0 && (
          <Link to="/app/incidents?status=open" className="ms-2 font-semibold text-amber-700 hover:underline">
            {t.see}
          </Link>
        )}
      </p>
      <button onClick={() => setClosed(true)} className="rounded-full p-1 text-ink/40 hover:bg-paper hover:text-ink" aria-label={t.close}>
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

/** Shown once per person (until "Got it"): what this page is for. Kept in this browser only. */
function Welcome() {
  const t = useText(TEXT).welcome;
  const { user } = useAuth();
  const key = `sitesentry.welcomed.${user?.id ?? ""}`;
  const [show, setShow] = useState(() => {
    try {
      return !localStorage.getItem(key);
    } catch {
      return false;
    }
  });
  if (!show) return null;
  const dismiss = () => {
    try {
      localStorage.setItem(key, "1");
    } catch {
      // private window: it shows again next time, which is fine
    }
    setShow(false);
  };
  return (
    <section className="relative mb-8 rounded-2xl bg-amber-50 p-6 ring-1 ring-amber-500/30">
      <button onClick={dismiss} className="absolute end-3 top-3 rounded-full p-1.5 text-ink/40 hover:bg-amber-100 hover:text-ink" aria-label={t.gotIt}>
        <X className="h-4 w-4" />
      </button>
      <h2 className="font-serif text-2xl text-ink">{t.title}</h2>
      <p className="mt-1 text-ink/70">{t.intro}</p>
      <ul className="mt-4 grid gap-3 sm:grid-cols-3">
        {t.tips.map(([what, how]) => (
          <li key={what} className="rounded-xl bg-white/70 p-4 text-sm leading-relaxed text-ink/70">
            <span className="font-semibold text-ink">{what}</span> {how}
          </li>
        ))}
      </ul>
      <button onClick={dismiss} className="mt-4 rounded-full bg-ink px-5 py-2 text-sm font-semibold text-paper hover:bg-ink/85">
        {t.gotIt}
      </button>
    </section>
  );
}

/** Dark band at the top: greeting, the site's state in one sentence, and the live camera. */
function ControlRoom({ open, urgent }: { open: number | undefined; urgent: number | undefined }) {
  const { user } = useAuth();
  const { connection } = useLive();
  const cameras = useCameras();
  const now = useClock();
  const camera = cameras.data?.find((c) => c.online) ?? cameras.data?.[0];
  const online = cameras.data?.filter((c) => c.online).length ?? 0;
  const firstName = user?.name.split(" ")[0] ?? "";
  const t = useText(TEXT);
  const { lang } = useLang();
  const loading = open === undefined || urgent === undefined;

  const [headline, hint] = loading
    ? ["", ""]
    : open === 0
      ? [t.allClear, cameras.data && online === 0 ? t.allClearNoCamera : t.allClearHint]
      : urgent
        ? [t.urgentWaiting(urgent), t.urgentHint]
        : [t.waiting(open), t.waitingHint];

  return (
    <section className="relative -mx-4 -mt-8 overflow-hidden bg-ink text-paper sm:-mx-6 lg:-mx-10">
      <img
        src="/edition/console-1200.webp"
        srcSet="/edition/console-1200.webp 1200w, /edition/console-2400.webp 2400w"
        sizes="(min-width: 1024px) calc(100vw - 16rem), 100vw"
        alt=""
        className="page-photo absolute inset-0 h-full w-full object-cover"
        aria-hidden
      />
      <div className="absolute inset-0 bg-gradient-to-r from-ink/95 via-ink/70 to-ink/20 rtl:bg-gradient-to-l" aria-hidden />
      <div className="relative grid gap-10 px-4 pt-10 pb-24 sm:px-6 lg:px-10 xl:grid-cols-[1fr_1fr] xl:items-center xl:pt-14">
        <div>
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-paper/60">
            <span>
              {now.toLocaleDateString(LOCALES[lang], { weekday: "long", day: "numeric", month: "long" })} ·{" "}
              {now.toLocaleTimeString(LOCALES[lang], { hour: "numeric", minute: "2-digit" })}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="relative flex h-2 w-2">
                {connection === "live" && <span className="radar absolute inset-0 rounded-full bg-emerald-400" />}
                <span className={`relative h-2 w-2 rounded-full ${connection === "live" ? "bg-emerald-400" : "bg-amber-400"}`} />
              </span>
              {connection === "live" ? t.watching : t.reconnecting}
            </span>
          </p>
          <h1 className="mt-4 font-serif text-3xl leading-tight text-paper/85 sm:text-4xl">
            {t.greeting(now.getHours())}
            {firstName && <span className="text-amber-400 italic">{lang === "ar" ? "، " : ", "}{firstName}</span>}.
          </h1>
          <p
            className={`mt-3 max-w-xl font-display text-[clamp(2rem,3.6vw,3.4rem)] leading-[1.02] font-semibold tracking-[-0.035em] text-balance ${
              urgent ? "text-red-300" : "text-paper"
            }`}
            aria-live="polite"
          >
            {headline || " "}
          </p>
          {hint && <p className="mt-3 max-w-xl text-lg text-paper/70">{hint}</p>}
          <div className="mt-8 flex flex-wrap items-center gap-3">
            {open ? (
              <Link
                to={urgent ? "/app/incidents?status=open&severity=CRITICAL" : "/app/incidents?status=open"}
                className="inline-flex items-center gap-2 rounded-full bg-amber-400 px-5 py-2.5 text-sm font-semibold text-ink hover:bg-amber-300"
              >
                <Siren className="h-4 w-4" /> {urgent ? t.reviewUrgent : t.review} <ArrowRight className="flip-rtl h-4 w-4" />
              </Link>
            ) : open === 0 ? (
              <span className="inline-flex items-center gap-2 rounded-full bg-emerald-400/15 px-5 py-2.5 text-sm font-semibold text-emerald-300">
                <ShieldCheck className="h-4 w-4" /> {t.siteClear}
              </span>
            ) : null}
            {cameras.data && cameras.data.length > 0 && (
              <Link
                to="/app/cameras"
                className="inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold text-paper ring-1 ring-paper/25 hover:bg-white/10"
              >
                <span className={`h-2 w-2 rounded-full ${online === cameras.data.length ? "bg-emerald-400" : "bg-amber-400"}`} />
                <CameraIcon className="h-4 w-4" /> {t.cameraLive(online, cameras.data.length)}
              </Link>
            )}
          </div>
        </div>
        <figure>
          {cameras.isPending ? (
            <Spinner />
          ) : camera?.online ? (
            <>
              <Link to={`/app/cameras?camera=${encodeURIComponent(camera.camera_id)}`} className="block">
                <CameraFeed camera={camera} showFullscreen={false} showFps={false} className="shadow-2xl shadow-black/60 ring-white/10" />
              </Link>
              <figcaption className="mt-3 font-serif text-lg text-paper/70 italic">{t.seesNow(camera.camera_id, camera.location)}</figcaption>
            </>
          ) : (
            <div className="flex aspect-video flex-col items-center justify-center gap-3 rounded-xl bg-black/45 px-8 text-center ring-1 ring-white/10">
              <CameraOff className="h-8 w-8 text-paper/40" />
              <p className="font-display text-xl font-semibold text-paper">{camera ? t.cameraOff : t.noCameras}</p>
              {camera && <p className="max-w-sm text-sm leading-relaxed text-paper/60">{t.cameraOffHint}</p>}
            </div>
          )}
        </figure>
      </div>
    </section>
  );
}

type Group = { incident: Incident; others: Incident[] };

/** Changes the status of a whole group at once ("Close all"). */
function useSetGroupStatus() {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const run = async (ids: string[], status: IncidentStatus) => {
    setBusy(true);
    setFailed(false);
    const results = await Promise.allSettled(ids.map((id) => api.setStatus(id, status)));
    setFailed(results.some((r) => r.status === "rejected"));
    await Promise.all([qc.invalidateQueries({ queryKey: keys.incidents }), qc.invalidateQueries({ queryKey: ["stats"] })]);
    setBusy(false);
  };
  return { run, busy, failed };
}

/** One thing to deal with: what happened, where, what to do, and the buttons to handle it. */
function TaskCard({ group, canHandle }: { group: Group; canHandle: boolean }) {
  const { incident: i, others } = group;
  const t = useText(TEXT);
  const plugin = usePluginText();
  const place = plugin.location(i.location, i.metadata.zone_id);
  const thumb = mediaUrl(i.snapshot_url);
  const step = plugin.ruleActions(i.metadata.rule_id)[0];
  const one = useSetStatus(i.event_id);
  const all = useSetGroupStatus();
  const busy = one.isPending || all.busy;
  const link = `/app/incidents/${i.event_id}`;

  return (
    <li className="flex h-full flex-col gap-4 rounded-2xl bg-white p-4 ring-1 ring-ink/[0.08] sm:flex-row">
      <Link to={link} className="relative aspect-[4/3] w-full shrink-0 overflow-hidden rounded-xl bg-ink/10 sm:w-40" tabIndex={-1} aria-hidden>
        {thumb && (
          <img src={thumb} alt="" loading="lazy" className="absolute inset-0 h-full w-full object-cover"
            onError={(e) => (e.currentTarget.style.display = "none")} />
        )}
      </Link>
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-ink/60">
          <span className={`h-2 w-2 rounded-full ${SEVERITY_STYLES[i.severity]?.dot ?? "bg-ink/30"}`} />
          {severityLabel(i.severity)}
          {i.status === "acknowledged" && (
            <span className="text-violet-700">· {i.status_updated_by ? t.isOnIt(i.status_updated_by.split(" ")[0]) : t.someoneOnIt}</span>
          )}
        </span>
        <Link to={link} className="mt-1 font-display text-lg leading-snug font-semibold text-ink hover:text-amber-700">
          {incidentTitle(i)}
        </Link>
        <span className="text-sm text-ink/65">
          {joinParts([place ?? i.camera_id, timeAgo(i.received_at)])}
          {others.length > 0 && <span className="text-ink/60"> {t.moreLikeIt(others.length)}</span>}
        </span>
        {step && (
          <p className="mt-3 rounded-lg bg-paper px-3 py-2 text-sm leading-snug text-ink/75">
            <span className="font-semibold text-ink">{t.whatToDo}: </span>
            {step}
          </p>
        )}
        {canHandle && (
          <div className="mt-3 flex flex-wrap gap-2">
            {i.status === "open" && (
              <button
                disabled={busy}
                onClick={() => one.mutate({ status: "acknowledged" })}
                className="inline-flex items-center gap-1.5 rounded-full bg-ink px-4 py-2 text-sm font-semibold text-paper hover:bg-ink/85 disabled:opacity-50"
              >
                <Hand className="h-4 w-4" /> {t.onIt}
              </button>
            )}
            <button
              disabled={busy}
              onClick={() => one.mutate({ status: "resolved" })}
              className="inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold text-ink ring-1 ring-ink/20 hover:bg-paper disabled:opacity-50"
            >
              <Check className="h-4 w-4" /> {t.done}
            </button>
            {others.length > 0 && (
              <button
                disabled={busy}
                onClick={() => all.run([i, ...others].map((x) => x.event_id), "resolved")}
                className="rounded-full px-3 py-2 text-sm font-medium text-ink/60 hover:bg-paper hover:text-ink disabled:opacity-50"
              >
                {t.closeAll(others.length + 1)}
              </button>
            )}
          </div>
        )}
        {(one.isError || all.failed) && <p className="mt-2 text-sm text-red-700">{t.failed}</p>}
      </div>
    </li>
  );
}

/** Latest incidents in one line each: what, where, when. */
function Recent({ incidents }: { incidents: Incident[] }) {
  const plugin = usePluginText();
  return (
    <ol className="-mx-5 -my-5 divide-y divide-ink/[0.07]">
      {incidents.map((i, n) => (
        <li key={i.event_id} className="feed-in" style={{ animationDelay: `${n * 50}ms` }}>
          <Link to={`/app/incidents/${i.event_id}`} className="group flex items-center gap-4 px-5 py-3.5 hover:bg-paper/60">
            <span className={`h-9 w-1 shrink-0 rounded-full ${SEVERITY_STYLES[i.severity]?.bar ?? "bg-ink/30"}`} aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="truncate font-display font-semibold text-ink group-hover:text-amber-700">{incidentTitle(i)}</p>
              <p className="truncate text-sm text-ink/65">
                {joinParts([plugin.location(i.location, i.metadata.zone_id) ?? i.camera_id, timeAgo(i.received_at)])}
              </p>
            </div>
            <StatusBadge status={i.status} />
          </Link>
        </li>
      ))}
    </ol>
  );
}

/** One plain sentence about today, with the way to the numbers. */
function Today() {
  const t = useText(TEXT);
  const stats = useStats(24);
  if (!stats.data) return null;
  const top = Object.entries(stats.data.by_event_type).sort((a, b) => b[1] - a[1])[0]?.[0];
  return (
    <div className="mt-10 flex flex-wrap items-center justify-between gap-4 border-t border-ink/10 pt-6">
      <p className="font-serif text-xl text-ink/70 italic">{top ? t.todayMostly(incidentTitle({ event_type: top })) : t.todayQuiet}</p>
      <Link to="/app/analytics" className="inline-flex items-center gap-2 text-sm font-semibold text-amber-700 hover:underline">
        <BarChart3 className="h-4 w-4" /> {t.seeNumbers} <ArrowRight className="flip-rtl h-4 w-4" />
      </Link>
    </div>
  );
}

/** The same thing in the same place again is one group ("and 3 more like it"); order is kept. */
function groupIncidents(incidents: Incident[]): Group[] {
  const key = (x: Incident) =>
    [x.event_type, x.camera_id, x.metadata.zone_id ?? "", (x.metadata.missing_equipment ?? []).join(), x.status].join("|");
  const groups = new Map<string, Group>();
  for (const i of incidents) {
    const group = groups.get(key(i));
    if (group) group.others.push(i);
    else groups.set(key(i), { incident: i, others: [] });
  }
  return [...groups.values()];
}

export function Overview() {
  const t = useText(TEXT);
  const { lang } = useLang();
  const canHandle = useAuth().user?.role !== "viewer";
  // totals come from the list endpoints' X-Total-Count, so they count every open incident, not one period
  const urgent = useIncidents({ status: "open", severity: "CRITICAL", limit: 50 });
  const open = useIncidents({ status: "open", limit: 50 });
  const onIt = useIncidents({ status: "acknowledged", limit: 50 });
  const latest = useIncidents({ limit: 6 });

  // urgent first, then other open ones, then the ones someone is already on; four cards in all
  const seen = new Set<string>();
  const queue = [...(urgent.data?.items ?? []), ...(open.data?.items ?? []), ...(onIt.data?.items ?? [])].filter(
    (i) => !seen.has(i.event_id) && seen.add(i.event_id),
  );
  const first = groupIncidents(queue).slice(0, 4);

  return (
    <>
      <ControlRoom open={open.data?.total} urgent={urgent.data?.total} />

      <div className="paper-grain relative z-10 -mx-4 -mt-10 mb-6 flex flex-wrap items-end justify-between gap-4 rounded-t-[2rem] bg-paper px-4 pt-9 sm:-mx-6 sm:px-6 lg:-mx-10 lg:px-10">
        <InitialTitle text={t.handleFirst} lang={lang} />
        {first.length > 0 && (
          <Link to="/app/incidents?status=open" className="text-sm font-semibold text-amber-700 hover:underline">
            {t.seeAllOpen}
          </Link>
        )}
      </div>

      <SinceLastVisit />
      <Welcome />

      {open.isPending || urgent.isPending || onIt.isPending ? (
        <Spinner />
      ) : open.isError ? (
        <ErrorState error={open.error} onRetry={() => open.refetch()} />
      ) : first.length ? (
        <ul className="grid gap-4 xl:grid-cols-2">
          {first.map((g) => (
            <TaskCard key={g.incident.event_id} group={g} canHandle={canHandle} />
          ))}
        </ul>
      ) : (
        <EmptyState title={t.nothingOpen}>{t.nothingOpenHint}</EmptyState>
      )}

      <Card
        title={
          <span className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="radar absolute inset-0 rounded-full bg-red-500" />
              <span className="relative h-2 w-2 rounded-full bg-red-500" />
            </span>
            {t.recent}
          </span>
        }
        className="mt-10 min-w-0"
        action={<Link to="/app/incidents" className="text-sm font-medium text-amber-700 hover:underline">{t.viewAll}</Link>}
      >
        {latest.isPending ? (
          <Spinner />
        ) : latest.isError ? (
          <ErrorState error={latest.error} />
        ) : latest.data.items.length ? (
          <Recent incidents={latest.data.items} />
        ) : (
          <EmptyState title={t.noIncidents}>{t.noIncidentsHint}</EmptyState>
        )}
      </Card>

      <Today />
    </>
  );
}
