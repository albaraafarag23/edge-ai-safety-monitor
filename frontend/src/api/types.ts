// Mirrors the backend responses. Incident fields follow docs/contracts.md.

export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
export type IncidentStatus = "open" | "acknowledged" | "resolved";

export interface Detection {
  detection_id: string;
  class_name: string;
  confidence: number;
  bbox: [number, number, number, number];
  attributes: Record<string, unknown>;
  missing_equipment?: string[];
}

export interface Incident {
  event_id: string;
  timestamp: string;
  plugin_id: string;
  camera_id: string;
  severity: Severity;
  event_type: string;
  location: string;
  duration_seconds: number;
  rules_violated: string[];
  snapshot_url: string | null;
  clip_url: string | null;
  metadata: {
    rule_id?: string;
    zone_id?: string | null;
    zone_name?: string | null;
    detected_entities?: string[];
    missing_equipment?: string[];
    objects_involved?: Detection[];
    frame_id?: number;
    model?: string;
  };
  // added by the backend
  received_at: string;
  status: IncidentStatus;
  status_note: string | null;
  status_updated_at: string | null;
  status_updated_by?: string | null; // name of who last changed the status
  report: { generated_by: string; delivery_status: DeliveryStatus | null } | null;
}

export type DeliveryStatus = "sent" | "retrying" | "failed" | "not_configured" | "suppressed_duplicate";

export interface Report {
  event_id: string;
  markdown: string;
  markdown_ar?: string | null; // Arabic version, when the report was written in both (contracts v2.4)
  generated_by: string;
  delivery: {
    status?: DeliveryStatus;
    recipients?: string[];
    attachments?: string[];
    error?: string | null;
    duplicate_of?: string;
    attempts?: number;
    next_attempt_at?: string;
  };
  created_at: string;
}

export interface Stats {
  hours: number;
  total: number;
  open: number;
  by_severity: Partial<Record<Severity, number>>;
  by_event_type: Record<string, number>;
  by_status: Record<IncidentStatus, number>;
  by_camera: Record<string, number>;
  timeline: { hour: string; count: number }[];
}

export interface FilterOptions {
  camera_ids: string[];
  event_types: string[];
  severities: Severity[];
  statuses: IncidentStatus[];
}

export interface IncidentQuery {
  limit?: number;
  offset?: number;
  severity?: string;
  status?: string;
  event_type?: string;
  camera_id?: string;
  hours?: number;
}

export type Role = "admin" | "supervisor" | "viewer";

export interface User {
  id: number;
  email: string;
  name: string;
  role: Role;
  active: boolean;
  created_at: string | null;
  last_login_at: string | null;
}

export interface Analytics {
  days: number;
  tz: string;
  total: number;
  previous_total: number;
  by_day: ({ day: string } & Record<Severity, number>)[];
  heatmap: { weekday: number; hour: number; count: number }[]; // weekday 1 = Monday
  by_zone: { key: string; count: number }[];
  by_type: { key: string; count: number }[];
  by_camera: { key: string; count: number }[];
  missing_equipment: { key: string; count: number }[];
  by_status: Record<IncidentStatus, number>;
  median_minutes_to_handle: number | null;
}

/** GET /zones: a plugin zone and, when redrawn in the console, its polygon as fractions of the picture (0-1). */
export interface Zone {
  zone_id: string;
  name: string;
  camera_id: string | null;
  plugin_polygon: [number, number][]; // the plugin's own, in pixels of the camera's frame
  polygon: [number, number][] | null;
  rules: { rule_id: string; name: string }[]; // the rules that use this zone
  changed_by: string | null;
  changed_at: string | null;
}

export interface Camera {
  camera_id: string;
  online: boolean;
  plugin_id: string | null;
  model: string | null;
  mode: "test" | "live" | null;
  location: string | null;
  fps: number | null;
  width: number | null;
  height: number | null;
  frame_width?: number | null; // the detector's frame (boxes and zone polygons are in these pixels)
  frame_height?: number | null;
  updated_at: string | null;
}

export interface ActiveHours {
  start: string; // "07:00", site time
  end: string; // before start = spans midnight
  days: number[]; // 0 = Monday
}

/** Rule fields the console can change. */
export interface RuleSettings {
  min_duration_s: number;
  severity: Severity;
  cooldown_s: number;
  max_count: number | null; // only rules with a capacity limit
  active_hours: ActiveHours | null; // null = always
}

export interface SafetyRule extends RuleSettings {
  rule_id: string;
  name: string;
  type: string;
  description: string;
  event_type: string;
  zone_id: string | null;
  zone_name: string | null;
  recommended_actions?: string[]; // site-approved steps, most important first
  available: boolean; // false: not usable yet, see requires
  planned: boolean;
  requires: string | null;
  enabled: boolean;
  defaults: RuleSettings; // the plugin's values
  changed: (keyof RuleSettings)[];
  changed_by: string | null;
  changed_at: string | null;
}

/** A plugin's text in another language (the plugin's `translations` block, docs/plugins.md). */
export interface PluginTranslation {
  plugin_name?: string;
  rules?: Record<string, { name?: string; description?: string; requires?: string; recommended_actions?: string[] }>;
  zones?: Record<string, string>;
}

export interface SafetyRules {
  plugin_id: string;
  plugin_name: string;
  timezone: string;
  rules: SafetyRule[];
  zones?: Record<string, string>; // zone id -> English name
  translations?: { ar?: PluginTranslation };
}

/** PATCH /rules/{id}: only the fields sent change; null resets a field to the plugin's value. */
export type RuleChange = { enabled?: boolean } & { [K in keyof RuleSettings]?: RuleSettings[K] | null };
