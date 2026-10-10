import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import { PageHeader } from "../components/Layout";
import { BUTTON_PRIMARY, Card, INPUT } from "../components/ui";
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
    subtitle: "Your profile and password",
    profile: "Profile",
    name: "Name",
    email: "Email",
    role: "Role",
    memberSince: "Member since",
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
    subtitle: "ملفك الشخصي وكلمة المرور",
    profile: "الملف الشخصي",
    name: "الاسم",
    email: "البريد الإلكتروني",
    role: "الدور",
    memberSince: "عضو منذ",
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
        <ChangePassword />
      </div>
    </>
  );
}
