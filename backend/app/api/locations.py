"""Location endpoints (spec §7.5): list, shifts and settings (read + PATCH).

The settings response mirrors the shape `dashboardMock.ts` calls
`LocationSettings`; the ranking weights are stored as floats and surfaced as
the screen's high/medium levels, and a PATCH maps them back.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ManagerPrincipal, current_manager, get_db
from app.db.models import Employee, Location, LocationSettings, Shift
from app.schemas.dashboard import (
    LocationOut,
    LocationSettingsOut,
    LocationSettingsPatch,
    RankingWeightOut,
    ShiftOut,
    iso_utc,
)

router = APIRouter(prefix="/api/locations", tags=["locations"])

# Stored ranking-weight keys <-> the labels the Settings screen renders.
WEIGHT_LABELS: list[tuple[str, str]] = [
    ("equity", "Coverage equity"),
    ("proximity", "Proximity (same zone)"),
    ("preference", "Extra-shift preference"),
    ("no_overtime", "No overtime first"),
]
_LABEL_TO_KEY = {label: key for key, label in WEIGHT_LABELS}
# Levels the PATCH accepts, mapped back to stored weights.
_LEVEL_WEIGHTS = {"high": 0.4, "medium": 0.2}
HIGH_LEVEL_THRESHOLD = 0.35


def _as_utc(value: datetime) -> datetime:
    """Normalize a parsed query timestamp: naive values are treated as UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _settings_out(settings: LocationSettings) -> LocationSettingsOut:
    weights = settings.ranking_weights or {}
    return LocationSettingsOut(
        agentPaused=settings.agent_paused,
        rankingWeights=[
            RankingWeightOut(
                label=label,
                level="high" if float(weights.get(key, 0.0)) >= HIGH_LEVEL_THRESHOLD else "medium",
            )
            for key, label in WEIGHT_LABELS
        ],
        waveSize=settings.wave_size,
        waveIntervalMinutes=settings.wave_interval_minutes,
        quietStart=settings.quiet_hours_start,
        quietEnd=settings.quiet_hours_end,
    )


async def _location_or_404(session: AsyncSession, location_id: str) -> Location:
    location = (
        await session.execute(select(Location).where(Location.id == location_id))
    ).scalar_one_or_none()
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


async def _settings_or_404(session: AsyncSession, location_id: str) -> LocationSettings:
    settings = (
        await session.execute(
            select(LocationSettings).where(LocationSettings.location_id == location_id)
        )
    ).scalar_one_or_none()
    if settings is None:
        raise HTTPException(status_code=404, detail="Location settings not found")
    return settings


@router.get("", response_model=list[LocationOut])
async def list_locations(
    _principal: ManagerPrincipal = Depends(current_manager),
    session: AsyncSession = Depends(get_db),
) -> list[LocationOut]:
    locations = (
        (await session.execute(select(Location).order_by(Location.name))).scalars().all()
    )
    return [
        LocationOut(id=loc.id, name=loc.name, timezone=loc.timezone) for loc in locations
    ]


@router.get("/{location_id}/shifts", response_model=list[ShiftOut])
async def list_shifts(
    location_id: str,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    _principal: ManagerPrincipal = Depends(current_manager),
    session: AsyncSession = Depends(get_db),
) -> list[ShiftOut]:
    await _location_or_404(session, location_id)
    query = (
        select(Shift, Employee.full_name)
        .outerjoin(Employee, Shift.employee_id == Employee.id)
        .where(Shift.location_id == location_id)
        .order_by(Shift.starts_at)
    )
    if from_ is not None:
        query = query.where(Shift.ends_at > _as_utc(from_))
    if to is not None:
        query = query.where(Shift.starts_at < _as_utc(to))
    rows = (await session.execute(query)).all()
    return [
        ShiftOut(
            id=shift.id,
            locationId=shift.location_id,
            role=shift.role,
            startsAt=iso_utc(shift.starts_at),
            endsAt=iso_utc(shift.ends_at),
            assigneeName=assignee,
            status=shift.status,
        )
        for shift, assignee in rows
    ]


@router.get("/{location_id}/settings", response_model=LocationSettingsOut)
async def get_location_settings(
    location_id: str,
    _principal: ManagerPrincipal = Depends(current_manager),
    session: AsyncSession = Depends(get_db),
) -> LocationSettingsOut:
    await _location_or_404(session, location_id)
    return _settings_out(await _settings_or_404(session, location_id))


@router.patch("/{location_id}/settings", response_model=LocationSettingsOut)
async def patch_location_settings(
    location_id: str,
    body: LocationSettingsPatch,
    _principal: ManagerPrincipal = Depends(current_manager),
    session: AsyncSession = Depends(get_db),
) -> LocationSettingsOut:
    await _location_or_404(session, location_id)
    settings = await _settings_or_404(session, location_id)
    if body.agentPaused is not None:
        settings.agent_paused = body.agentPaused
    if body.waveSize is not None:
        settings.wave_size = body.waveSize
    if body.waveIntervalMinutes is not None:
        settings.wave_interval_minutes = body.waveIntervalMinutes
    if body.quietStart is not None:
        settings.quiet_hours_start = body.quietStart
    if body.quietEnd is not None:
        settings.quiet_hours_end = body.quietEnd
    if body.rankingWeights is not None:
        weights = dict(settings.ranking_weights or {})
        for weight in body.rankingWeights:
            key = _LABEL_TO_KEY.get(weight.label)
            level = _LEVEL_WEIGHTS.get(weight.level)
            if key is not None and level is not None:
                weights[key] = level
        settings.ranking_weights = weights
    await session.commit()
    await session.refresh(settings)
    return _settings_out(settings)
