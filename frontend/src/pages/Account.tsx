import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { AlertLevel } from "../api/types";
import { PageHeader } from "../components/Layout";
import { BUTTON_PRIMARY, Card, ErrorState, INPUT, Spinner } from "../components/ui";
import { useAuth } from "../lib/auth";
import { formatDateTime } from "../lib/format";
import { bilingual, useText } from "../lib/i18n";
import { useRoleInfo } from "./Users";

const TEXT = bilingual(
  {
    tooShort: "The new password must be at least 8 characters.",
    noMatch: "The new passwords don't match.",
    failed: "Couldn't change the password.",
    changePassword: "Change password",
    current: "Current password",
    new: "New password",
    repeat: "Repeat new password",
    changed: "Password changed. Other devices have been signed out.",
    title: "Account",
    subtitle: "Your profile, password and alert emails",
    profile: "Profile",
    name: "Name",
    email: "Email",
    role: "Role",
    memberSince: "Member since",
    demo: "This is the shared demo account. It can look at everything but change nothing, including its own password.",
    alerts: {
      title: "Alert emails",
      what: "Which incidents are emailed to you, with the snapshot, clip and report.",
      levels: {
        CRITICAL: ["Critical only", "Only the most serious incidents"],
        HIGH: ["High and critical", "Recommended: the incidents that need someone now"],
        MEDIUM: ["Medium and up", "Adds the less urgent ones"],
        LOW: ["Everything", "Every incident, including low ones: can be a lot of email"],
        OFF: ["None", "No incident emails. You still see everything in the console"],
      } as Record<AlertLevel, [string, string]>,
      summary: "Also send me the end-of-day summary",
      sendTo: "Send to",
      signInEmail: (email: string) => `My sign-in email (${email})`,
      otherEmail: "Another address",
      save: "Save",
      saving: "Saving…",
      saved: "Saved.",
      failed: "Couldn't save. Try again.",
      isDefault: "You haven't chosen yet, so this is the default for your role.",
      demo: "The shared demo account doesn't get email.",
    },
  },
  {
    tooShort: "يجب ألا تقل كلمة المرور الجديدة عن 8 أحرف.",
    noMatch: "كلمتا المرور الجديدتان غير متطابقتين.",
    failed: "تعذّر تغيير كلمة المرور.",
    changePassword: "تغيير كلمة المرور",
    current: "كلمة المرور الحالية",
    new: "كلمة المرور الجديدة",
    repeat: "تأكيد كلمة المرور الجديدة",
    changed: "تم تغيير كلمة المرور، وسُجّل الخروج من الأجهزة الأخرى.",
    title: "الحساب",
    subtitle: "ملفك الشخصي وكلمة المرور وتنبيهات البريد",
    profile: "الملف الشخصي",
    name: "الاسم",
    email: "البريد الإلكتروني",
    role: "الدور",
    memberSince: "عضو منذ",
    demo: "هذا حساب العرض المشترك. يستطيع الاطلاع على كل شيء دون تغيير أي شيء، بما في ذلك كلمة مروره.",
    alerts: {
      title: "تنبيهات البريد",
      what: "الحوادث التي تصلك بالبريد، مع اللقطة والمقطع والتقرير.",
      levels: {
        CRITICAL: ["الحرجة فقط", "أخطر الحوادث فقط"],
        HIGH: ["المرتفعة والحرجة", "المقترح: الحوادث التي تحتاج إلى تدخّل الآن"],
        MEDIUM: ["المتوسطة فما فوق", "تضيف الحوادث الأقل إلحاحًا"],
        LOW: ["كل الحوادث", "كل حادثة، حتى المنخفضة: قد يكثر البريد"],
        OFF: ["لا شيء", "لا رسائل عن الحوادث، وتبقى كلها ظاهرة في لوحة التحكم"],
      },
      summary: "أرسل إليّ أيضًا ملخص نهاية اليوم",
      sendTo: "الإرسال إلى",
      signInEmail: (email: string) => `بريد الدخول (${email})`,
      otherEmail: "عنوان آخر",
      save: "حفظ",
      saving: "جارٍ الحفظ…",
      saved: "تم الحفظ.",
      failed: "تعذّر الحفظ. حاول مرة أخرى.",
      isDefault: "لم تختر بعد، فهذا هو الإعداد المعتاد لدورك.",
      demo: "حساب العرض المشترك لا تصله رسائل بريد.",
    },
  },
);

function ChangePassword() {
  const qc = useQueryClient();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [state, setState] = useState<{ busy?: boolean; error?: string; done?: boolean }>({});
  const t = useText(TEXT);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next.length < 8) return setState({ error: t.tooShort });
    if (next !== repeat) return setState({ error: t.noMatch });
    setState({ busy: true });
    try {
      const user = await api.changePassword(current, next);
      qc.setQueryData(["auth", "me"], user);
      setCurrent("");
      setNext("");
      setRepeat("");
      setState({ done: true });
    } catch (err) {
      setState({ error: err instanceof Error ? err.message : t.failed });
    }
  };

  return (
    <Card title={t.changePassword}>
      <form onSubmit={submit} className="max-w-sm space-y-4">
        <label className="block text-sm font-medium text-slate-700">
          {t.current}
          <input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} className={INPUT} required />
        </label>
        <label className="block text-sm font-medium text-slate-700">
          {t.new}
          <input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} className={INPUT} required minLength={8} />
        </label>
        <label className="block text-sm font-medium text-slate-700">
          {t.repeat}
          <input type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} className={INPUT} required />
        </label>
        {state.error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{state.error}</p>}
        {state.done && (
          <p className="flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
            <CheckCircle2 className="h-4 w-4" /> {t.changed}
          </p>
        )}
        <button type="submit" disabled={state.busy || !current || !next || !repeat} className={BUTTON_PRIMARY}>
          {t.changePassword}
        </button>
      </form>
    </Card>
  );
}

const LEVELS: AlertLevel[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "OFF"];

/** Each person chooses their own alert emails: where to, from which severity up, and the daily summary. */
function AlertEmails({ signInEmail }: { signInEmail: string }) {
  const t = useText(TEXT).alerts;
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["auth", "alerts"], queryFn: api.myAlerts });
  const data = query.data;
  const [level, setLevel] = useState<AlertLevel>("HIGH");
  const [summary, setSummary] = useState(false);
  const [own, setOwn] = useState(false);
  const [email, setEmail] = useState("");
  useEffect(() => {
    if (!data) return;
    setLevel(data.level);
    setSummary(data.summary);
    setOwn(data.own_email);
    setEmail(data.own_email ? data.email : "");
  }, [data]);
  const save = useMutation({
    mutationFn: () => api.setMyAlerts({ email: own ? email.trim() : null, level, summary }),
    onSuccess: (saved) => qc.setQueryData(["auth", "alerts"], saved),
  });

  if (query.isPending) return <Card title={t.title}><Spinner /></Card>;
  if (query.isError || !data) return <Card title={t.title}><ErrorState error={query.error} onRetry={() => query.refetch()} /></Card>;
  if (data.locked) return <Card title={t.title}><p className="max-w-sm text-sm text-slate-600">{t.demo}</p></Card>;

  const changed = level !== data.level || summary !== data.summary || own !== data.own_email ||
    (own && email.trim().toLowerCase() !== (data.own_email ? data.email : ""));
  const reset = () => save.reset();
  return (
    <Card title={t.title}>
      <form className="max-w-md space-y-5" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <p className="text-sm text-slate-600">{t.what}</p>
        <fieldset className="space-y-2">
          {LEVELS.map((l) => (
            <label key={l} className="flex cursor-pointer items-start gap-3 rounded-lg px-2 py-1.5 hover:bg-slate-50">
              <input type="radio" name="alert-level" value={l} checked={level === l}
                onChange={() => { setLevel(l); reset(); }} className="mt-1" />
              <span>
                <span className="block text-sm font-medium text-slate-900">{t.levels[l][0]}</span>
                <span className="block text-xs text-slate-500">{t.levels[l][1]}</span>
              </span>
            </label>
          ))}
        </fieldset>
        <label className="flex cursor-pointer items-center gap-3 text-sm text-slate-700">
          <input type="checkbox" checked={summary} onChange={(e) => { setSummary(e.target.checked); reset(); }} />
          {t.summary}
        </label>
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium text-slate-700">{t.sendTo}</legend>
          <label className="flex cursor-pointer items-center gap-3 text-sm text-slate-700">
            <input type="radio" name="alert-to" checked={!own} onChange={() => { setOwn(false); reset(); }} />
            <span className="break-all">{t.signInEmail(signInEmail)}</span>
          </label>
          <label className="flex cursor-pointer items-center gap-3 text-sm text-slate-700">
            <input type="radio" name="alert-to" checked={own} onChange={() => { setOwn(true); reset(); }} />
            {t.otherEmail}
          </label>
          {own && (
            <input type="email" dir="ltr" required autoComplete="email" value={email}
              onChange={(e) => { setEmail(e.target.value); reset(); }} className={INPUT} aria-label={t.otherEmail} />
          )}
        </fieldset>
        {!data.chosen && <p className="text-xs text-slate-500">{t.isDefault}</p>}
        <div className="flex items-center gap-3">
          <button type="submit" disabled={!changed || save.isPending} className={BUTTON_PRIMARY}>
            {save.isPending ? t.saving : t.save}
          </button>
          <span className="text-sm" role="status">
            {save.isError ? (
              <span className="text-red-700">{save.error instanceof Error ? save.error.message : t.failed}</span>
            ) : save.isSuccess && !changed ? (
              <span className="text-slate-600">{t.saved}</span>
            ) : null}
          </span>
        </div>
      </form>
    </Card>
  );
}

export function Account() {
  const { user } = useAuth();
  const t = useText(TEXT);
  const roleInfo = useRoleInfo();
  if (!user) return null;
  return (
    <>
      <PageHeader title={t.title} subtitle={t.subtitle} />
      <div className="grid gap-6 lg:grid-cols-[20rem_1fr]">
        <Card title={t.profile}>
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="text-slate-500">{t.name}</dt>
              <dd className="font-medium text-slate-900">{user.name}</dd>
            </div>
            <div>
              <dt className="text-slate-500">{t.email}</dt>
              <dd className="font-medium text-slate-900">{user.email}</dd>
            </div>
            <div>
              <dt className="text-slate-500">{t.role}</dt>
              <dd className="font-medium text-slate-900">{roleInfo[user.role].label}</dd>
              <dd className="text-xs text-slate-500">{roleInfo[user.role].text}</dd>
            </div>
            <div>
              <dt className="text-slate-500">{t.memberSince}</dt>
              <dd className="font-medium text-slate-900">{formatDateTime(user.created_at)}</dd>
            </div>
          </dl>
        </Card>
        {user.demo ? (
          <Card title={t.changePassword}>
            <p className="max-w-sm text-sm text-slate-600">{t.demo}</p>
          </Card>
        ) : (
          <ChangePassword />
        )}
        <div className="lg:col-start-2">
          <AlertEmails signInEmail={user.email} />
        </div>
      </div>
    </>
  );
}
