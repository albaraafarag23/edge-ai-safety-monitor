import { Pencil, RefreshCw, RotateCcw, X } from "lucide-react";
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { cameraFrameUrl } from "../api/client";
import { useZoneMutations, useZones } from "../api/queries";
import type { Camera, Zone } from "../api/types";
import { timeAgo } from "../lib/format";
import { bilingual, useText } from "../lib/i18n";
import { joinList, usePluginText } from "../lib/terms";
import { Spinner } from "./ui";

// Draw the plugin's zones on the camera picture (backend/zone_settings.py). Points are fractions of the picture
// (0-1), so a zone fits whatever resolution the camera runs at; the rule engine scales them to each frame.

type Point = [number, number];

const TEXT = bilingual(
  {
    title: "Zones on this camera",
    hint: "Pick a zone, then drag its corners, or redraw it by clicking around the area. A person counts as inside when their feet are inside.",
    fromPlugin: "Original shape",
    drawnBy: (who: string, when: string) => `Drawn by ${who}, ${when}`,
    usedBy: (rules: string) => `Used by: ${rules}`,
    redraw: "Redraw",
    redrawing: "Click around the area, point by point. Click the first point (or Finish) to close it.",
    finish: "Finish",
    save: "Save zone",
    cancel: "Cancel",
    reset: "Back to the original shape",
    refresh: "New picture",
    close: "Close",
    saved: "Saved. The camera uses the new zone within a few seconds.",
    failed: (msg: string) => `Couldn't save: ${msg}`,
    needPoints: "A zone needs at least 3 points.",
    noZones: "This camera has no zones.",
    offline: "The camera is offline, so the picture may be old. Zones can still be drawn.",
  },
  {
    title: "المناطق على هذه الكاميرا",
    hint: "اختر منطقة ثم اسحب زواياها، أو أعد رسمها بالنقر حول المكان. يُعد الشخص داخلها حين تكون قدماه داخلها.",
    fromPlugin: "الشكل الأصلي",
    drawnBy: (who: string, when: string) => `رسمها ${who}، ${when}`,
    usedBy: (rules: string) => `تستخدمها: ${rules}`,
    redraw: "إعادة الرسم",
    redrawing: "انقر حول المكان نقطة بعد نقطة. انقر النقطة الأولى (أو «إنهاء») لإغلاقها.",
    finish: "إنهاء",
    save: "حفظ المنطقة",
    cancel: "إلغاء",
    reset: "العودة إلى الشكل الأصلي",
    refresh: "صورة جديدة",
    close: "إغلاق",
    saved: "تم الحفظ. تستخدم الكاميرا المنطقة الجديدة خلال ثوانٍ.",
    failed: (msg: string) => `تعذّر الحفظ: ${msg}`,
    needPoints: "تحتاج المنطقة إلى 3 نقاط على الأقل.",
    noZones: "لا توجد مناطق على هذه الكاميرا.",
    offline: "الكاميرا غير متصلة، فقد تكون الصورة قديمة. ما زال بالإمكان رسم المناطق.",
  },
);

const COLORS = ["#f59e0b", "#ef4444", "#3b82f6", "#10b981", "#a855f7", "#ec4899"];

/** The zone's polygon as fractions: the console's drawing, or the plugin's pixels divided by the frame size. */
function fractions(zone: Zone, camera: Camera): Point[] {
  if (zone.polygon) return zone.polygon;
  const w = camera.frame_width ?? camera.width ?? 640;
  const h = camera.frame_height ?? camera.height ?? 480;
  return zone.plugin_polygon.map(([x, y]) => [Math.min(1, Math.max(0, x / w)), Math.min(1, Math.max(0, y / h))]);
}

export function ZoneEditor({ camera, onClose }: { camera: Camera; onClose: () => void }) {
  const t = useText(TEXT);
  const plugin = usePluginText();
  const zones = useZones();
  const { draw, reset } = useZoneMutations();
  const mine = (zones.data ?? []).filter((z) => !z.camera_id || z.camera_id === camera.camera_id);
  const [selected, setSelected] = useState<string | null>(null);
  const [points, setPoints] = useState<Point[] | null>(null);   // the selected zone while it's being edited
  const [redrawing, setRedrawing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [picture, setPicture] = useState(() => `${cameraFrameUrl(camera.camera_id)}?t=${Date.now()}`);
  const box = useRef<HTMLDivElement>(null);
  const dragging = useRef<number | null>(null);

  const zone = mine.find((z) => z.zone_id === selected) ?? null;
  useEffect(() => {
    if (!selected && mine.length) setSelected(mine[0].zone_id);
  }, [mine, selected]);
  useEffect(() => {
    setPoints(zone ? fractions(zone, camera) : null);
    setRedrawing(false);
    // only when another zone is picked, or after a save brings the stored shape back
  }, [zone?.zone_id, zone?.changed_at]); // eslint-disable-line react-hooks/exhaustive-deps

  const at = (e: { clientX: number; clientY: number }): Point => {
    const r = box.current!.getBoundingClientRect();
    return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))];
  };

  const onPictureClick = (e: React.MouseEvent) => {
    if (!redrawing || !points) return;
    setPoints([...points, at(e)]);
  };
  const onHandleDown = (n: number) => (e: ReactPointerEvent) => {
    e.stopPropagation();
    if (redrawing) {
      if (n === 0 && points && points.length >= 3) setRedrawing(false);   // clicking the first point closes the shape
      return;
    }
    dragging.current = n;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onMove = (e: ReactPointerEvent) => {
    if (dragging.current === null || !points) return;
    const next = [...points];
    next[dragging.current] = at(e);
    setPoints(next);
  };
  const onUp = () => {
    dragging.current = null;
  };

  const save = () => {
    if (!zone || !points) return;
    if (points.length < 3) return setMessage(t.needPoints);
    draw.mutate(
      { zoneId: zone.zone_id, polygon: points },
      { onSuccess: () => setMessage(t.saved), onError: (e) => setMessage(t.failed(e.message)) },
    );
  };
  const changed = zone && points && JSON.stringify(points) !== JSON.stringify(fractions(zone, camera));
  const ratio = (camera.frame_width ?? camera.width ?? 640) / (camera.frame_height ?? camera.height ?? 480);

  return (
    <section className="rounded-2xl bg-white p-5 ring-1 ring-ink/[0.08]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-serif text-2xl text-ink">{t.title}</h2>
          <p className="mt-1 max-w-2xl text-sm text-ink/65">{t.hint}</p>
        </div>
        <button onClick={onClose} className="rounded-full p-1.5 text-ink/50 hover:bg-paper hover:text-ink" aria-label={t.close}>
          <X className="h-5 w-5" />
        </button>
      </div>
      {!camera.online && <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">{t.offline}</p>}

      {zones.isPending ? (
        <Spinner />
      ) : !mine.length ? (
        <p className="mt-4 text-ink/65">{t.noZones}</p>
      ) : (
        <div className="mt-4 grid gap-5 xl:grid-cols-[1fr_17rem]">
          <div>
            {/* the picture never flips in Arabic: zones are positions on the camera image */}
            <div
              ref={box}
              dir="ltr"
              className={`relative touch-none overflow-hidden rounded-xl bg-ink select-none ${redrawing ? "cursor-crosshair" : ""}`}
              style={{ aspectRatio: ratio }}
              onClick={onPictureClick}
              onPointerMove={onMove}
              onPointerUp={onUp}
            >
              <img src={picture} alt="" className="absolute inset-0 h-full w-full object-cover" draggable={false} />
              <svg viewBox="0 0 1 1" preserveAspectRatio="none" className="absolute inset-0 h-full w-full">
                {mine.map((z, n) => {
                  const pts = z.zone_id === selected && points ? points : fractions(z, camera);
                  const color = COLORS[n % COLORS.length];
                  const active = z.zone_id === selected;
                  const shape = pts.map((p) => p.join(",")).join(" ");
                  return active && redrawing ? (
                    <polyline key={z.zone_id} points={shape} fill="none" stroke={color} strokeWidth={2} vectorEffect="non-scaling-stroke" />
                  ) : (
                    <polygon
                      key={z.zone_id}
                      points={shape}
                      fill={color}
                      fillOpacity={active ? 0.28 : 0.12}
                      stroke={color}
                      strokeWidth={active ? 2.5 : 1.5}
                      strokeDasharray={active ? undefined : "4 3"}
                      vectorEffect="non-scaling-stroke"
                      onClick={(e) => {
                        if (redrawing) return;
                        e.stopPropagation();
                        setSelected(z.zone_id);
                      }}
                      className={redrawing ? "" : "cursor-pointer"}
                    />
                  );
                })}
              </svg>
              {points?.map(([x, y], n) => (
                <span
                  key={n}
                  onPointerDown={onHandleDown(n)}
                  className={`absolute h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow ${
                    redrawing && n === 0 ? "bg-emerald-500" : "bg-ink"
                  } ${redrawing ? "" : "cursor-grab active:cursor-grabbing"}`}
                  style={{ left: `${x * 100}%`, top: `${y * 100}%` }}
                />
              ))}
            </div>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-ink/65">{redrawing ? t.redrawing : ""}</p>
              <button
                onClick={() => setPicture(`${cameraFrameUrl(camera.camera_id)}?t=${Date.now()}`)}
                className="inline-flex items-center gap-1.5 text-sm font-medium text-ink/65 hover:text-ink"
              >
                <RefreshCw className="h-4 w-4" /> {t.refresh}
              </button>
            </div>
          </div>

          <div className="space-y-3">
            <ul className="space-y-2">
              {mine.map((z, n) => (
                <li key={z.zone_id}>
                  <button
                    onClick={() => setSelected(z.zone_id)}
                    className={`w-full rounded-xl p-3 text-start ring-1 transition ${
                      z.zone_id === selected ? "bg-paper ring-ink/40" : "ring-ink/10 hover:ring-ink/25"
                    }`}
                  >
                    <span className="flex items-center gap-2 font-semibold text-ink">
                      <span className="h-3 w-3 rounded-sm" style={{ background: COLORS[n % COLORS.length] }} />
                      {plugin.zoneName(z.zone_id, z.name)}
                    </span>
                    <span className="mt-0.5 block text-xs text-ink/60">
                      {z.changed_by && z.changed_at ? t.drawnBy(z.changed_by, timeAgo(z.changed_at)) : t.fromPlugin}
                    </span>
                    {z.rules.length > 0 && <span className="mt-0.5 block text-xs text-ink/60">{t.usedBy(joinList(z.rules.map((r) => plugin.ruleName(r.rule_id, r.name))))}</span>}
                  </button>
                </li>
              ))}
            </ul>

            {zone && (
              <div className="flex flex-wrap gap-2 border-t border-ink/10 pt-3">
                {redrawing ? (
                  <button
                    disabled={!points || points.length < 3}
                    onClick={() => setRedrawing(false)}
                    className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-paper disabled:opacity-40"
                  >
                    {t.finish}
                  </button>
                ) : (
                  <>
                    <button
                      disabled={!changed || draw.isPending}
                      onClick={save}
                      className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-paper disabled:opacity-40"
                    >
                      {t.save}
                    </button>
                    <button
                      onClick={() => {
                        setPoints([]);
                        setRedrawing(true);
                        setMessage(null);
                      }}
                      className="inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold ring-1 ring-ink/20 hover:bg-paper"
                    >
                      <Pencil className="h-4 w-4" /> {t.redraw}
                    </button>
                  </>
                )}
                {(changed || redrawing) && (
                  <button
                    onClick={() => {
                      setPoints(fractions(zone, camera));
                      setRedrawing(false);
                    }}
                    className="rounded-full px-4 py-2 text-sm font-medium text-ink/65 hover:text-ink"
                  >
                    {t.cancel}
                  </button>
                )}
                {zone.polygon && !redrawing && (
                  <button
                    disabled={reset.isPending}
                    onClick={() => reset.mutate(zone.zone_id, { onSuccess: () => setMessage(null) })}
                    className="inline-flex items-center gap-1.5 rounded-full px-3 py-2 text-sm font-medium text-ink/65 hover:text-ink"
                  >
                    <RotateCcw className="h-4 w-4" /> {t.reset}
                  </button>
                )}
              </div>
            )}
            {message && <p className="text-sm text-ink/75">{message}</p>}
          </div>
        </div>
      )}
    </section>
  );
}
