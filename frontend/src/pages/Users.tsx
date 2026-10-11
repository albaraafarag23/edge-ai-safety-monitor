import { Copy, KeyRound, Plus, RefreshCw, UserCheck, UserX } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";
import { useUserMutations, useUsers } from "../api/queries";
import type { Role, User } from "../api/types";
import { PageHeader } from "../components/Layout";
import {
  BUTTON_PRIMARY,
  BUTTON_SECONDARY,
  Card,
  ErrorState,
  INPUT,
  Modal,
  Spinner,
  generatePassword,
} from "../components/ui";
import { useAuth } from "../lib/auth";
import { timeAgo } from "../lib/format";
import { bilingual, useText } from "../lib/i18n";
import { roleLabel } from "../lib/terms";

const ROLES: Role[] = ["admin", "supervisor", "viewer"];
const ROLE_STYLE: Record<Role, string> = {
  admin: "bg-slate-900 text-white ring-slate-900",
  supervisor: "bg-sky-50 text-sky-800 ring-sky-600/20",
  viewer: "bg-slate-50 text-slate-600 ring-slate-500/20",
};

const TEXT = bilingual(
  {
    roleText: {
      admin: "Everything, including managing users",
      supervisor: "Watches cameras and handles incidents",
      viewer: "Read-only: can look but not change anything",
    } as Record<Role, string>,
    generate: "Generate a new one",
    copy: "Copy",
    copied: "Copied.",
    passwordHint: "At least 8 characters. Share it with the person securely; they can change it under Account.",
    addTitle: "Add a user",
    fullName: "Full name",
    email: "Email",
    role: "Role",
    tempPassword: "Temporary password",
    cancel: "Cancel",
    addUser: "Add user",
    resetTitle: (name: string) => `Reset password for ${name}`,
    resetDone: (name: string) => `Done. ${name} has been signed out everywhere and can now sign in with:`,
    close: "Close",
    newTempPassword: "New temporary password",
    resetPassword: "Reset password",
    title: "Users",
    subtitle: "Who can sign in to the console, and what they can do",
    head: { user: "User", role: "Role", status: "Status", lastSignIn: "Last sign-in", actions: "Actions" },
    you: "(you)",
    roleOf: (name: string) => `Role of ${name}`,
    cantChangeOwn: "You can't change your own role",
    active: "Active",
    disabled: "Disabled",
    never: "Never",
    changePassword: "Change password",
    disableHint: "Disable: they can't sign in until enabled again",
    disable: "Disable",
    enable: "Enable",
  },
  {
    roleText: {
      admin: "كل شيء، بما في ذلك إدارة المستخدمين",
      supervisor: "يتابع الكاميرات ويتعامل مع الحوادث",
      viewer: "قراءة فقط: يطّلع دون تغيير أي شيء",
    },
    generate: "إنشاء كلمة مرور جديدة",
    copy: "نسخ",
    copied: "تم النسخ.",
    passwordHint: "8 أحرف على الأقل. شاركها مع الشخص بطريقة آمنة، ويمكنه تغييرها من صفحة الحساب.",
    addTitle: "إضافة مستخدم",
    fullName: "الاسم الكامل",
    email: "البريد الإلكتروني",
    role: "الدور",
    tempPassword: "كلمة مرور مؤقتة",
    cancel: "إلغاء",
    addUser: "إضافة المستخدم",
    resetTitle: (name: string) => `إعادة تعيين كلمة مرور ${name}`,
    resetDone: (name: string) => `تم. سُجّل خروج ${name} من كل الأجهزة، ويمكنه الآن الدخول بكلمة المرور:`,
    close: "إغلاق",
    newTempPassword: "كلمة مرور مؤقتة جديدة",
    resetPassword: "إعادة تعيين كلمة المرور",
    title: "المستخدمون",
    subtitle: "من يمكنه الدخول إلى لوحة التحكم، وما الذي يمكنه فعله",
    head: { user: "المستخدم", role: "الدور", status: "الحالة", lastSignIn: "آخر دخول", actions: "الإجراءات" },
    you: "(أنت)",
    roleOf: (name: string) => `دور ${name}`,
    cantChangeOwn: "لا يمكنك تغيير دورك",
    active: "نشط",
    disabled: "معطّل",
    never: "لم يدخل بعد",
    changePassword: "تغيير كلمة المرور",
    disableHint: "تعطيل: لا يمكنه الدخول حتى يُفعَّل من جديد",
    disable: "تعطيل",
    enable: "تفعيل",
  },
);

/** Each role's name, what it can do and its badge style, in the current language. */
export function useRoleInfo(): Record<Role, { label: string; text: string; style: string }> {
  const t = useText(TEXT);
  return Object.fromEntries(
    ROLES.map((r) => [r, { label: roleLabel(r), text: t.roleText[r], style: ROLE_STYLE[r] }]),
  ) as Record<Role, { label: string; text: string; style: string }>;
}

function PasswordField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [copied, setCopied] = useState(false);
  const t = useText(TEXT);
  return (
    <div>
      <div className="mt-1.5 flex gap-2">
        <input value={value} onChange={(e) => onChange(e.target.value)} className={`${INPUT} mt-0 font-mono`} dir="ltr" minLength={8} required />
        <button type="button" onClick={() => onChange(generatePassword())} className={BUTTON_SECONDARY} title={t.generate}>
          <RefreshCw className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={async () => {
            await navigator.clipboard?.writeText(value);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1500);
          }}
          className={BUTTON_SECONDARY}
          title={t.copy}
        >
          <Copy className="h-4 w-4" />
        </button>
      </div>
      <p className="mt-1.5 text-xs text-slate-500">
        {copied ? t.copied : t.passwordHint}
      </p>
    </div>
  );
}

function AddUserDialog({ onClose }: { onClose: () => void }) {
  const { add } = useUserMutations();
  const [form, setForm] = useState({ email: "", name: "", role: "supervisor" as Role, password: generatePassword() });
  const set = (change: Partial<typeof form>) => setForm((f) => ({ ...f, ...change }));
  const t = useText(TEXT);
  const roleInfo = useRoleInfo();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    add.mutate(form, { onSuccess: onClose });
  };

  return (
    <Modal title={t.addTitle} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <label className="block text-sm font-medium text-slate-700">
          {t.fullName}
          <input value={form.name} onChange={(e) => set({ name: e.target.value })} className={INPUT} required autoFocus />
        </label>
        <label className="block text-sm font-medium text-slate-700">
          {t.email}
          <input type="email" dir="ltr" value={form.email} onChange={(e) => set({ email: e.target.value })} className={INPUT} required />
        </label>
        <fieldset>
          <legend className="text-sm font-medium text-slate-700">{t.role}</legend>
          <div className="mt-1.5 space-y-2">
            {ROLES.map((role) => (
              <label
                key={role}
                className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 ${
                  form.role === role ? "border-slate-900 ring-1 ring-slate-900" : "border-slate-200"
                }`}
              >
                <input type="radio" name="role" checked={form.role === role} onChange={() => set({ role })} className="mt-0.5" />
                <span>
                  <span className="block text-sm font-medium text-slate-900">{roleInfo[role].label}</span>
                  <span className="block text-xs text-slate-500">{roleInfo[role].text}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        <label className="block text-sm font-medium text-slate-700">
          {t.tempPassword}
          <PasswordField value={form.password} onChange={(password) => set({ password })} />
        </label>
        {add.isError && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{add.error.message}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className={BUTTON_SECONDARY}>
            {t.cancel}
          </button>
          <button type="submit" disabled={add.isPending} className={BUTTON_PRIMARY}>
            {t.addUser}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ResetPasswordDialog({ user, onClose }: { user: User; onClose: () => void }) {
  const { resetPassword } = useUserMutations();
  const [password, setPassword] = useState(generatePassword());
  const t = useText(TEXT);

  return (
    <Modal title={t.resetTitle(user.name)} onClose={onClose}>
      {resetPassword.isSuccess ? (
        <div className="space-y-4">
          <p className="text-sm text-slate-600">{t.resetDone(user.name)}</p>
          <p className="rounded-lg bg-slate-50 px-3 py-2 font-mono text-sm text-slate-900" dir="ltr">{password}</p>
          <div className="flex justify-end">
            <button onClick={onClose} className={BUTTON_PRIMARY}>
              {t.close}
            </button>
          </div>
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            resetPassword.mutate({ id: user.id, password });
          }}
          className="space-y-4"
        >
          <label className="block text-sm font-medium text-slate-700">
            {t.newTempPassword}
            <PasswordField value={password} onChange={setPassword} />
          </label>
          {resetPassword.isError && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{resetPassword.error.message}</p>
          )}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={onClose} className={BUTTON_SECONDARY}>
              {t.cancel}
            </button>
            <button type="submit" disabled={resetPassword.isPending} className={BUTTON_PRIMARY}>
              {t.resetPassword}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

export function Users() {
  const { user: me } = useAuth();
  const users = useUsers();
  const { update } = useUserMutations();
  const [adding, setAdding] = useState(false);
  const [resetting, setResetting] = useState<User | null>(null);
  const t = useText(TEXT);
  const roleInfo = useRoleInfo();

  if (me?.role !== "admin") return <Navigate to="/app" replace />;

  return (
    <>
      <PageHeader
        title={t.title}
        subtitle={t.subtitle}
        actions={
          <button onClick={() => setAdding(true)} className={BUTTON_PRIMARY}>
            <Plus className="h-4 w-4" /> {t.addUser}
          </button>
        }
      />
      {update.isError && (
        <p className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-red-200" role="alert">
          {update.error.message}
        </p>
      )}
      <Card>
        {users.isPending ? (
          <Spinner />
        ) : users.isError ? (
          <ErrorState error={users.error} onRetry={() => users.refetch()} />
        ) : (
          <div className="-mx-5 -my-5 overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-start text-xs font-medium tracking-wide text-slate-500 uppercase">
                  <th className="px-3 py-3 sm:px-5">{t.head.user}</th>
                  <th className="px-3 py-3 sm:px-5">{t.head.role}</th>
                  <th className="hidden px-3 py-3 sm:px-5 md:table-cell">{t.head.status}</th>
                  <th className="hidden px-3 py-3 sm:px-5 md:table-cell">{t.head.lastSignIn}</th>
                  <th className="px-3 py-3 sm:px-5 text-end">{t.head.actions}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {users.data.map((u) => {
                  const isMe = u.id === me.id;
                  return (
                    <tr key={u.id} className={u.active ? "" : "bg-slate-50/60 text-slate-400"}>
                      <td className="px-3 py-3 sm:px-5">
                        <p className={`font-medium ${u.active ? "text-slate-900" : ""}`}>
                          {u.name} {isMe && <span className="text-xs font-normal text-slate-400">{t.you}</span>}
                        </p>
                        <p className="text-xs text-slate-500">{u.email}</p>
                        {/* on phones, status and last sign-in live here instead of their own columns */}
                        <p className="mt-0.5 text-xs text-slate-500 md:hidden">
                          {u.active ? t.active : t.disabled} · {u.last_login_at ? timeAgo(u.last_login_at) : t.never}
                        </p>
                      </td>
                      <td className="px-3 py-3 sm:px-5">
                        <select
                          value={u.role}
                          disabled={isMe || update.isPending}
                          onChange={(e) => update.mutate({ id: u.id, role: e.target.value as Role })}
                          className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-900 disabled:opacity-60"
                          aria-label={t.roleOf(u.name)}
                          title={isMe ? t.cantChangeOwn : roleInfo[u.role].text}
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>
                              {roleInfo[r].label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="hidden px-3 py-3 sm:px-5 md:table-cell">
                        <span
                          className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${
                            u.active ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20" : "bg-slate-100 text-slate-500 ring-slate-500/20"
                          }`}
                        >
                          {u.active ? t.active : t.disabled}
                        </span>
                      </td>
                      <td className="hidden px-3 py-3 sm:px-5 text-slate-500 md:table-cell">{u.last_login_at ? timeAgo(u.last_login_at) : t.never}</td>
                      <td className="px-3 py-3 sm:px-5">
                        <div className="flex justify-end gap-2">
                          {isMe ? (
                            <Link to="/app/account" className={BUTTON_SECONDARY} title={t.changePassword}>
                              <KeyRound className="h-4 w-4" />
                              <span className="hidden xl:inline">{t.changePassword}</span>
                            </Link>
                          ) : (
                            <button onClick={() => setResetting(u)} className={BUTTON_SECONDARY} title={t.resetPassword}>
                              <KeyRound className="h-4 w-4" />
                              <span className="hidden xl:inline">{t.resetPassword}</span>
                            </button>
                          )}
                          {!isMe && (
                            <button
                              onClick={() => update.mutate({ id: u.id, active: !u.active })}
                              disabled={update.isPending}
                              className={BUTTON_SECONDARY}
                              title={u.active ? t.disableHint : t.enable}
                            >
                              {u.active ? <UserX className="h-4 w-4" /> : <UserCheck className="h-4 w-4" />}
                              <span className="hidden xl:inline">{u.active ? t.disable : t.enable}</span>
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        {ROLES.map((r) => (
          <div key={r} className="rounded-lg bg-white ring-1 ring-ink/10 p-4">
            <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${roleInfo[r].style}`}>
              {roleInfo[r].label}
            </span>
            <p className="mt-2 text-sm text-slate-600">{roleInfo[r].text}</p>
          </div>
        ))}
      </div>
      {adding && <AddUserDialog onClose={() => setAdding(false)} />}
      {resetting && <ResetPasswordDialog user={resetting} onClose={() => setResetting(null)} />}
    </>
  );
}
