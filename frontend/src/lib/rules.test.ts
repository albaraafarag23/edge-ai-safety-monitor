import { describe, expect, it } from "vitest";
import type { RuleSettings } from "../api/types";
import { describeHours, settingsChange } from "./rules";

describe("describeHours", () => {
  it("says always when there are no working hours", () => {
    expect(describeHours(null)).toBe("Always");
  });
  it("shows a run of weekdays as a range", () => {
    expect(describeHours({ start: "07:00", end: "19:00", days: [4, 0, 1, 2, 3] })).toBe("Mon–Fri, 07:00–19:00");
  });
  it("shows a work week across the weekend as a range", () => {
    expect(describeHours({ start: "07:00", end: "17:00", days: [6, 0, 1, 2, 3] })).toBe("Sun–Thu, 07:00–17:00");
  });
  it("lists separate days and marks a night shift", () => {
    expect(describeHours({ start: "22:00", end: "06:00", days: [0, 2] })).toBe("Mon, Wed, 22:00–06:00 (overnight)");
  });
  it("says every day for all seven", () => {
    expect(describeHours({ start: "00:00", end: "23:59", days: [0, 1, 2, 3, 4, 5, 6] })).toBe("Every day, 00:00–23:59");
  });
});

describe("settingsChange", () => {
  const base: RuleSettings = { min_duration_s: 3, severity: "HIGH", cooldown_s: 10, max_count: null, active_hours: null };
  it("sends only what changed", () => {
    expect(settingsChange(base, { ...base, severity: "LOW", min_duration_s: 5 })).toEqual({ severity: "LOW", min_duration_s: 5 });
  });
  it("sends nothing when nothing changed", () => {
    expect(settingsChange(base, { ...base })).toEqual({});
  });
  it("sends working hours being removed as null", () => {
    const withHours = { ...base, active_hours: { start: "07:00", end: "19:00", days: [0] } };
    expect(settingsChange(withHours, base)).toEqual({ active_hours: null });
  });
});
