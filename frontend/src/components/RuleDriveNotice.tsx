import { Usb } from "lucide-react";
import { useRules } from "../api/queries";
import type { RuleDrive } from "../api/types";
import { bilingual, useText } from "../lib/i18n";

const TEXT = bilingual(
  {
    none: "No rule drive plugged in",
    noneHint: "The camera is watching and people are recognised, but no safety rules are checked and no incidents are raised. Plug in a SiteSentry rule drive to start.",
    loading: "Reading the rule drive…",
    loadingHint: "Checking its signature and copying the rules. This takes a few seconds.",
    refused: "This drive was not accepted",
    reasons: {
      unsigned: "It isn't signed by SiteSentry, or it was changed after signing.",
      wrong_drive: "These rules were made for a different drive. Copies don't work: use the original drive.",
      damaged: "Some of its files are missing or were changed.",
      no_keys: "This box has no key to check drives with. Contact SiteSentry support.",
      too_new: "It was made for a newer version of SiteSentry. Update the box first.",
      unreadable: "It couldn't be read. Try another USB port, or check the drive.",
    } as Record<string, string>,
    other: "Take it out and plug in a SiteSentry rule drive.",
  },
  {
    none: "لا توجد وحدة قواعد موصولة",
    noneHint: "الكاميرا تعمل ويُتعرَّف على الأشخاص، لكن لا تُطبَّق أي قواعد سلامة ولا تُسجَّل حوادث. صِل وحدة قواعد SiteSentry للبدء.",
    loading: "جارٍ قراءة وحدة القواعد…",
    loadingHint: "يُتحقَّق من توقيعها وتُنسخ القواعد. يستغرق ذلك بضع ثوانٍ.",
    refused: "لم تُقبل هذه الوحدة",
    reasons: {
      unsigned: "ليست موقّعة من SiteSentry، أو عُدِّلت بعد التوقيع.",
      wrong_drive: "صُنعت هذه القواعد لوحدة أخرى. النسخ لا تعمل: استخدم الوحدة الأصلية.",
      damaged: "بعض ملفاتها مفقود أو معدَّل.",
      no_keys: "لا يوجد في هذا الجهاز مفتاح للتحقق من الوحدات. تواصل مع دعم SiteSentry.",
      too_new: "صُنعت لإصدار أحدث من SiteSentry. حدِّث الجهاز أولًا.",
      unreadable: "تعذّرت قراءتها. جرّب منفذ USB آخر أو افحص الوحدة.",
    } as Record<string, string>,
    other: "انزعها وصِل وحدة قواعد SiteSentry.",
  },
);

/** A plain notice at the top of every console page when the box runs from rule drives and no rules are live. */
export function RuleDriveNotice() {
  const t = useText(TEXT);
  const rules = useRules();
  const source = rules.data?.source;
  if (!source || source.mode !== "drive") return null;
  const drive: RuleDrive = source.drive ?? {};
  if (drive.state === "active" && !source.base) return null;

  const [title, hint, tone] =
    drive.state === "loading"
      ? [t.loading, t.loadingHint, "bg-sky-50 text-sky-900 ring-sky-200"]
      : drive.state === "refused"
        ? [t.refused, `${t.reasons[drive.reason ?? ""] ?? ""} ${t.other}`.trim(), "bg-red-50 text-red-900 ring-red-200"]
        : [t.none, t.noneHint, "bg-amber-50 text-amber-950 ring-amber-200"];
  return (
    <div role="status" className={`mb-6 flex items-start gap-3 rounded-xl px-4 py-3 ring-1 ${tone}`}>
      <Usb className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
      <div>
        <p className="font-medium">{title}</p>
        <p className="mt-0.5 text-sm opacity-80">{hint}</p>
      </div>
    </div>
  );
}
