/** Companies (overseer) and one company: its sites, its people and their devices, invite links. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, ExternalLink, Plus } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { bilingual, useText } from "../../lib/i18n";
import { cancelledByBrowser, get, send, type BoxHealth, type CompanyDetail, type CompanyPerson, type CompanySummary, type Role, type RuleSet } from "../api";
import { BOX_TEXT, healthLine } from "./Boxes";
import { BTN, BTN_LINE, Dot, FIELD, Header, Panel, problem, useLocale, useMe, when, WORDS } from "../shell";

const TEXT = bilingual(
  {
    title: "Companies",
    lead: "Each client company: you add it and its first manager; their managers run their own sites from there.",
    add: "Add a company",
    name: "Company name",
    save: "Add",
    cancel: "Cancel",
    none: "No companies yet.",
    counts: (s: number, p: number, b: number) => `${s} site${s === 1 ? "" : "s"} · ${p} ${p === 1 ? "person" : "people"} · ${b} box${b === 1 ? "" : "es"}`,
    suspended: "Suspended",
    since: (d: string) => `Client since ${d}`,
    allClients: "All clients",
    sitesTitle: "Sites",
    addSite: "Add a site",
    siteName: "Site name",
    city: "City (optional)",
    noSites: "No sites yet.",
    box: (serial: string) => `Box ${serial}`,
    noBox: "No box connected yet",
    silent: "silent",
    openConsole: "Open console",
    peopleTitle: "People and their devices",
    peopleNote: "Managers' devices are approved by SiteSentry; managers approve their own staff.",
    addPerson: "Add a person",
    email: "Email",
    fullName: "Full name",
    role: "Role",
    sitesFor: "Sites they work on",
    allSites: "All sites (managers only)",
    linkReady: (name: string) => `${name} can now set up their phone or laptop with this link (one use, 3 days):`,
    emailed: "It was also emailed to them.",
    notEmailed: "Email isn't set up for the portal yet, so send them this link yourself (WhatsApp is fine: it only works once).",
    copy: "Copy link",
    copied: "Copied",
    newLink: "New link",
    switchOff: "Switch off",
    switchOn: "Switch on",
    off: "Switched off",
    waitingSetup: "Hasn't set up a device yet",
    devices: (n: number) => `${n} device${n === 1 ? "" : "s"}`,
    lastIn: (at: string) => `last in ${at}`,
    remove: "Remove",
    approve: "Approve",
    suspend: "Suspend company",
    resume: "Switch company back on",
    suspendHint: "Suspending signs everyone in this company out at once; their boxes keep running.",
    failed: "That didn't work. Try again.",
    cancelled: "The passkey prompt was closed, so nothing was changed.",
    cant: "What you can't see here",
    cantText: "Camera pictures, clips, incidents, reports and workers' face photos stay on each company's own box. The portal only knows accounts, devices, licences and whether each box is healthy.",
  },
  {
    title: "الشركات",
    lead: "كل شركة عميلة: تضيفها أنت مع أول مدير لها، ثم يدير مديروها مواقعهم بأنفسهم.",
    add: "إضافة شركة",
    name: "اسم الشركة",
    save: "إضافة",
    cancel: "إلغاء",
    none: "لا توجد شركات بعد.",
    counts: (s: number, p: number, b: number) => `${s} ${s === 1 ? "موقع" : "مواقع"} · ${p} ${p === 1 ? "شخص" : "أشخاص"} · ${b} ${b === 1 ? "جهاز" : "أجهزة"}`,
    suspended: "موقوفة",
    since: (d: string) => `عميل منذ ${d}`,
    allClients: "كل العملاء",
    sitesTitle: "المواقع",
    addSite: "إضافة موقع",
    siteName: "اسم الموقع",
    city: "المدينة (اختياري)",
    noSites: "لا توجد مواقع بعد.",
    box: (serial: string) => `الجهاز ${serial}`,
    noBox: "لم يتصل جهاز بعد",
    silent: "صامت",
    openConsole: "فتح لوحة التحكم",
    peopleTitle: "الأشخاص وأجهزتهم",
    peopleNote: "توافق SiteSentry على أجهزة المديرين، ويوافق المديرون على أجهزة موظفيهم.",
    addPerson: "إضافة شخص",
    email: "البريد الإلكتروني",
    fullName: "الاسم الكامل",
    role: "الدور",
    sitesFor: "المواقع التي يعمل فيها",
    allSites: "كل المواقع (للمديرين فقط)",
    linkReady: (name: string) => `يستطيع ${name} الآن تجهيز هاتفه أو حاسوبه بهذا الرابط (استخدام واحد، 3 أيام):`,
    emailed: "وأُرسل إليه بالبريد أيضًا.",
    notEmailed: "البريد غير مُعدّ للبوابة بعد، فأرسل الرابط بنفسك (واتساب مناسب: يعمل مرة واحدة فقط).",
    copy: "نسخ الرابط",
    copied: "تم النسخ",
    newLink: "رابط جديد",
    switchOff: "إيقاف",
    switchOn: "تشغيل",
    off: "متوقف",
    waitingSetup: "لم يجهّز جهازًا بعد",
    devices: (n: number) => `${n} ${n === 1 ? "جهاز" : "أجهزة"}`,
    lastIn: (at: string) => `آخر دخول ${at}`,
    remove: "إزالة",
    approve: "موافقة",
    suspend: "إيقاف الشركة",
    resume: "إعادة تشغيل الشركة",
    suspendHint: "يُخرج الإيقاف كل أفراد الشركة فورًا، وتستمر أجهزتهم في العمل.",
    failed: "لم ينجح ذلك. حاول مرة أخرى.",
    cancelled: "أُغلقت نافذة مفتاح المرور، فلم يتغير شيء.",
    cant: "ما لا تراه هنا",
    cantText: "تبقى صور الكاميرات والمقاطع والحوادث والتقارير وصور وجوه العمال على جهاز كل شركة. لا تعرف البوابة إلا الحسابات والأجهزة والتراخيص وحالة كل جهاز.",
  },
);

function useChange() {
  const qc = useQueryClient();
  const t = useText(TEXT);
  const [error, setError] = useState<string | null>(null);
  const run = async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setError(null);
    try {
      return await fn();
    } catch (err) {
      setError(cancelledByBrowser(err) ? t.cancelled : problem(err, t.failed));
      return undefined;
    } finally {
      await qc.invalidateQueries();
    }
  };
  return { run, error };
}

function Alert({ text }: { text: string | null }) {
  return text ? <p role="alert" className="rounded-xl bg-[#fff1e6] px-3.5 py-2.5 text-sm text-[#9a3412]">{text}</p> : null;
}

function Toggle({ label, children }: { label: string; children: (close: () => void) => ReactNode }) {
  const [open, setOpen] = useState(false);
  return open ? <>{children(() => setOpen(false))}</> : (
    <button type="button" className={BTN} onClick={() => setOpen(true)}><Plus className="h-4 w-4" aria-hidden="true" />{label}</button>
  );
}

export function Companies() {
  const t = useText(TEXT);
  const companies = useQuery({ queryKey: ["companies"], queryFn: () => get<CompanySummary[]>("/companies") });
  const { run, error } = useChange();
  const [name, setName] = useState("");

  return (
    <>
      <Header title={t.title} lead={t.lead}>
        <Toggle label={t.add}>
          {(close) => (
            <form className="flex w-full max-w-lg flex-wrap items-end gap-2.5" onSubmit={async (e: FormEvent) => {
              e.preventDefault();
              if (await run(() => send("/companies", { name: name.trim() }))) { setName(""); close(); }
            }}>
              <label className="min-w-56 flex-1 text-sm font-medium">{t.name}
                <input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} className={FIELD} />
              </label>
              <button type="submit" className={BTN}>{t.save}</button>
              <button type="button" className={BTN_LINE} onClick={close}>{t.cancel}</button>
            </form>
          )}
        </Toggle>
      </Header>
      <Alert text={error} />
      <Panel>
        {companies.data?.length === 0 && <p className="text-sm text-[#4a4439]">{t.none}</p>}
        <ul className="flex flex-col divide-y divide-[#ece8df]">
          {companies.data?.map((c) => (
            <li key={c.id}>
              <Link to={`/companies/${c.id}`} className="flex flex-wrap items-center justify-between gap-2 py-3.5 hover:text-[#8a5a00]">
                <span className="flex items-center gap-2 font-semibold"><Dot tone={!c.active ? "off" : c.silent_boxes ? "bad" : "good"} /><bdi>{c.name}</bdi>
                  {!c.active && <span className="text-xs text-[#6b6355]">· {t.suspended}</span>}</span>
                <span className="text-[13px] text-[#4a4439]">{t.counts(c.sites, c.people, c.boxes)}</span>
              </Link>
            </li>
          ))}
        </ul>
      </Panel>
    </>
  );
}

function CopyLink({ link }: { link: string }) {
  const t = useText(TEXT);
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <code dir="ltr" className="min-w-0 flex-1 break-all rounded-lg bg-[#f5f1ea] px-3 py-2 text-[13px]">{link}</code>
      <button type="button" className={BTN_LINE} onClick={async () => {
        try { await navigator.clipboard.writeText(link); setCopied(true); } catch { /* select it by hand */ }
      }}>
        {copied ? <Check className="h-4 w-4" aria-hidden="true" /> : <Copy className="h-4 w-4" aria-hidden="true" />}
        {copied ? t.copied : t.copy}
      </button>
    </div>
  );
}

export function Company() {
  const { id = "" } = useParams();
  const t = useText(TEXT);
  const words = useText(WORDS);
  const locale = useLocale();
  const me = useMe();
  const company = useQuery({ queryKey: ["company", id], queryFn: () => get<CompanyDetail>(`/companies/${id}`) });
  const { run, error } = useChange();
  const [site, setSite] = useState({ name: "", city: "" });
  const [person, setPerson] = useState({ email: "", name: "", role: "supervisor" as Role, site_ids: [] as number[] });
  const [link, setLink] = useState<{ name: string; link: string; emailed: boolean } | null>(null);

  const sets = useQuery({ queryKey: ["rule-sets"], queryFn: () => get<RuleSet[]>("/rule-sets"), staleTime: Infinity });
  const boxWords = useText(BOX_TEXT);
  const ruleNames = Object.fromEntries((sets.data ?? []).map((r) => [r.id, r.name]));
  const c = company.data;
  const role = me.data?.role;
  if (!c) return <div aria-busy="true" className="min-h-[40vh]" />;
  const canEdit = role === "overseer" || role === "manager";
  const roleChoices: Role[] = role === "overseer" ? ["manager", "supervisor", "viewer"] : ["supervisor", "viewer"];
  const siteName = (sid: number) => c.sites.find((s) => s.id === sid)?.name;

  const addPerson = async (e: FormEvent, close: () => void) => {
    e.preventDefault();
    const made = await run(() => send<{ name: string; invite_link: string; emailed: boolean }>(`/companies/${c.id}/people`, person));
    if (made) {
      setLink({ name: made.name, link: made.invite_link, emailed: made.emailed });
      setPerson({ email: "", name: "", role: "supervisor", site_ids: [] });
      close();
    }
  };
  const openConsole = async (siteId: number) => {
    const made = await run(() => send<{ url: string }>(`/sites/${siteId}/console`));
    if (made) window.location.assign(made.url);
  };
  const reinvite = async (p: CompanyPerson) => {
    const made = await run(() => send<{ invite_link: string; emailed: boolean }>(`/people/${p.id}/invite`));
    if (made) setLink({ name: p.name, link: made.invite_link, emailed: made.emailed });
  };

  return (
    <>
      <Header
        back={role === "overseer" ? <Link to="/companies" className="text-sm font-medium text-[#6b6355] no-underline">{t.allClients}</Link> : undefined}
        kicker={c.created_at ? t.since(new Date(c.created_at).toLocaleDateString(locale, { month: "long", year: "numeric" })) : undefined}
        title={<><bdi>{c.name}</bdi>{!c.active && <span className="ms-3 align-middle text-base font-semibold text-[#9a3412]">{t.suspended}</span>}</>}
      >
        {role === "overseer" && (
          <button type="button" className={BTN_LINE} title={t.suspendHint}
            onClick={() => run(() => send(`/companies/${c.id}`, { active: !c.active }, "PATCH"))}>
            {c.active ? t.suspend : t.resume}
          </button>
        )}
      </Header>
      <Alert text={error} />
      {link && (
        <Panel className="border-[#f2b705] bg-[#fffbeb]">
          <div className="flex flex-col gap-3">
            <p className="text-sm font-medium" dir="auto">{t.linkReady(link.name)}</p>
            <CopyLink link={link.link} />
            <p className="text-[13px] text-[#4a4439]">{link.emailed ? t.emailed : t.notEmailed}</p>
          </div>
        </Panel>
      )}

      <Panel title={t.sitesTitle}>
        {c.sites.length === 0 && <p className="mb-4 text-sm text-[#4a4439]">{t.noSites}</p>}
        <ul className="mb-4 grid gap-3 sm:grid-cols-2">
          {c.sites.map((s) => {
            const box = c.boxes.find((b) => b.site_id === s.id);
            return (
              <li key={s.id} className="flex flex-col gap-1 rounded-xl border border-[#e4ddd0] p-4">
                <span className="font-semibold"><bdi>{s.name}</bdi>{s.city ? <span className="font-normal text-[#6b6355]"> · {s.city}</span> : null}</span>
                <span className="flex items-center gap-2 text-[13px] text-[#4a4439]">
                  <Dot tone={!box ? "off" : box.silent ? "bad" : "good"} />
                  {box ? <>{t.box(box.serial)}{box.silent ? ` · ${t.silent}` : ""}</> : t.noBox}
                </span>
                {box && box.last_checkin && (
                  <span className="text-[13px] text-[#4a4439]">{healthLine(box.health as BoxHealth, boxWords, ruleNames)}</span>
                )}
                {role !== "overseer" && box?.connected && (
                  <button type="button" className={`${BTN} mt-2 self-start`} onClick={() => openConsole(s.id)}>
                    <ExternalLink className="h-4 w-4" aria-hidden="true" /> {t.openConsole}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
        {canEdit && (
          <Toggle label={t.addSite}>
            {(close) => (
              <form className="flex flex-wrap items-end gap-2.5" onSubmit={async (e) => {
                e.preventDefault();
                if (await run(() => send(`/companies/${c.id}/sites`, site))) { setSite({ name: "", city: "" }); close(); }
              }}>
                <label className="min-w-48 flex-1 text-sm font-medium">{t.siteName}
                  <input required minLength={2} value={site.name} onChange={(e) => setSite({ ...site, name: e.target.value })} className={FIELD} />
                </label>
                <label className="min-w-40 flex-1 text-sm font-medium">{t.city}
                  <input value={site.city} onChange={(e) => setSite({ ...site, city: e.target.value })} className={FIELD} />
                </label>
                <button type="submit" className={BTN}>{t.save}</button>
                <button type="button" className={BTN_LINE} onClick={close}>{t.cancel}</button>
              </form>
            )}
          </Toggle>
        )}
      </Panel>

      {canEdit && (
        <Panel title={t.peopleTitle} note={t.peopleNote}>
          <ul className="mb-4 flex flex-col divide-y divide-[#ece8df]">
            {c.people.map((p) => {
              const approved = p.devices.filter((d) => d.status === "approved");
              const pending = p.devices.filter((d) => d.status === "pending");
              return (
                <li key={p.id} className="flex flex-col gap-2 py-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <bdi className="font-semibold">{p.name}</bdi>
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${p.role === "manager" ? "bg-ink text-paper" : p.role === "supervisor" ? "bg-[#e0f2fe] text-[#075985]" : "bg-[#f1efe9] text-[#4a4439]"}`}>{words.role[p.role]}</span>
                      {!p.active && <span className="text-xs font-semibold text-[#9a3412]">{t.off}</span>}
                    </div>
                    {p.can_manage && p.id !== me.data?.id && (
                      <div className="flex flex-wrap gap-2">
                        <button type="button" className={BTN_LINE} onClick={() => reinvite(p)}>{t.newLink}</button>
                        <button type="button" className={BTN_LINE} onClick={() => run(() => send(`/people/${p.id}`, { active: !p.active }, "PATCH"))}>
                          {p.active ? t.switchOff : t.switchOn}
                        </button>
                      </div>
                    )}
                  </div>
                  <div className="text-[13px] text-[#4a4439]" dir="auto">
                    <span dir="ltr">{p.email}</span>
                    {p.site_ids.length > 0 && <> · {p.site_ids.map(siteName).filter(Boolean).join(", ")}</>}
                    {" · "}
                    {approved.length ? t.devices(approved.length) : t.waitingSetup}
                    {p.last_sign_in && <> · {t.lastIn(when(p.last_sign_in, locale))}</>}
                  </div>
                  {pending.map((d) => (
                    <div key={d.id} className="flex flex-wrap items-center gap-2.5 rounded-xl bg-[#fffbeb] px-3 py-2 text-sm">
                      <Dot tone="warn" /> {d.label}: {words.device.pending}
                      {p.can_manage && (
                        <button type="button" className={`${BTN} ms-auto min-h-9 py-1.5`}
                          onClick={() => run(() => send(`/devices/${d.id}/decision`, { decision: "approve" }))}>{t.approve}</button>
                      )}
                    </div>
                  ))}
                  {p.can_manage && approved.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {approved.map((d) => (
                        <span key={d.id} className="inline-flex items-center gap-2 rounded-full border border-[#e4ddd0] px-3 py-1 text-[13px]">
                          {d.label}
                          <button type="button" className="font-semibold text-[#9a3412] hover:underline"
                            onClick={() => run(() => send(`/devices/${d.id}/decision`, { decision: "revoke" }))}>{t.remove}</button>
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
          <Toggle label={t.addPerson}>
            {(close) => (
              <form className="grid gap-3 rounded-xl bg-[#f8f5ef] p-4 sm:grid-cols-2" onSubmit={(e) => addPerson(e, close)}>
                <label className="text-sm font-medium">{t.fullName}
                  <input required minLength={2} value={person.name} onChange={(e) => setPerson({ ...person, name: e.target.value })} className={FIELD} />
                </label>
                <label className="text-sm font-medium">{t.email}
                  <input type="email" required dir="ltr" value={person.email} onChange={(e) => setPerson({ ...person, email: e.target.value })} className={FIELD} />
                </label>
                <label className="text-sm font-medium">{t.role}
                  <select value={person.role} onChange={(e) => setPerson({ ...person, role: e.target.value as Role })} className={FIELD}>
                    {roleChoices.map((r) => <option key={r} value={r}>{words.role[r]}</option>)}
                  </select>
                </label>
                <fieldset className="text-sm">
                  <legend className="font-medium">{t.sitesFor}</legend>
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
                    {c.sites.map((s) => (
                      <label key={s.id} className="inline-flex items-center gap-2">
                        <input type="checkbox" checked={person.site_ids.includes(s.id)} onChange={(e) => setPerson({
                          ...person, site_ids: e.target.checked ? [...person.site_ids, s.id] : person.site_ids.filter((x) => x !== s.id),
                        })} />
                        {s.name}
                      </label>
                    ))}
                  </div>
                  {person.role === "manager" && <p className="mt-1 text-xs text-[#6b6355]">{t.allSites}</p>}
                </fieldset>
                <div className="flex flex-wrap gap-2.5 sm:col-span-2">
                  <button type="submit" className={BTN}>{t.save}</button>
                  <button type="button" className={BTN_LINE} onClick={close}>{t.cancel}</button>
                </div>
              </form>
            )}
          </Toggle>
        </Panel>
      )}

      {role === "overseer" && (
        <section className="flex flex-col gap-2 rounded-2xl bg-ink px-6 py-5 text-paper">
          <h2 className="font-serif text-2xl italic text-[#f2b705]">{t.cant}</h2>
          <p className="max-w-3xl text-[15px] leading-relaxed">{t.cantText}</p>
        </section>
      )}
    </>
  );
}
