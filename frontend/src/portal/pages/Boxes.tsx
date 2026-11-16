/** The boxes (Jetsons on site): new ones asking to join, and each box's health and licence. Health only. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { bilingual, useText } from "../../lib/i18n";
import { cancelledByBrowser, get, send, type Box, type BoxHealth, type RuleSet, type SiteRef } from "../api";
import { BTN, BTN_LINE, Dot, FIELD, Header, Panel, problem, useLocale, when } from "../shell";

export const BOX_TEXT = bilingual(
  {
    title: "Boxes",
    lead: "Each site's Jetson, as it last reported. Health only: pictures, clips and incidents never leave the site.",
    none: "No box has contacted the portal yet. A box connects once its PORTAL_URL is set.",
    waiting: "Asking to join",
    waitingLead: "A box that contacted the portal on its own. It runs no licensed rules until you assign it.",
    site: "Site",
    pickSite: "Choose a site",
    ruleSets: "Rule sets it may run",
    assign: "Assign",
    block: "Block",
    unblock: "Unblock",
    save: "Save licence",
    noSites: "Add the company and its site first (Companies).",
    status: { fine: "Fine", silent: "Silent", waiting: "Waiting", blocked: "Blocked" },
    lastIn: (at: string) => `Last check-in ${at}`,
    never: "Hasn't checked in yet",
    cameras: (n: number, fps: string) => `${n} camera${n === 1 ? "" : "s"} · ${fps} fps`,
    noCamera: "No camera reporting",
    rules: (r: string) => `Running: ${r}`,
    noRules: "Running no rules",
    disk: (p: number) => `Disk ${p}% full`,
    licence: "Licence",
    failed: "That didn't work. Try again.",
    cancelled: "The passkey prompt was closed, so nothing was changed.",
    silentNote: "Its rules keep running on site for up to 7 days without the portal.",
    drives: "Cancelled rule drives",
    drivesLead: "A drive reported lost, stolen or replaced. Every box refuses it from its next check-in. The serial is printed by scripts/plugin-drive.py when the drive is made.",
    driveSerial: "Drive serial",
    driveNote: "Why (optional)",
    cancelDrive: "Cancel this drive",
    allowAgain: "Allow again",
    noCancelled: "No drive is cancelled.",
  },
  {
    title: "الأجهزة",
    lead: "جهاز Jetson في كل موقع كما أبلغ آخر مرة. الحالة فقط: لا تغادر الصور والمقاطع والحوادث الموقع.",
    none: "لم يتصل أي جهاز بالبوابة بعد. يتصل الجهاز بعد ضبط PORTAL_URL عليه.",
    waiting: "يطلب الانضمام",
    waitingLead: "جهاز اتصل بالبوابة من تلقاء نفسه. لا يشغّل قواعد مرخّصة حتى تعيّنه.",
    site: "الموقع",
    pickSite: "اختر موقعًا",
    ruleSets: "مجموعات القواعد المسموح بها",
    assign: "تعيين",
    block: "حظر",
    unblock: "إلغاء الحظر",
    save: "حفظ الترخيص",
    noSites: "أضف الشركة وموقعها أولًا (الشركات).",
    status: { fine: "بخير", silent: "صامت", waiting: "بانتظار", blocked: "محظور" },
    lastIn: (at: string) => `آخر اتصال ${at}`,
    never: "لم يتصل بعد",
    cameras: (n: number, fps: string) => `${n} ${n === 1 ? "كاميرا" : "كاميرات"} · ${fps} إطارًا/ث`,
    noCamera: "لا تبلغ أي كاميرا",
    rules: (r: string) => `يشغّل: ${r}`,
    noRules: "لا يشغّل قواعد",
    disk: (p: number) => `القرص ممتلئ ${p}%`,
    licence: "الترخيص",
    failed: "لم ينجح ذلك. حاول مرة أخرى.",
    cancelled: "أُغلقت نافذة مفتاح المرور، فلم يتغير شيء.",
    silentNote: "تستمر قواعده في العمل في الموقع حتى 7 أيام دون البوابة.",
    drives: "وحدات القواعد الملغاة",
    drivesLead: "وحدة أُبلغ عن فقدها أو سرقتها أو استبدالها. ترفضها كل الأجهزة من اتصالها التالي. يطبع scripts/plugin-drive.py الرقم التسلسلي عند صنع الوحدة.",
    driveSerial: "الرقم التسلسلي للوحدة",
    driveNote: "السبب (اختياري)",
    cancelDrive: "إلغاء هذه الوحدة",
    allowAgain: "السماح من جديد",
    noCancelled: "لا توجد وحدات ملغاة.",
  },
);

type State = "fine" | "silent" | "waiting" | "blocked";
const state = (b: Box): State => (b.status !== "approved" ? b.status : b.silent ? "silent" : "fine");
const TONE = { fine: "good", silent: "bad", waiting: "warn", blocked: "off" } as const;

export function healthLine(h: BoxHealth, t: (typeof BOX_TEXT)["en"], ruleNames: Record<string, string>) {
  const cams = h.cameras ?? [];
  const fps = cams.length ? (cams.reduce((a, c) => a + c.fps, 0) / cams.length).toFixed(0) : "0";
  return [
    cams.length ? t.cameras(cams.length, fps) : t.noCamera,
    h.rules ? t.rules(ruleNames[h.rules] ?? h.rules) : t.noRules,
    h.disk_used_pct != null ? t.disk(h.disk_used_pct) : null,
  ].filter(Boolean).join(" · ");
}

function RuleSetChoice({ sets, value, onChange }: { sets: RuleSet[]; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-2">
      {sets.map((r) => (
        <label key={r.id} className="inline-flex items-center gap-2 text-sm">
          <input type="checkbox" checked={value.includes(r.id)}
            onChange={(e) => onChange(e.target.checked ? [...value, r.id] : value.filter((x) => x !== r.id))} />
          {r.name}
        </label>
      ))}
    </div>
  );
}

function BoxCard({ box, sites, sets }: { box: Box; sites: SiteRef[]; sets: RuleSet[] }) {
  const t = useText(BOX_TEXT);
  const locale = useLocale();
  const qc = useQueryClient();
  const [siteId, setSiteId] = useState<number | "">(box.site_id ?? "");
  const [plugins, setPlugins] = useState<string[]>(box.plugins);
  const [error, setError] = useState<string | null>(null);
  const names = Object.fromEntries(sets.map((r) => [r.id, r.name]));
  const s = state(box);

  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(cancelledByBrowser(err) ? t.cancelled : problem(err, t.failed));
    } finally {
      await qc.invalidateQueries();
    }
  };

  return (
    <article className={`flex flex-col gap-3 rounded-2xl border bg-white p-5 ${s === "silent" ? "border-[#f0c9a0] bg-[#fff7ed]" : "border-[#d9d2c4]"}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-display text-lg font-bold" dir="ltr">{box.serial}</h3>
        <span className="inline-flex items-center gap-2 text-sm font-semibold"><Dot tone={TONE[s]} />{t.status[s]}</span>
      </div>
      {box.company && (
        <Link to={`/companies/${box.company_id}`} className="text-sm font-semibold underline"><bdi>{box.company}</bdi> · <bdi>{box.site}</bdi></Link>
      )}
      <p className="text-[13px] text-[#4a4439]">
        {box.last_checkin ? t.lastIn(when(box.last_checkin, locale)) : t.never}
        {box.last_checkin && <> · {healthLine(box.health as BoxHealth, t, names)}</>}
      </p>
      {s === "silent" && <p className="text-[13px] text-[#9a3412]">{t.silentNote}</p>}

      {box.status === "waiting" ? (
        sites.length === 0 ? <p className="text-sm text-[#4a4439]">{t.noSites}</p> : (
          <div className="flex flex-col gap-3 rounded-xl bg-[#f8f5ef] p-4">
            <label className="text-sm font-medium">{t.site}
              <select className={FIELD} value={siteId} onChange={(e) => setSiteId(e.target.value ? Number(e.target.value) : "")}>
                <option value="">{t.pickSite}</option>
                {sites.map((x) => <option key={x.id} value={x.id}>{x.company} · {x.name}</option>)}
              </select>
            </label>
            <fieldset className="text-sm"><legend className="mb-2 font-medium">{t.ruleSets}</legend>
              <RuleSetChoice sets={sets} value={plugins} onChange={setPlugins} />
            </fieldset>
            <div className="flex flex-wrap gap-2.5">
              <button type="button" className={BTN} disabled={siteId === ""}
                onClick={() => run(() => send(`/boxes/${box.id}/assign`, { site_id: siteId, plugins }))}>{t.assign}</button>
              <button type="button" className={BTN_LINE}
                onClick={() => run(() => send(`/boxes/${box.id}`, { status: "blocked" }, "PATCH"))}>{t.block}</button>
            </div>
          </div>
        )
      ) : (
        <div className="flex flex-col gap-3">
          <fieldset className="text-sm"><legend className="mb-2 font-medium">{t.licence}</legend>
            <RuleSetChoice sets={sets} value={plugins} onChange={setPlugins} />
          </fieldset>
          <div className="flex flex-wrap gap-2.5">
            <button type="button" className={BTN} disabled={plugins.slice().sort().join() === box.plugins.slice().sort().join()}
              onClick={() => run(() => send(`/boxes/${box.id}`, { plugins }, "PATCH"))}>{t.save}</button>
            <button type="button" className={BTN_LINE}
              onClick={() => run(() => send(`/boxes/${box.id}`, { status: box.status === "blocked" ? "approved" : "blocked" }, "PATCH"))}>
              {box.status === "blocked" ? t.unblock : t.block}
            </button>
          </div>
        </div>
      )}
      {error && <p role="alert" className="rounded-xl bg-[#fff1e6] px-3.5 py-2.5 text-sm text-[#9a3412]">{error}</p>}
    </article>
  );
}

export function BoxCards({ boxes }: { boxes: Box[] }) {
  const sites = useQuery({ queryKey: ["sites"], queryFn: () => get<SiteRef[]>("/sites") });
  const sets = useQuery({ queryKey: ["rule-sets"], queryFn: () => get<RuleSet[]>("/rule-sets"), staleTime: Infinity });
  return (
    <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(300px,1fr))]">
      {boxes.map((b) => <BoxCard key={`${b.id}-${b.status}-${b.plugins.join()}`} box={b} sites={sites.data ?? []} sets={sets.data ?? []} />)}
    </div>
  );
}

function CancelledDrives() {
  const t = useText(BOX_TEXT);
  const locale = useLocale();
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["cancelled-drives"],
    queryFn: () => get<{ serial: string; note: string | null; by: string; at: string }[]>("/drives/cancelled") });
  const [serial, setSerial] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      return true;
    } catch (err) {
      setError(cancelledByBrowser(err) ? t.cancelled : problem(err, t.failed));
      return false;
    } finally {
      await qc.invalidateQueries({ queryKey: ["cancelled-drives"] });
    }
  };
  return (
    <Panel title={t.drives}>
      <p className="mb-4 text-sm text-[#4a4439]">{t.drivesLead}</p>
      <form className="mb-4 flex flex-wrap items-end gap-2.5" onSubmit={async (e) => {
        e.preventDefault();
        if (await run(() => send("/drives/cancelled", { serial: serial.trim(), note: note.trim() || null }))) {
          setSerial("");
          setNote("");
        }
      }}>
        <label className="min-w-52 flex-1 text-sm font-medium">{t.driveSerial}
          <input required dir="ltr" pattern="[A-Za-z0-9._:\-]{3,128}" value={serial} onChange={(e) => setSerial(e.target.value)} className={FIELD} />
        </label>
        <label className="min-w-52 flex-1 text-sm font-medium">{t.driveNote}
          <input value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} className={FIELD} />
        </label>
        <button type="submit" className={BTN}>{t.cancelDrive}</button>
      </form>
      {error && <p role="alert" className="mb-3 rounded-xl bg-[#fff1e6] px-3.5 py-2.5 text-sm text-[#9a3412]">{error}</p>}
      {list.data?.length === 0 ? <p className="text-sm text-[#4a4439]">{t.noCancelled}</p> : (
        <ul className="flex flex-col divide-y divide-[#ece8df]">
          {list.data?.map((d) => (
            <li key={d.serial} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm">
              <span><span dir="ltr" className="font-semibold">{d.serial}</span>{d.note ? ` · ${d.note}` : ""} · {d.by}, {when(d.at, locale)}</span>
              <button type="button" className={BTN_LINE} onClick={() => run(() => send(`/drives/cancelled/${encodeURIComponent(d.serial)}`, undefined, "DELETE"))}>
                {t.allowAgain}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export function Boxes() {
  const t = useText(BOX_TEXT);
  const boxes = useQuery({ queryKey: ["boxes"], queryFn: () => get<Box[]>("/boxes"), refetchInterval: 30_000 });
  const waiting = boxes.data?.filter((b) => b.status === "waiting") ?? [];
  const others = boxes.data?.filter((b) => b.status !== "waiting") ?? [];
  return (
    <>
      <Header title={t.title} lead={t.lead} />
      {boxes.data?.length === 0 && <Panel><p className="text-sm text-[#4a4439]">{t.none}</p></Panel>}
      {waiting.length > 0 && (
        <section className="flex flex-col gap-3" aria-labelledby="waiting">
          <h2 id="waiting" className="font-display text-xl font-bold">{t.waiting}</h2>
          <p className="text-sm text-[#4a4439]">{t.waitingLead}</p>
          <BoxCards boxes={waiting} />
        </section>
      )}
      {others.length > 0 && <BoxCards boxes={others} />}
      <CancelledDrives />
    </>
  );
}
