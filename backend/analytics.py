"""Trends for the console's analytics page: when, where and what kind of incidents happen,
and how quickly they're handled. Times are grouped in the viewer's time zone (`tz`)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import Integer, case, cast, func, select, text

from models import Incident, SessionLocal

router = APIRouter(tags=["analytics"])

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")


@router.get("/analytics")
async def analytics(days: int = Query(30, ge=1, le=365), tz: str = Query("UTC", max_length=64)):
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=422, detail=f"Unknown time zone: {tz}")

    now = datetime.utcnow()
    since = now - timedelta(days=days)
    recent = Incident.created_at >= since
    # created_at is naive UTC; this gives the same moment as local wall-clock time in `tz`
    local = func.timezone(tz, func.timezone("UTC", Incident.created_at))

    async with SessionLocal() as session:
        async def rows(*columns, where=recent, group=None, order=None):
            q = select(*columns).where(where)
            if group is not None:
                q = q.group_by(*group)
            if order is not None:
                q = q.order_by(*order)
            return (await session.execute(q)).all()

        day = func.date(local)
        by_day_raw = await rows(day, Incident.severity, func.count(), group=[day, Incident.severity], order=[day])

        dow = cast(func.extract("isodow", local), Integer)   # 1 = Monday … 7 = Sunday
        hour = cast(func.extract("hour", local), Integer)
        heat = await rows(dow, hour, func.count(), group=[dow, hour])

        zone = case((Incident.location == "NOT SPECIFIED", "No zone"), else_=Incident.location)
        by_zone = await rows(zone, func.count(), group=[zone], order=[func.count().desc()])
        by_type = await rows(Incident.event_type, func.count(), group=[Incident.event_type], order=[func.count().desc()])
        by_camera = await rows(Incident.camera_id, func.count(), group=[Incident.camera_id], order=[func.count().desc()])
        by_status = dict(await rows(Incident.status, func.count(), group=[Incident.status]))

        # which PPE item was missing, from metadata.missing_equipment (a JSON list)
        missing = (await session.execute(text("""
            SELECT item, count(*) FROM incidents,
                jsonb_array_elements_text(CASE WHEN jsonb_typeof(metadata->'missing_equipment') = 'array'
                                               THEN metadata->'missing_equipment' ELSE '[]'::jsonb END) AS item
            WHERE created_at >= :since AND event_type = 'PPE_MISSING'
            GROUP BY item ORDER BY count(*) DESC"""), {"since": since})).all()

        # time from detection to the latest status change, for handled incidents
        minutes = func.extract("epoch", Incident.status_updated_at - Incident.created_at) / 60
        handled = (Incident.status != "open") & Incident.status_updated_at.isnot(None)
        median_minutes = await session.scalar(
            select(func.percentile_cont(0.5).within_group(minutes)).where(recent, handled))

        previous_total = await session.scalar(
            select(func.count()).select_from(Incident)
            .where(Incident.created_at >= since - timedelta(days=days), Incident.created_at < since))

    by_day: dict[str, dict] = {}
    for d, severity, count in by_day_raw:
        entry = by_day.setdefault(d.isoformat(), {s: 0 for s in SEVERITIES})
        entry[severity] = entry.get(severity, 0) + count

    total = sum(c for _, c in by_type)
    return {
        "days": days,
        "tz": tz,
        "total": total,
        "previous_total": previous_total,
        "by_day": [{"day": d, **counts} for d, counts in sorted(by_day.items())],
        "heatmap": [{"weekday": w, "hour": h, "count": c} for w, h, c in heat],
        "by_zone": [{"key": k, "count": c} for k, c in by_zone],
        "by_type": [{"key": k, "count": c} for k, c in by_type],
        "by_camera": [{"key": k, "count": c} for k, c in by_camera],
        "missing_equipment": [{"key": k, "count": c} for k, c in missing],
        "by_status": {s: by_status.get(s, 0) for s in ("open", "acknowledged", "resolved")},
        "median_minutes_to_handle": round(median_minutes, 1) if median_minutes is not None else None,
    }
