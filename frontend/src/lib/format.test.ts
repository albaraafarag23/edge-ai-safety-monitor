import { describe, expect, it } from "vitest";
import { formatDuration, humanize, humanizeItem, timeAgo } from "./format";

describe("humanize", () => {
  it("keeps acronyms and lower-cases the rest", () => {
    expect(humanize("PPE_MISSING")).toBe("PPE missing");
    expect(humanize("PERSON_NEAR_MACHINERY")).toBe("Person near machinery");
  });
  it("handles missing values", () => {
    expect(humanize(undefined)).toBe("Unknown");
    expect(humanize("")).toBe("Unknown");
  });
});

describe("humanizeItem", () => {
  it("turns snake_case equipment into words", () => {
    expect(humanizeItem("hard_hat")).toBe("Hard hat");
  });
});

describe("formatDuration", () => {
  it("shows short durations with one decimal", () => {
    expect(formatDuration(3)).toBe("3.0 s");
  });
  it("switches to minutes", () => {
    expect(formatDuration(45)).toBe("45 s");
    expect(formatDuration(90)).toBe("1 min 30 s");
    expect(formatDuration(120)).toBe("2 min");
  });
  it("handles missing values", () => {
    expect(formatDuration(null)).toBe("—");
  });
});

describe("timeAgo", () => {
  const now = Date.parse("2026-10-07T12:00:00Z");
  it("says just now for the last few seconds", () => {
    expect(timeAgo("2026-10-07T11:59:55Z", now)).toBe("just now");
  });
  it("uses the largest whole unit", () => {
    expect(timeAgo("2026-10-07T11:55:00Z", now)).toMatch(/5 minutes ago/);
    expect(timeAgo("2026-10-07T09:00:00Z", now)).toMatch(/3 hours ago/);
  });
  it("handles missing values", () => {
    expect(timeAgo(null, now)).toBe("—");
  });
});
