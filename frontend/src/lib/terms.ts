/**
 * Words the whole console shares: severities, statuses, roles, incident types, detected classes and missing
 * items, and an incident's title in plain words (incidentTitle). Unknown codes fall back to a readable version of
 * the code (PPE_MISSING -> "PPE missing"), so a new code still shows something sensible.
 *
 * Plugin text (rule names, zone names) comes from the plugin's own `translations.ar` block, see usePluginText.
 */
import { useRules } from "../api/queries";
import type { IncidentStatus, PluginTranslation, Role, Severity } from "../api/types";
import { humanize, humanizeItem } from "./format";
import { currentLang, type Lang } from "./i18n";

const SEVERITY_AR: Record<Severity, string> = { CRITICAL: "حرج", HIGH: "مرتفع", MEDIUM: "متوسط", LOW: "منخفض" };
const STATUS: Record<Lang, Record<IncidentStatus, string>> = {
  en: { open: "Open", acknowledged: "Acknowledged", resolved: "Resolved" },
  ar: { open: "مفتوحة", acknowledged: "تم الاستلام", resolved: "تم الحل" },
};
const ROLE: Record<Lang, Record<Role, string>> = {
  en: { admin: "Admin", supervisor: "Supervisor", viewer: "Viewer" },
  ar: { admin: "مسؤول", supervisor: "مشرف", viewer: "مشاهد" },
};
const EVENT_TYPE_AR: Record<string, string> = {
  PPE_MISSING: "معدات وقاية ناقصة",
  RESTRICTED_ZONE_ENTRY: "دخول منطقة محظورة",
  LOITERING_HAZARD_ZONE: "البقاء في منطقة خطرة",
  ZONE_OVER_CAPACITY: "تجاوز سعة المنطقة",
  PERSON_NEAR_MACHINERY: "شخص قرب آلة",
  SMOKING: "التدخين",
  VAPING: "السجائر الإلكترونية",
  FOOD_IN_RESTRICTED_ZONE: "طعام أو شراب في منطقة محظورة",
  PERSON_DOWN: "سقوط شخص",
  SLEEPING_ON_SITE: "النوم في الموقع",
};
const ITEM_AR: Record<string, string> = { hard_hat: "خوذة", safety_vest: "سترة عاكسة" };
// Short plain names for filters and charts (the codes are for machines)
const EVENT_TYPE_EN: Record<string, string> = {
  PPE_MISSING: "Missing safety gear",
  RESTRICTED_ZONE_ENTRY: "Restricted area entry",
  LOITERING_HAZARD_ZONE: "Staying in a danger zone",
  ZONE_OVER_CAPACITY: "Area over capacity",
  PERSON_NEAR_MACHINERY: "Too close to machinery",
  SMOKING: "Smoking",
  VAPING: "Vaping",
  FOOD_IN_RESTRICTED_ZONE: "Food or drink in a restricted area",
  PERSON_DOWN: "Person down",
  SLEEPING_ON_SITE: "Sleeping on site",
};
// What happened, as a person would say it: the title of one incident
const INCIDENT_TITLE: Record<Lang, Record<string, string>> = {
  en: {
    RESTRICTED_ZONE_ENTRY: "Someone entered a restricted area",
    LOITERING_HAZARD_ZONE: "Someone staying in a danger zone",
    ZONE_OVER_CAPACITY: "Too many people in one area",
    PERSON_NEAR_MACHINERY: "Someone too close to machinery",
    SMOKING: "Someone smoking",
    VAPING: "Someone vaping",
    FOOD_IN_RESTRICTED_ZONE: "Food or drink in a restricted area",
    PERSON_DOWN: "Someone may have fallen",
    SLEEPING_ON_SITE: "Someone may be asleep on site",
  },
  ar: {
    RESTRICTED_ZONE_ENTRY: "شخص دخل منطقة محظورة",
    LOITERING_HAZARD_ZONE: "شخص يبقى في منطقة خطرة",
    ZONE_OVER_CAPACITY: "عدد كبير من الأشخاص في منطقة واحدة",
    PERSON_NEAR_MACHINERY: "شخص قريب جدًا من آلة",
    SMOKING: "شخص يدخّن",
    VAPING: "شخص يستخدم سيجارة إلكترونية",
    FOOD_IN_RESTRICTED_ZONE: "طعام أو شراب في منطقة محظورة",
    PERSON_DOWN: "ربما سقط شخص",
    SLEEPING_ON_SITE: "ربما ينام شخص في الموقع",
  },
};
const CLASS_AR: Record<string, string> = {
  Person: "شخص",
  Hardhat: "خوذة",
  "NO-Hardhat": "بدون خوذة",
  "Safety Vest": "سترة عاكسة",
  "NO-Safety Vest": "بدون سترة",
  machinery: "آلات",
  vehicle: "مركبة",
  cigarette: "سيجارة",
  vape: "سيجارة إلكترونية",
  bottle: "زجاجة",
  cup: "كوب",
};
/** The incident payload's placeholder for a missing field (docs/contracts.md). */
export const NOT_SPECIFIED = "NOT SPECIFIED";

const ar = () => currentLang() === "ar";

export const severityLabel = (s: Severity | string) =>
  ar() ? (SEVERITY_AR[s as Severity] ?? s) : humanize(s);
export const statusLabel = (s: IncidentStatus | string) => STATUS[currentLang()][s as IncidentStatus] ?? humanize(s);
export const roleLabel = (r: Role | string) => ROLE[currentLang()][r as Role] ?? humanize(r);
export const eventTypeLabel = (code: string | null | undefined) =>
  (code && (ar() ? EVENT_TYPE_AR[code] : EVENT_TYPE_EN[code])) || humanize(code);
/** One incident in plain words: "No hard hat", "Someone too close to machinery". */
export function incidentTitle(i: { event_type: string; metadata?: { missing_equipment?: string[] } }): string {
  const missing = i.metadata?.missing_equipment ?? [];
  if (i.event_type === "PPE_MISSING" && missing.length) {
    const items = joinList(missing.map(itemLabel));
    return ar() ? `بدون ${items}` : `No ${items.toLowerCase()}`;
  }
  return INCIDENT_TITLE[currentLang()][i.event_type] ?? eventTypeLabel(i.event_type);
}
export const itemLabel = (item: string) => (ar() && ITEM_AR[item]) || humanizeItem(item);
/** A detector class name as shown to people (the model's own name in English). */
export const classLabel = (name: string) => (ar() && CLASS_AR[name]) || name;
export const notSpecified = () => (ar() ? "غير محدد" : "Not specified");

/**
 * Rule and zone names in the current language, from the plugin's translations (served with GET /rules).
 * Falls back to the plugin's English text.
 */
export function usePluginText() {
  const rules = useRules();
  const t: PluginTranslation = (ar() && rules.data?.translations?.ar) || {};
  const zoneByName = new Map(Object.entries(rules.data?.zones ?? {}).map(([id, name]) => [name, id]));
  return {
    pluginName: (english: string) => t.plugin_name ?? english,
    ruleName: (ruleId: string | undefined, english: string) => (ruleId && t.rules?.[ruleId]?.name) || english,
    ruleDescription: (ruleId: string, english: string) => t.rules?.[ruleId]?.description || english,
    ruleRequires: (ruleId: string, english: string | null) => t.rules?.[ruleId]?.requires || english,
    /** The site-approved steps for a rule (plugin recommended_actions), in the current language. */
    ruleActions: (ruleId: string | undefined): string[] => {
      const rule = rules.data?.rules.find((r) => r.rule_id === ruleId);
      return (ruleId && t.rules?.[ruleId]?.recommended_actions) || rule?.recommended_actions || [];
    },
    zoneName: (zoneId: string | null | undefined, english: string | null) => (zoneId && t.zones?.[zoneId]) || english,
    /** An incident's location: a zone name (translated through its zone id) or NOT SPECIFIED. */
    location: (location: string | null | undefined, zoneId?: string | null) => {
      if (!location || location === NOT_SPECIFIED) return null;
      const id = zoneId ?? zoneByName.get(location);
      return (id && t.zones?.[id]) || location;
    },
  };
}

/**
 * Joins parts that mix Latin and Arabic (a camera id, a zone, a date) with " · ", each part kept whole:
 * without Unicode isolation, right-to-left text reorders "cam_01 · 10/10/2026" into a jumble.
 */
export const joinParts = (parts: (string | null | undefined)[]) =>
  parts.filter(Boolean).map((p) => `\u2068${p}\u2069`).join(" · ");

/** "a, b, c" with the language's own comma (Arabic uses ،). */
export const joinList = (items: string[]) => items.join(ar() ? "، " : ", ");
