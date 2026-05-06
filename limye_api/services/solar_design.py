"""Geocode → Google Solar buildingInsights → canvas-ready roof layout (auth-free flow)."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any
from urllib.parse import quote

import httpx

from limye_api.config import Settings

_SOLAR_URL = "https://solar.googleapis.com/v1/buildingInsights:findClosest"
_MAPBOX_GEOCODE = "https://api.mapbox.com/geocoding/v5/mapbox.places/{query}.json"
_CANVAS_SIZE = 4000.0
_CANVAS_MARGIN = 80.0
_CACHE_PREFIX = "design:solar:v1:"
_CACHE_TTL_SECONDS = 7 * 24 * 3600


def normalized_address_key(address: str) -> str:
    s = address.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def cache_key_for_address(address: str) -> str:
    norm = normalized_address_key(address)
    h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    return f"{_CACHE_PREFIX}{h}"


def _orientation_score(azimuth_degrees: float | None) -> float:
    """1.0 = due south (US steep-south bias); 0.0 = steep north."""
    if azimuth_degrees is None:
        return 0.0
    # Deviation from 180° (south) on 0..360 circle
    d = abs(((float(azimuth_degrees) - 180.0 + 540.0) % 360.0) - 180.0)
    return max(0.0, 1.0 - d / 180.0)


def _annual_sunshine_kwh_per_kw(stats: dict[str, Any] | None) -> float | None:
    if not stats:
        return None
    quantiles = stats.get("sunshineQuantiles") or stats.get("sunshine_quantiles")
    if not quantiles:
        return None
    try:
        return float(max(float(q) for q in quantiles))
    except (TypeError, ValueError):
        return None


def _latlng_to_plane(lat: float, lon: float, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    x = (lon - ref_lon) * math.cos(math.radians(ref_lat))
    y = lat - ref_lat
    return x, y


def _plane_to_isometric(px: float, py: float) -> tuple[float, float]:
    return (px - py, (px + py) * 0.5)


def _project_latlng(
    lat: float,
    lon: float,
    ref_lat: float,
    ref_lon: float,
) -> tuple[float, float]:
    px, py = _latlng_to_plane(lat, lon, ref_lat, ref_lon)
    return _plane_to_isometric(px, py)


def _fit_transform_points(
    points: list[tuple[float, float]],
) -> tuple[float, float, float, float, float, float]:
    """Return (min_x, max_x, min_y, max_y, scale, margin) for uniform scale into canvas."""
    if not points:
        return 0.0, 1.0, 0.0, 1.0, 1.0, _CANVAS_MARGIN
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    w = max_x - min_x
    h = max_y - min_y
    if w < 1e-12:
        w = 1e-12
    if h < 1e-12:
        h = 1e-12
    inner = _CANVAS_SIZE - 2 * _CANVAS_MARGIN
    scale = min(inner / w, inner / h)
    return min_x, max_x, min_y, max_y, scale, _CANVAS_MARGIN


def _to_canvas(
    p: tuple[float, float],
    min_x: float,
    max_y: float,
    scale: float,
    margin: float,
) -> dict[str, float]:
    x, y = p
    return {
        "x": (x - min_x) * scale + margin,
        "y": (max_y - y) * scale + margin,
    }


def _segment_footprint_latlng(seg: dict[str, Any]) -> list[tuple[float, float]]:
    """Roof outline from LatLngBox (rectangle in lat/lng); Solar API has no richer polygon."""
    box = seg.get("boundingBox") or seg.get("bounding_box")
    if not box:
        ctr = seg.get("center")
        if ctr and "latitude" in ctr and "longitude" in ctr:
            lat0 = float(ctr["latitude"])
            lon0 = float(ctr["longitude"])
            d = 2e-5
            return [
                (lat0 - d, lon0 - d),
                (lat0 - d, lon0 + d),
                (lat0 + d, lon0 + d),
                (lat0 + d, lon0 - d),
            ]
        return []
    sw = box.get("sw") or box.get("SW")
    ne = box.get("ne") or box.get("NE")
    if not sw or not ne:
        return []
    lat_s = float(sw["latitude"])
    lon_s = float(sw["longitude"])
    lat_n = float(ne["latitude"])
    lon_e = float(ne["longitude"])
    # sw, se, ne, nw
    return [
        (lat_s, lon_s),
        (lat_s, lon_e),
        (lat_n, lon_e),
        (lat_n, lon_s),
    ]


async def geocode_mapbox(address: str, settings: Settings) -> tuple[float, float]:
    token = (settings.MAPBOX_ACCESS_TOKEN or "").strip()
    if not token:
        raise RuntimeError("MAPBOX_ACCESS_TOKEN is not configured.")
    path_segment = quote(address, safe="")
    url = _MAPBOX_GEOCODE.format(query=path_segment) + f"?access_token={token}&limit=1"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url)
    if r.status_code != 200:
        raise RuntimeError(f"Mapbox geocoding failed (HTTP {r.status_code}).")
    data = r.json()
    feats = data.get("features") or []
    if not feats:
        raise ValueError("Address not found — try a fuller street address.")
    center = feats[0].get("center")
    if not center or len(center) < 2:
        raise ValueError("Address not found — geocoder returned no coordinates.")
    lon, lat = float(center[0]), float(center[1])
    return lat, lon


async def fetch_google_building_insights(lat: float, lon: float, settings: Settings) -> dict[str, Any]:
    key = (settings.GOOGLE_SOLAR_API_KEY or "").strip()
    if not key:
        raise RuntimeError("GOOGLE_SOLAR_API_KEY is not configured.")
    params = {
        "location.latitude": str(lat),
        "location.longitude": str(lon),
        "key": key,
    }
    async with httpx.AsyncClient(timeout=45.0) as client:
        r = await client.get(_SOLAR_URL, params=params)
    if r.status_code == 404:
        raise ValueError(
            "No solar building data near this location — the Solar API "
            "returned no building within range."
        )
    if r.status_code != 200:
        try:
            err = r.json().get("error", {})
            msg = err.get("message", r.text[:500])
        except Exception:  # noqa: BLE001
            msg = r.text[:500]
        raise RuntimeError(f"Google Solar API error (HTTP {r.status_code}): {msg}")
    return r.json()


def _pick_top_panel_config(configs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not configs:
        return None
    return max(
        configs,
        key=lambda c: (
            int(c.get("panelsCount") or c.get("panels_count") or 0),
            float(c.get("yearlyEnergyDcKwh") or c.get("yearly_energy_dc_kwh") or 0.0),
        ),
    )


def build_design_payload(building: dict[str, Any]) -> dict[str, Any]:
    sp = building.get("solarPotential") or building.get("solar_potential")
    if not sp:
        raise ValueError("Solar API returned no solar potential data for this building.")
    whole = sp.get("wholeRoofStats") or sp.get("whole_roof_stats")
    if not whole:
        raise ValueError("Solar API returned no whole-roof statistics.")

    roof_segments = sp.get("roofSegmentStats") or sp.get("roof_segment_stats") or []
    if not roof_segments:
        raise ValueError("Solar API returned no roof segments for this building.")

    center = building.get("center") or {}
    ref_lat = float(center.get("latitude", 0.0))
    ref_lon = float(center.get("longitude", 0.0))

    collect_points: list[tuple[float, float]] = []

    segment_out: list[dict[str, Any]] = []
    segment_polys_ll: list[list[tuple[float, float]]] = []
    for idx, seg in enumerate(roof_segments):
        pitch = seg.get("pitchDegrees") if "pitchDegrees" in seg else seg.get("pitch_degrees")
        az = seg.get("azimuthDegrees") if "azimuthDegrees" in seg else seg.get("azimuth_degrees")
        stats = seg.get("stats")
        poly_ll = _segment_footprint_latlng(seg)
        segment_polys_ll.append(poly_ll)
        for lat, lon in poly_ll:
            collect_points.append(_project_latlng(lat, lon, ref_lat, ref_lon))
        sunshine = _annual_sunshine_kwh_per_kw(stats if isinstance(stats, dict) else None)
        segment_out.append(
            {
                "id": idx,
                "azimuth": float(az) if az is not None else None,
                "pitch": float(pitch) if pitch is not None else None,
                "polygon": [],
                "orientationScore": _orientation_score(float(az) if az is not None else None),
                "annualSunshine": sunshine,
            }
        )

    panels_raw = sp.get("solarPanels") or sp.get("solar_panels") or []
    configs = sp.get("solarPanelConfigs") or sp.get("solar_panel_configs") or []
    top = _pick_top_panel_config(configs)
    if top is None:
        raise ValueError("No solar panel layout configurations are available for this roof.")

    n = int(top.get("panelsCount") or top.get("panels_count") or 0)
    if n <= 0:
        raise ValueError("The best solar configuration has no panels.")
    yearly = float(top.get("yearlyEnergyDcKwh") or top.get("yearly_energy_dc_kwh") or 0.0)

    active_slice = panels_raw[:n]
    for p in active_slice:
        c = p.get("center") or {}
        if "latitude" in c and "longitude" in c:
            collect_points.append(
                _project_latlng(float(c["latitude"]), float(c["longitude"]), ref_lat, ref_lon)
            )

    if not collect_points:
        collect_points.append(_project_latlng(ref_lat, ref_lon, ref_lat, ref_lon))

    min_x, max_x, min_y, max_y, scale, margin = _fit_transform_points(collect_points)

    for i, poly_ll in enumerate(segment_polys_ll):
        canvas_poly: list[dict[str, float]] = []
        for lat, lon in poly_ll:
            iso = _project_latlng(lat, lon, ref_lat, ref_lon)
            canvas_poly.append(_to_canvas(iso, min_x, max_y, scale, margin))
        segment_out[i]["polygon"] = canvas_poly

    active_config: list[dict[str, Any]] = []
    for i, p in enumerate(active_slice):
        c = p.get("center") or {}
        ori = p.get("orientation", p.get("Orientation"))
        if isinstance(ori, str):
            ori_str = ori.split(".")[-1]
        elif ori is not None:
            ori_str = str(ori)
        else:
            ori_str = "UNSPECIFIED"
        si = p.get("segmentIndex")
        if si is None:
            si = p.get("segment_index")
        center_d: dict[str, float] = {}
        if "latitude" in c and "longitude" in c:
            iso = _project_latlng(float(c["latitude"]), float(c["longitude"]), ref_lat, ref_lon)
            center_d = _to_canvas(iso, min_x, max_y, scale, margin)
        active_config.append(
            {
                "id": i,
                "segmentIndex": int(si) if si is not None else -1,
                "center": center_d,
                "orientation": ori_str,
            }
        )

    quantiles = whole.get("sunshineQuantiles") or whole.get("sunshine_quantiles") or []
    area = whole.get("areaMeters2")
    if area is None:
        area = whole.get("area_meters2")

    return {
        "segments": segment_out,
        "activeConfig": active_config,
        "yearlyEnergyDcKwh": yearly,
        "wholeRoofStats": {
            "area": float(area) if area is not None else None,
            "sunshineQuantiles": [float(q) for q in quantiles],
        },
    }


async def run_solar_design(
    address: str,
    settings: Settings,
    redis_client: Any | None,
) -> dict[str, Any]:
    key = cache_key_for_address(address)
    if redis_client is not None:
        try:
            cached = await redis_client.get(key)
            if cached:
                return json.loads(str(cached))
        except Exception:  # noqa: BLE001
            pass

    lat, lon = await geocode_mapbox(address, settings)
    building = await fetch_google_building_insights(lat, lon, settings)
    payload = build_design_payload(building)

    if redis_client is not None:
        try:
            await redis_client.set(key, json.dumps(payload), ex=_CACHE_TTL_SECONDS)
        except Exception:  # noqa: BLE001
            pass

    return payload


async def get_cached_solar_design(
    redis_client: Any | None,
    *,
    address: str | None = None,
    cache_key: str | None = None,
) -> dict[str, Any] | None:
    """Return cached POST /design JSON body, or None if Redis is missing or key absent."""
    if redis_client is None:
        return None
    key = (cache_key or "").strip() if cache_key else None
    if not key and address and address.strip():
        key = cache_key_for_address(address.strip())
    if not key:
        return None
    try:
        raw = await redis_client.get(key)
        if not raw:
            return None
        data = json.loads(str(raw))
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


__all__ = [
    "build_design_payload",
    "run_solar_design",
    "cache_key_for_address",
    "get_cached_solar_design",
]
