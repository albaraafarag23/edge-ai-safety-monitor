import { Clock, RotateCcw, SlidersHorizontal } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { useChangeRule, useRules } from "../api/queries";
import type { ActiveHours, RuleSettings, SafetyRule, Severity } from "../api/types";
import { PageHeader } from "../components/Layout";
import { BUTTON_PRIMARY, BUTTON_SECONDARY, Card, ErrorState, INPUT, Modal, SeverityBadge, Spinner } from "../components/ui";
import { useAuth } from "../lib/auth";
import { SEVERITY_ORDER, formatDuration, timeAgo } from "../lib/format";
import { DAY_NAMES, describeHours, settingsChange } from "../lib/rules";

// Sunday–Thursday: the usual site week in Egypt
const WORK_WEEK: ActiveHours = { start: "07:00", end: "17:00", days: [0, 1, 2, 3, 6] };

function Toggle({ checked, disabled, label, onChange }: {
  checked: boolean;
  disabled?: boolean;
  label: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? "bg-emerald-600" : "bg-slate-300"
      }`}
    >
      <span
        className={`inline-block h-5 w-5 rounded-full bg-white shadow transition ${checked ? "translate-x-[22px]" : "translate-x-0.5"}`}
        aria-hidden
      />
    </button>
  );
}

function Field({ label, hint, changed, children }: { label: string; hint?: string; changed?: boolean; children: ReactNode }) {
  return (
    <label className="block text-sm font-medium text-slate-700">
      <span className="flex items-center gap-2">
        {label}
        {changed && <span className="rounded bg-sky-50 px-1.5 text-[11px] font-medium text-sky-700">changed</span>}
      </span>
      {children}
      {hint && <span className="mt-1 block text-xs font-normal text-slate-500">{hint}</span>}
    </label>
  );
}

function SettingsDialog({ rule, timezone, onClose }: { rule: SafetyRule; timezone: string; onClose: () => void }) {
  const change = useChangeRule();
  const current: RuleSettings = {
    min_duration_s: rule.min_duration_s,
    severity: rule.severity,
    cooldown_s: rule.cooldown_s,
    max_count: rule.max_count,
    active_hours: rule.active_hours,
  };
  const [form, setForm] = useState<RuleSettings>(current);
  const set = (c: Partial<RuleSettings>) => setForm((f) => ({ ...f, ...c }));
  const hours = form.active_hours;
  const setHours = (c: Partial<ActiveHours>) => hours && set({ active_hours: { ...hours, ...c } });
  const isDefault = (key: keyof RuleSettings) => JSON.stringify(form[key]) === JSON.stringify(rule.defaults[key]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const diff = settingsChange(current, form);
    if (Object.keys(diff).length === 0) return onClose();
    change.mutate({ ruleId: rule.rule_id, change: diff }, { onSuccess: onClose });
  };

  return (
    <Modal title={`${rule.name} settings`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Alert after (s)" hint="How long it must last" changed={!isDefault("min_duration_s")}>
            <input
              type="number"
              min={0}
              max={3600}
              step={0.5}
              required
              value={form.min_duration_s}
              onChange={(e) => set({ min_duration_s: Number(e.target.value) })}
              className={INPUT}
            />
          </Field>
          <Field label="Repeat after (s)" hint="While it continues" changed={!isDefault("cooldown_s")}>
            <input
              type="number"
              min={0}
              max={3600}
              step={1}
              required
              value={form.cooldown_s}
              onChange={(e) => set({ cooldown_s: Number(e.target.value) })}
              className={INPUT}
            />
          </Field>
        </div>
        <Field label="Severity" changed={!isDefault("severity")}>
          <select value={form.severity} onChange={(e) => set({ severity: e.target.value as Severity })} className={INPUT}>
            {SEVERITY_ORDER.map((s) => (
              <option key={s} value={s}>
                {s.charAt(0) + s.slice(1).toLowerCase()}
              </option>
            ))}
          </select>
        </Field>
        {rule.defaults.max_count !== null && (
          <Field label="Maximum people allowed" hint={rule.zone_name ?? undefined} changed={!isDefault("max_count")}>
            <input
              type="number"
              min={0}
              max={100}
              required
              value={form.max_count ?? 0}
              onChange={(e) => set({ max_count: Number(e.target.value) })}
              className={INPUT}
            />
          </Field>
        )}
        <fieldset>
          <legend className="flex items-center gap-2 text-sm font-medium text-slate-700">
            Working hours
            {!isDefault("active_hours") && <span className="rounded bg-sky-50 px-1.5 text-[11px] font-medium text-sky-700">changed</span>}
          </legend>
          <div className="mt-1.5 flex gap-4 text-sm text-slate-700">
            <label className="flex items-center gap-2">
              <input type="radio" checked={!hours} onChange={() => set({ active_hours: null })} /> Always
            </label>
            <label className="flex items-center gap-2">
              <input type="radio" checked={!!hours} onChange={() => set({ active_hours: hours ?? WORK_WEEK })} /> Only during
            </label>
          </div>
          {hours && (
            <div className="mt-3 space-y-3 rounded-lg bg-slate-50 p-3">
              <div className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="time"
                  required
                  value={hours.start}
                  onChange={(e) => setHours({ start: e.target.value })}
                  className={`${INPUT} mt-0`}
                  aria-label="From"
                />
                to
                <input
                  type="time"
                  required
                  value={hours.end}
                  onChange={(e) => setHours({ end: e.target.value })}
                  className={`${INPUT} mt-0`}
                  aria-label="Until"
                />
              </div>
              <div className="flex flex-wrap gap-1.5">
                {DAY_NAMES.map((name, day) => {
                  const on = hours.days.includes(day);
                  return (
                    <button
                      key={name}
                      type="button"
                      aria-pressed={on}
                      onClick={() =>
                        setHours({ days: on ? hours.days.filter((d) => d !== day) : [...hours.days, day].sort((a, b) => a - b) })
                      }
                      className={`rounded-md px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${
                        on ? "bg-slate-900 text-white ring-slate-900" : "bg-white text-slate-600 ring-slate-300"
                      }`}
                    >
                      {name}
                    </button>
                  );
                })}
              </div>
              <p className="text-xs text-slate-500">
                Site time ({timezone}). If the end is earlier than the start, the hours run overnight.
              </p>
              {hours.days.length === 0 && <p className="text-xs text-red-700">Pick at least one day.</p>}
            </div>
          )}
        </fieldset>
        {change.isError && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{change.error.message}</p>}
        <div className="flex items-center justify-between gap-2 pt-2">
          <button
            type="button"
            onClick={() => setForm(rule.defaults)}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900"
          >
            <RotateCcw className="h-4 w-4" /> Plugin defaults
          </button>
          <div className="flex gap-2">
            <button type="button" onClick={onClose} className={BUTTON_SECONDARY}>
              Cancel
            </button>
            <button
              type="submit"
              disabled={change.isPending || (hours !== null && (hours.days.length === 0 || hours.start === hours.end))}
              className={BUTTON_PRIMARY}
            >
              Save
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}

function RuleRow({ rule, canEdit, onSettings }: { rule: SafetyRule; canEdit: boolean; onSettings: () => void }) {
  const change = useChangeRule();
  const pending = change.isPending;
  // show the new position straight away while the request is on its way
  const enabled = pending && change.variables.change.enabled !== undefined ? change.variables.change.enabled : rule.enabled;

  return (
    <li className={`flex items-start gap-4 px-5 py-4 ${enabled ? "" : "bg-slate-50/60"}`}>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className={`font-medium ${enabled ? "text-slate-900" : "text-slate-500"}`}>{rule.name}</p>
          <SeverityBadge severity={rule.severity} />
        </div>
        <p className="mt-0.5 text-sm text-slate-600">{rule.description}</p>
        <p className="mt-1 flex flex-wrap items-center gap-x-1.5 text-xs text-slate-400">
          <span>{rule.rule_id}</span>
          {rule.zone_name && <span>· {rule.zone_name}</span>}
          <span>· {rule.min_duration_s > 0 ? `alerts after ${formatDuration(rule.min_duration_s)}` : "alerts at once"}</span>
          {rule.max_count !== null && <span>· more than {rule.max_count} people</span>}
          {rule.active_hours && (
            <span className="inline-flex items-center gap-1 text-sky-700">
              · <Clock className="h-3 w-3" /> {describeHours(rule.active_hours)}
            </span>
          )}
          {rule.changed_by && rule.changed_at && (
            <span>
              · changed by {rule.changed_by} {timeAgo(rule.changed_at)}
            </span>
          )}
        </p>
        {change.isError && <p className="mt-1 text-sm text-red-700">{change.error.message}</p>}
      </div>
      <div className="flex items-center gap-3">
        {canEdit && (
          <button onClick={onSettings} className={BUTTON_SECONDARY} title="Settings">
            <SlidersHorizontal className="h-4 w-4" />
            <span className="hidden sm:inline">Settings</span>
            {rule.changed.length > 0 && <span className="h-1.5 w-1.5 rounded-full bg-sky-600" aria-label="changed" />}
          </button>
        )}
        <Toggle
          checked={enabled}
          disabled={!canEdit || pending}
          label={`${rule.name}: ${enabled ? "on" : "off"}`}
          onChange={(on) => change.mutate({ ruleId: rule.rule_id, change: { enabled: on } })}
        />
      </div>
    </li>
  );
}

function UnavailableRow({ rule }: { rule: SafetyRule }) {
  return (
    <li className="flex items-start gap-4 px-5 py-4">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-medium text-slate-700">{rule.name}</p>
          <SeverityBadge severity={rule.severity} />
          <span className="rounded-md bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 ring-1 ring-amber-600/20 ring-inset">
            {rule.planned ? "Coming soon" : "Not available yet"}
          </span>
        </div>
        <p className="mt-0.5 text-sm text-slate-600">{rule.description}</p>
        {rule.requires && <p className="mt-1 text-xs text-slate-500">Needs: {rule.requires}</p>}
      </div>
      <Toggle checked={false} disabled label={`${rule.name}: not available`} onChange={() => {}} />
    </li>
  );
}

export function Rules() {
  const { user } = useAuth();
  const rules = useRules();
  const [editing, setEditing] = useState<SafetyRule | null>(null);
  const canEdit = user?.role === "admin" || user?.role === "supervisor";
  const available = rules.data?.rules.filter((r) => r.available) ?? [];
  const unavailable = rules.data?.rules.filter((r) => !r.available) ?? [];
  const off = available.filter((r) => !r.enabled).length;

  return (
    <>
      <PageHeader
        title="Safety rules"
        subtitle={
          canEdit
            ? "Choose which rules raise incidents and alerts, and when. A rule that's off is ignored until you switch it back on."
            : "Which rules raise incidents and alerts. Only admins and supervisors can change them."
        }
      />
      {off > 0 && (
        <p className="mb-4 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900 ring-1 ring-amber-200">
          {off === 1 ? "1 rule is" : `${off} rules are`} switched off. These violations are not detected or reported.
        </p>
      )}
      {rules.isPending ? (
        <Card>
          <Spinner />
        </Card>
      ) : rules.isError ? (
        <Card>
          <ErrorState error={rules.error} onRetry={() => rules.refetch()} />
        </Card>
      ) : (
        <div className="space-y-6">
          <Card title={rules.data.plugin_name}>
            <ul className="-mx-5 -my-5 divide-y divide-slate-100">
              {available.map((rule) => (
                <RuleRow key={rule.rule_id} rule={rule} canEdit={canEdit} onSettings={() => setEditing(rule)} />
              ))}
            </ul>
          </Card>
          {unavailable.length > 0 && (
            <Card title="Coming soon">
              <ul className="-mx-5 -my-5 divide-y divide-slate-100">
                {unavailable.map((rule) => (
                  <UnavailableRow key={rule.rule_id} rule={rule} />
                ))}
              </ul>
            </Card>
          )}
        </div>
      )}
      {editing && rules.data && (
        <SettingsDialog
          key={editing.rule_id}
          rule={rules.data.rules.find((r) => r.rule_id === editing.rule_id) ?? editing}
          timezone={rules.data.timezone}
          onClose={() => setEditing(null)}
        />
      )}
    </>
  );
}
