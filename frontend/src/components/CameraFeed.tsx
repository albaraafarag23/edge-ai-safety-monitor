import { CameraOff, Maximize2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cameraStreamUrl } from "../api/client";
import type { Camera } from "../api/types";
import { bilingual, useText } from "../lib/i18n";

const TEXT = bilingual(
  {
    live: "LIVE",
    offline: "OFFLINE",
    testMode: "TEST MODE",
    fullScreen: "Full screen",
    cameraOffline: "Camera offline",
    waiting: "Waiting for the detector to send frames…",
  },
  {
    live: "مباشر",
    offline: "غير متصل",
    testMode: "وضع الاختبار",
    fullScreen: "ملء الشاشة",
    cameraOffline: "الكاميرا غير متصلة",
    waiting: "في انتظار أن يرسل النظام الصور…",
  },
);

/**
 * Live view of one camera: a Motion-JPEG stream in a plain <img>, with a status overlay.
 * The stream holds a connection open, so it's only mounted while visible and is reconnected
 * when the camera comes back online.
 */
export function CameraFeed({ camera, className = "", showFullscreen = true }: {
  camera: Camera;
  className?: string;
  showFullscreen?: boolean;
}) {
  const t = useText(TEXT);
  const box = useRef<HTMLDivElement>(null);
  const img = useRef<HTMLImageElement>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  // retry the stream when the camera reports online again
  useEffect(() => {
    if (camera.online) {
      setFailed(false);
      setAttempt((a) => a + 1);
    }
  }, [camera.online]);

  // browsers keep an <img> stream open after unmount unless its src is cleared
  useEffect(
    () => () => {
      if (img.current) img.current.src = "";
    },
    [],
  );

  const live = camera.online && !failed;
  const ratio = camera.width && camera.height ? `${camera.width} / ${camera.height}` : "16 / 9";

  return (
    <div
      ref={box}
      className={`group relative overflow-hidden rounded-xl bg-slate-950 ring-1 ring-slate-900/10 ${className}`}
      style={{ aspectRatio: ratio }}
    >
      {live ? (
        <img
          ref={img}
          key={attempt}
          src={`${cameraStreamUrl(camera.camera_id)}?n=${attempt}`}
          alt={`Live view of ${camera.camera_id}`}
          onError={() => setFailed(true)}
          className="h-full w-full object-contain"
        />
      ) : (
        <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-slate-500">
          <CameraOff className="h-8 w-8" aria-hidden />
          <p className="text-sm font-medium text-slate-400">{t.cameraOffline}</p>
          <p className="text-xs">{t.waiting}</p>
        </div>
      )}

      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between bg-gradient-to-b from-black/60 to-transparent p-3 text-white">
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 text-[10px] font-bold tracking-wider ${
              live ? "bg-red-600" : "bg-slate-600"
            }`}
          >
            {live && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" />}
            {live ? t.live : t.offline}
          </span>
          <span className="text-xs font-medium drop-shadow">{camera.camera_id}</span>
          {camera.location && <span className="hidden text-xs text-white/70 sm:inline">· {camera.location}</span>}
        </div>
        <div className="flex items-center gap-2 text-[11px] text-white/80">
          {camera.mode === "test" && <span className="rounded bg-amber-400/90 px-1.5 py-0.5 font-semibold text-slate-950">{t.testMode}</span>}
          {live && camera.fps !== null && <span className="tabular-nums">{camera.fps.toFixed(1)} fps</span>}
        </div>
      </div>

      {showFullscreen && live && (
        <button
          onClick={() => box.current?.requestFullscreen?.()}
          className="absolute end-3 bottom-3 rounded-md bg-black/50 p-1.5 text-white opacity-0 transition group-hover:opacity-100 focus:opacity-100"
          aria-label={t.fullScreen}
          title={t.fullScreen}
        >
          <Maximize2 className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
