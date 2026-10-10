/**
 * English and Arabic. The language follows the browser until someone picks one with the switch, which is
 * remembered on this device. Arabic turns the whole page right-to-left (<html dir="rtl">), so layouts use
 * logical classes (ms-/me-/ps-/pe-/start-/end-) rather than left/right.
 *
 * Text lives next to the component that shows it, as one object per language:
 *
 *   const TEXT = bilingual({ title: "Incidents", count: (n: number) => `${n} open` },
 *                          { title: "الحوادث", count: (n: number) => `${n} مفتوحة` });
 *   const t = useText(TEXT);   // t.title, t.count(3)
 *
 * `bilingual` makes TypeScript reject an Arabic object that misses or misnames an English entry.
 */
import { createContext, Fragment, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Lang = "en" | "ar";
const STORAGE_KEY = "sitesentry.lang";

/** Locale for dates and numbers: Egyptian Arabic, but with Western digits (as on Egyptian sites and receipts). */
export const LOCALES: Record<Lang, string> = { en: "en-GB", ar: "ar-EG-u-nu-latn" };

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "en" || saved === "ar") return saved;
  } catch {
    /* storage blocked: fall back to the browser */
  }
  const preferred = navigator.languages?.length ? navigator.languages : [navigator.language];
  return preferred.some((l) => l?.toLowerCase().startsWith("ar")) ? "ar" : "en";
}

interface LangState {
  lang: Lang;
  setLang: (lang: Lang) => void;
}

const LangContext = createContext<LangState>({ lang: "en", setLang: () => {} });

let current: Lang = "en";
/** The language outside React (formatting helpers). Kept in step by LanguageProvider. */
export function currentLang(): Lang {
  return current;
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  current = lang;

  useEffect(() => {
    const root = document.documentElement;
    root.lang = lang;
    root.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);

  const setLang = useCallback((next: Lang) => {
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* not remembered, but still switched */
    }
    setLangState(next);
  }, []);

  const value = useMemo(() => ({ lang, setLang }), [lang, setLang]);
  // keyed by language: switching remounts the page, so text formatted outside React (dates, labels) changes
  // too. Cached server data survives (it lives in the query client above this provider).
  return (
    <LangContext.Provider value={value}>
      <Fragment key={lang}>{children}</Fragment>
    </LangContext.Provider>
  );
}

export function useLang() {
  return useContext(LangContext);
}

export interface Bilingual<T> {
  en: T;
  ar: T;
}

/** English and Arabic text with the same shape (TypeScript checks the Arabic against the English). */
export function bilingual<T>(en: T, ar: NoInfer<T>): Bilingual<T> {
  return { en, ar };
}

/** The current language's text from a bilingual() object. */
export function useText<T>(text: Bilingual<T>): T {
  return text[useLang().lang];
}

/** EN / عربي switch. */
export function LanguageSwitch({ className = "" }: { className?: string }) {
  const { lang, setLang } = useLang();
  const next: Lang = lang === "ar" ? "en" : "ar";
  return (
    <button
      type="button"
      onClick={() => setLang(next)}
      lang={next}
      aria-label={next === "ar" ? "التبديل إلى العربية" : "Switch to English"}
      className={`rounded-full px-3 py-1.5 text-sm font-semibold transition ${className}`}
    >
      {next === "ar" ? "عربي" : "EN"}
    </button>
  );
}

type PluralForms = Partial<Record<Intl.LDMLPluralRule, string>> & { other: string };
const pluralRules = new Map<string, Intl.PluralRules>();

/**
 * The right word for a count: Arabic has separate forms for 1, 2, 3–10 and 11+ ("one", "two", "few", "many").
 *   plural(lang, n, { one: "incident", other: "incidents" })
 *   plural(lang, n, { one: "حادثة", two: "حادثتان", few: "حوادث", many: "حادثة", other: "حادثة" })
 */
export function plural(lang: Lang, n: number, forms: PluralForms): string {
  let rules = pluralRules.get(lang);
  if (!rules) pluralRules.set(lang, (rules = new Intl.PluralRules(LOCALES[lang])));
  return forms[rules.select(n)] ?? forms.other;
}
