import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import { PageHeader } from "../components/Layout";
import { BUTTON_PRIMARY, Card, INPUT } from "../components/ui";
import { useAuth } from "../lib/auth";
import { formatDateTime } from "../lib/format";
import { ROLE_INFO } from "./Users";

function ChangePassword() {
  const qc = useQueryClient();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [state, setState] = useState<{ busy?: boolean; error?: string; done?: boolean }>({});

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next.length < 8) return setState({ error: "The new password must be at least 8 characters." });
    if (next !== repeat) return setState({ error: "The new passwords don't match." });
    setState({ busy: true });
    try {
      const user = await api.changePassword(current, next);
      qc.setQueryData(["auth", "me"], user);
      setCurrent("");
      setNext("");
      setRepeat("");
      setState({ done: true });
    } catch (err) {
      setState({ error: err instanceof Error ? err.message : "Couldn't change the password." });
    }
  };

  return (
    <Card title="Change password">
      <form onSubmit={submit} className="max-w-sm space-y-4">
        <label className="block text-sm font-medium text-slate-700">
          Current password
          <input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} className={INPUT} required />
        </label>
        <label className="block text-sm font-medium text-slate-700">
          New password
          <input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} className={INPUT} required minLength={8} />
        </label>
        <label className="block text-sm font-medium text-slate-700">
          Repeat new password
          <input type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} className={INPUT} required />
        </label>
        {state.error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{state.error}</p>}
        {state.done && (
          <p className="flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
            <CheckCircle2 className="h-4 w-4" /> Password changed. Other devices have been signed out.
          </p>
        )}
        <button type="submit" disabled={state.busy || !current || !next || !repeat} className={BUTTON_PRIMARY}>
          Change password
        </button>
      </form>
    </Card>
  );
}

export function Account() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <>
      <PageHeader title="Account" subtitle="Your profile and password" />
      <div className="grid gap-6 lg:grid-cols-[20rem_1fr]">
        <Card title="Profile">
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="text-slate-500">Name</dt>
              <dd className="font-medium text-slate-900">{user.name}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Email</dt>
              <dd className="font-medium text-slate-900">{user.email}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Role</dt>
              <dd className="font-medium text-slate-900">{ROLE_INFO[user.role].label}</dd>
              <dd className="text-xs text-slate-500">{ROLE_INFO[user.role].text}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Member since</dt>
              <dd className="font-medium text-slate-900">{formatDateTime(user.created_at)}</dd>
            </div>
          </dl>
        </Card>
        <ChangePassword />
      </div>
    </>
  );
}
