import type { ActiveHours, RuleChange, RuleSettings } from "../api/types";

export const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** "Mon–Fri, 07:00–19:00" style summary of a rule's working hours. */
export function describeHours(hours: ActiveHours | null): string {
  if (!hours) return "Always";
  const days = [...hours.days].sort((a, b) => a - b);
  let dayText: string;
  if (days.length === 7) dayText = "Every day";
  else if (days.length > 2 && days.every((d, i) => i === 0 || d === days[i - 1] + 1))
    dayText = `${DAY_NAMES[days[0]]}–${DAY_NAMES[days[days.length - 1]]}`;
  else dayText = days.map((d) => DAY_NAMES[d]).join(", ");
  const overnight = hours.end < hours.start ? " (overnight)" : "";
  return `${dayText}, ${hours.start}–${hours.end}${overnight}`;
}

/** Only the fields that differ from the rule's current settings, for PATCH /rules/{id}. */
export function settingsChange(current: RuleSettings, next: RuleSettings): RuleChange {
  const change: RuleChange = {};
  for (const key of Object.keys(next) as (keyof RuleSettings)[]) {
    if (JSON.stringify(current[key]) !== JSON.stringify(next[key])) {
      (change as Record<string, unknown>)[key] = next[key];
    }
  }
  return change;
}
