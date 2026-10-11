import { afterEach, describe, expect, it, vi } from "vitest";
import type { Lang } from "./i18n";

// the language helpers read the current language from i18n; switch it per test
let lang: Lang = "en";
vi.mock("./i18n", async (original) => ({ ...(await original<typeof import("./i18n")>()), currentLang: () => lang }));

const { eventTypeLabel, incidentTitle, statusLabel } = await import("./terms");

afterEach(() => {
  lang = "en";
});

describe("incidentTitle", () => {
  it("names the missing gear", () => {
    expect(incidentTitle({ event_type: "PPE_MISSING", metadata: { missing_equipment: ["hard_hat"] } })).toBe("No hard hat");
  });
  it("joins two missing items with 'or'", () => {
    expect(incidentTitle({ event_type: "PPE_MISSING", metadata: { missing_equipment: ["hard_hat", "safety_vest"] } })).toBe(
      "No hard hat or safety vest",
    );
  });
  it("falls back to the category when the gear isn't known", () => {
    expect(incidentTitle({ event_type: "PPE_MISSING", metadata: {} })).toBe("Missing safety gear");
  });
  it("says other incidents as a sentence", () => {
    expect(incidentTitle({ event_type: "PERSON_NEAR_MACHINERY" })).toBe("Someone too close to machinery");
  });
  it("still shows something readable for a new code", () => {
    expect(incidentTitle({ event_type: "LADDER_MISUSE" })).toBe("Ladder misuse");
  });
  it("speaks Arabic", () => {
    lang = "ar";
    expect(incidentTitle({ event_type: "PPE_MISSING", metadata: { missing_equipment: ["hard_hat", "safety_vest"] } })).toBe(
      "بدون خوذة أو سترة عاكسة",
    );
    expect(incidentTitle({ event_type: "SMOKING" })).toBe("شخص يدخّن");
  });
});

describe("short names", () => {
  it("uses plain category names for filters and charts", () => {
    expect(eventTypeLabel("PPE_MISSING")).toBe("Missing safety gear");
    expect(eventTypeLabel("ZONE_OVER_CAPACITY")).toBe("Area over capacity");
  });
  it("matches the buttons: On it and Done", () => {
    expect(statusLabel("acknowledged")).toBe("On it");
    expect(statusLabel("resolved")).toBe("Done");
  });
});
