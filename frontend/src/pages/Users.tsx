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

export const ROLE_INFO: Record<Role, { label: string; text: string; style: string }> = {
  admin: { label: "Admin", text: "Everything, including managing users", style: "bg-slate-900 text-white ring-slate-900" },
  supervisor: { label: "Supervisor", text: "Watches cameras and handles incidents", style: "bg-sky-50 text-sky-800 ring-sky-600/20" },
  viewer: { label: "Viewer", text: "Read-only: can look but not change anything", style: "bg-slate-50 text-slate-600 ring-slate-500/20" },
};

function PasswordField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [copied, setCopied] = useState(false);
  return (
    <div>
      <div className="mt-1.5 flex gap-2">
        <input value={value} onChange={(e) => onChange(e.target.value)} className={`${INPUT} mt-0 font-mono`} minLength={8} required />
        <button type="button" onClick={() => onChange(generatePassword())} className={BUTTON_SECONDARY} title="Generate a new one">
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
          title="Copy"
        >
          <Copy className="h-4 w-4" />
        </button>
      </div>
      <p className="mt-1.5 text-xs text-slate-500">
        {copied ? "Copied." : "At least 8 characters. Share it with the person securely; they can change it under Account."}
      </p>
    </div>
  );
}

function AddUserDialog({ onClose }: { onClose: () => void }) {
  const { add } = useUserMutations();
  const [form, setForm] = useState({ email: "", name: "", role: "supervisor" as Role, password: generatePassword() });
  const set = (change: Partial<typeof form>) => setForm((f) => ({ ...f, ...change }));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    add.mutate(form, { onSuccess: onClose });
  };

  return (
    <Modal title="Add a user" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <label className="block text-sm font-medium text-slate-700">
          Full name
          <input value={form.name} onChange={(e) => set({ name: e.target.value })} className={INPUT} required autoFocus />
        </label>
        <label className="block text-sm font-medium text-slate-700">
          Email
          <input type="email" value={form.email} onChange={(e) => set({ email: e.target.value })} className={INPUT} required />
        </label>
        <fieldset>
          <legend className="text-sm font-medium text-slate-700">Role</legend>
          <div className="mt-1.5 space-y-2">
            {(Object.keys(ROLE_INFO) as Role[]).map((role) => (
              <label
                key={role}
                className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 ${
                  form.role === role ? "border-slate-900 ring-1 ring-slate-900" : "border-slate-200"
                }`}
              >
                <input type="radio" name="role" checked={form.role === role} onChange={() => set({ role })} className="mt-0.5" />
                <span>
                  <span className="block text-sm font-medium text-slate-900">{ROLE_INFO[role].label}</span>
                  <span className="block text-xs text-slate-500">{ROLE_INFO[role].text}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        <label className="block text-sm font-medium text-slate-700">
          Temporary password
          <PasswordField value={form.password} onChange={(password) => set({ password })} />
        </label>
        {add.isError && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{add.error.message}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className={BUTTON_SECONDARY}>
            Cancel
          </button>
          <button type="submit" disabled={add.isPending} className={BUTTON_PRIMARY}>
            Add user
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ResetPasswordDialog({ user, onClose }: { user: User; onClose: () => void }) {
  const { resetPassword } = useUserMutations();
  const [password, setPassword] = useState(generatePassword());

  return (
    <Modal title={`Reset password for ${user.name}`} onClose={onClose}>
      {resetPassword.isSuccess ? (
        <div className="space-y-4">
          <p className="text-sm text-slate-600">
            Done. {user.name} has been signed out everywhere and can now sign in with:
          </p>
          <p className="rounded-lg bg-slate-50 px-3 py-2 font-mono text-sm text-slate-900">{password}</p>
          <div className="flex justify-end">
            <button onClick={onClose} className={BUTTON_PRIMARY}>
              Close
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
            New temporary password
            <PasswordField value={password} onChange={setPassword} />
          </label>
          {resetPassword.isError && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{resetPassword.error.message}</p>
          )}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={onClose} className={BUTTON_SECONDARY}>
              Cancel
            </button>
            <button type="submit" disabled={resetPassword.isPending} className={BUTTON_PRIMARY}>
              Reset password
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

  if (me?.role !== "admin") return <Navigate to="/app" replace />;

  return (
    <>
      <PageHeader
        title="Users"
        subtitle="Who can sign in to the console, and what they can do"
        actions={
          <button onClick={() => setAdding(true)} className={BUTTON_PRIMARY}>
            <Plus className="h-4 w-4" /> Add user
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
                <tr className="border-b border-slate-200 text-left text-xs font-medium tracking-wide text-slate-500 uppercase">
                  <th className="px-5 py-3">User</th>
                  <th className="px-5 py-3">Role</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Last sign-in</th>
                  <th className="px-5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {users.data.map((u) => {
                  const isMe = u.id === me.id;
                  return (
                    <tr key={u.id} className={u.active ? "" : "bg-slate-50/60 text-slate-400"}>
                      <td className="px-5 py-3">
                        <p className={`font-medium ${u.active ? "text-slate-900" : ""}`}>
                          {u.name} {isMe && <span className="text-xs font-normal text-slate-400">(you)</span>}
                        </p>
                        <p className="text-xs text-slate-500">{u.email}</p>
                      </td>
                      <td className="px-5 py-3">
                        <select
                          value={u.role}
                          disabled={isMe || update.isPending}
                          onChange={(e) => update.mutate({ id: u.id, role: e.target.value as Role })}
                          className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-900 disabled:opacity-60"
                          aria-label={`Role of ${u.name}`}
                          title={isMe ? "You can't change your own role" : ROLE_INFO[u.role].text}
                        >
                          {(Object.keys(ROLE_INFO) as Role[]).map((r) => (
                            <option key={r} value={r}>
                              {ROLE_INFO[r].label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-5 py-3">
                        <span
                          className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${
                            u.active ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20" : "bg-slate-100 text-slate-500 ring-slate-500/20"
                          }`}
                        >
                          {u.active ? "Active" : "Disabled"}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-slate-500">{u.last_login_at ? timeAgo(u.last_login_at) : "Never"}</td>
                      <td className="px-5 py-3">
                        <div className="flex justify-end gap-2">
                          {isMe ? (
                            <Link to="/app/account" className={BUTTON_SECONDARY} title="Change your password">
                              <KeyRound className="h-4 w-4" />
                              <span className="hidden xl:inline">Change password</span>
                            </Link>
                          ) : (
                            <button onClick={() => setResetting(u)} className={BUTTON_SECONDARY} title="Reset password">
                              <KeyRound className="h-4 w-4" />
                              <span className="hidden xl:inline">Reset password</span>
                            </button>
                          )}
                          {!isMe && (
                            <button
                              onClick={() => update.mutate({ id: u.id, active: !u.active })}
                              disabled={update.isPending}
                              className={BUTTON_SECONDARY}
                              title={u.active ? "Disable: they can't sign in until enabled again" : "Enable"}
                            >
                              {u.active ? <UserX className="h-4 w-4" /> : <UserCheck className="h-4 w-4" />}
                              <span className="hidden xl:inline">{u.active ? "Disable" : "Enable"}</span>
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
        {(Object.keys(ROLE_INFO) as Role[]).map((r) => (
          <div key={r} className="rounded-lg bg-white ring-1 ring-ink/10 p-4">
            <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${ROLE_INFO[r].style}`}>
              {ROLE_INFO[r].label}
            </span>
            <p className="mt-2 text-sm text-slate-600">{ROLE_INFO[r].text}</p>
          </div>
        ))}
      </div>
      {adding && <AddUserDialog onClose={() => setAdding(false)} />}
      {resetting && <ResetPasswordDialog user={resetting} onClose={() => setResetting(null)} />}
    </>
  );
}
