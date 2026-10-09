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
  report: { generated_by: string; delivery_status: DeliveryStatus | null } | null;
}

export type DeliveryStatus = "sent" | "failed" | "not_configured" | "suppressed_duplicate";

export interface Report {
  event_id: string;
  markdown: string;
  generated_by: string;
  delivery: {
    status?: DeliveryStatus;
    recipients?: string[];
    attachments?: string[];
    error?: string | null;
    duplicate_of?: string;
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
  updated_at: string | null;
}

export interface SafetyRule {
  rule_id: string;
  type: string;
  description: string;
  event_type: string;
  severity: Severity;
  zone_name: string | null;
  min_duration_s: number;
  available: boolean; // false: not usable yet (e.g. the model can't detect its classes)
  enabled: boolean;
  changed_by: string | null;
  changed_at: string | null;
}

export interface SafetyRules {
  plugin_id: string;
  plugin_name: string;
  rules: SafetyRule[];
}
