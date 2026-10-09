import { useRules, useSwitchRule } from "../api/queries";
import type { SafetyRule } from "../api/types";
import { PageHeader } from "../components/Layout";
import { Card, ErrorState, SeverityBadge, Spinner } from "../components/ui";
import { useAuth } from "../lib/auth";
import { formatDuration, humanize, timeAgo } from "../lib/format";

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

function RuleRow({ rule, canEdit }: { rule: SafetyRule; canEdit: boolean }) {
  const switchRule = useSwitchRule();
  const pending = switchRule.isPending;
  // show the new position straight away while the request is on its way
  const enabled = pending ? switchRule.variables.enabled : rule.enabled;

  return (
    <li className={`flex items-start gap-4 px-5 py-4 ${enabled ? "" : "bg-slate-50/60"}`}>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className={`font-medium ${enabled ? "text-slate-900" : "text-slate-500"}`}>{humanize(rule.event_type)}</p>
          <SeverityBadge severity={rule.severity} />
          {!rule.available && (
            <span className="rounded-md bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 ring-1 ring-amber-600/20 ring-inset">
              Not available yet
            </span>
          )}
        </div>
        <p className="mt-0.5 text-sm text-slate-600">{rule.description}</p>
        <p className="mt-1 text-xs text-slate-400">
          {rule.rule_id}
          {rule.zone_name && ` · ${rule.zone_name}`}
          {rule.min_duration_s > 0 && ` · after ${formatDuration(rule.min_duration_s)}`}
          {rule.changed_by && rule.changed_at && ` · switched ${rule.enabled ? "on" : "off"} by ${rule.changed_by} ${timeAgo(rule.changed_at)}`}
        </p>
        {switchRule.isError && <p className="mt-1 text-sm text-red-700">{switchRule.error.message}</p>}
      </div>
      <Toggle
        checked={enabled}
        disabled={!canEdit || !rule.available || pending}
        label={`${humanize(rule.event_type)}: ${enabled ? "on" : "off"}`}
        onChange={(on) => switchRule.mutate({ ruleId: rule.rule_id, enabled: on })}
      />
    </li>
  );
}

export function Rules() {
  const { user } = useAuth();
  const rules = useRules();
  const canEdit = user?.role === "admin" || user?.role === "supervisor";
  const off = rules.data?.rules.filter((r) => r.available && !r.enabled).length ?? 0;

  return (
    <>
      <PageHeader
        title="Safety rules"
        subtitle={
          canEdit
            ? "Choose which rules raise incidents and alerts. A rule that's off is ignored until you switch it back on."
            : "Which rules raise incidents and alerts. Only admins and supervisors can change them."
        }
      />
      {off > 0 && (
        <p className="mb-4 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900 ring-1 ring-amber-200">
          {off === 1 ? "1 rule is" : `${off} rules are`} switched off. These violations are not detected or reported.
        </p>
      )}
      <Card title={rules.data?.plugin_name}>
        {rules.isPending ? (
          <Spinner />
        ) : rules.isError ? (
          <ErrorState error={rules.error} onRetry={() => rules.refetch()} />
        ) : (
          <ul className="-mx-5 -my-5 divide-y divide-slate-100">
            {rules.data.rules.map((rule) => (
              <RuleRow key={rule.rule_id} rule={rule} canEdit={canEdit} />
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
