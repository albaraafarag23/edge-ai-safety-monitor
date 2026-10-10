import type { ActiveHours, RuleChange, RuleSettings } from "../api/types";
import { currentLang } from "./i18n";

// day 0 = Monday, as in the backend
const DAYS = {
  en: { names: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], always: "Always", everyDay: "Every day", overnight: " (overnight)", comma: ", " },
  ar: {
    names: ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"],
    always: "دائمًا",
    everyDay: "كل يوم",
    overnight: " (وردية ليلية)",
    comma: "، ",
  },
};

/** Short day names in the current language, Monday first. */
export const dayNames = () => DAYS[currentLang()].names;

/** "Mon–Fri, 07:00–19:00" style summary of a rule's working hours. */
export function describeHours(hours: ActiveHours | null): string {
  const words = DAYS[currentLang()];
  const DAY_NAMES = words.names;
  if (!hours) return words.always;
  const days = [...hours.days].sort((a, b) => a - b);
  // a run of 3+ days, possibly across the weekend (Sun–Thu)
  const first = days.find((d) => days.every((_, i) => days.includes((d + i) % 7)));
  let dayText: string;
  if (days.length === 7) dayText = words.everyDay;
  else if (days.length > 2 && first !== undefined) dayText = `${DAY_NAMES[first]}–${DAY_NAMES[(first + days.length - 1) % 7]}`;
  else dayText = days.map((d) => DAY_NAMES[d]).join(words.comma);
  const overnight = hours.end < hours.start ? words.overnight : "";
  return `${dayText}${words.comma}${hours.start}–${hours.end}${overnight}`;
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
