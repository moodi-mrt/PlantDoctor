"""Weather forecast (Open-Meteo, free, no API key) and weather-driven disease-risk warnings.

Risk rules live in the knowledge base (`risk:` on each disease): a temperature band plus a
minimum (or maximum) relative humidity, and the number of forecast hours in the next 72 h that
must meet both. These are simple infection-period heuristics in the spirit of published
disease-forecasting models; they flag *elevated risk*, not certainty.
"""
import json
import urllib.parse
import urllib.request

from ..config import WEATHER_TTL_S
from ..knowledge import kb
from .cache import cached

GEO = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
UA = {"User-Agent": "PlantDoctor/3 (open-source plant health app)"}
SOURCE = "Open-Meteo (open-meteo.com) — national weather service models, CC BY 4.0"


def _get(url: str, params: dict) -> dict:
    q = url + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(q, headers=UA), timeout=20) as r:
        return json.loads(r.read())


def geocode(name: str) -> dict:
    name = name.strip()[:80]
    if not name:
        raise ValueError("empty location")

    def fetch():
        d = _get(GEO, {"name": name, "count": 5, "language": "en", "format": "json"})
        res = d.get("results") or []
        # Prefer Pakistani matches for ambiguous names (e.g. "Hyderabad").
        res.sort(key=lambda r: r.get("country_code") != "PK")
        if not res:
            raise LookupError(f"no place called {name!r}")
        r = res[0]
        return {"name": r["name"], "admin1": r.get("admin1"), "country": r.get("country"),
                "lat": r["latitude"], "lon": r["longitude"], "timezone": r.get("timezone", "auto")}
    return cached(f"geo:{name.lower()}", SOURCE, 30 * 24 * 3600, fetch)["data"]


def forecast(lat: float, lon: float) -> dict:
    lat, lon = round(float(lat), 2), round(float(lon), 2)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("invalid coordinates")

    def fetch():
        return _get(FORECAST, {
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 7,
            "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code",
            "hourly": "temperature_2m,relative_humidity_2m,precipitation,dew_point_2m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,"
                     "relative_humidity_2m_mean,et0_fao_evapotranspiration,weather_code",
        })
    return cached(f"wx:{lat},{lon}", SOURCE, WEATHER_TTL_S, fetch)


def disease_risks(hourly: dict, crop_keys: list[str] | None = None, hours: int = 72) -> list:
    """Evaluate every KB risk rule for the given crops against the next `hours` of forecast.
    Rules with `months` only apply in those months (crop stage present in Pakistan's calendar)."""
    times = hourly.get("time", [])
    month = int(times[0][5:7]) if times else None
    T = hourly.get("temperature_2m", [])[:hours]
    RH = hourly.get("relative_humidity_2m", [])[:hours]
    out = []
    for label in kb.disease_keys():
        crop = kb.plant_key_for_label(label)
        if crop_keys and crop not in crop_keys:
            continue
        e = kb.entry(label)
        rule = e.get("risk")
        if not rule:
            continue
        if month and rule.get("months") and month not in rule["months"]:
            continue
        tmin, tmax = rule["t"]
        n = 0
        for t, rh in zip(T, RH):
            if t is None or rh is None:
                continue
            ok_t = tmin <= t <= tmax
            ok_rh = rh >= rule["rh"] if "rh" in rule else rh <= rule.get("rh_max", 100)
            n += ok_t and ok_rh
        need = rule.get("hours", 10)
        if n >= need:
            level = "High" if n >= 2 * need else "Elevated"
            out.append({"label": label, "crop_key": crop, "crop": e["crop"], "disease": e["name"],
                        "kind": e["kind"], "level": level, "favourable_hours": n, "needed_hours": need,
                        "window_hours": hours, "conditions": e["conditions"],
                        "advice": (e["treatment"]["preventive"] or e["treatment"]["immediate"])[:2]})
    out.sort(key=lambda r: (r["level"] != "High", -r["favourable_hours"] / r["needed_hours"]))
    return out


def irrigation_hint(daily: dict) -> str | None:
    """Short, non-prescriptive note from forecast rain and reference evapotranspiration."""
    rain = sum(x or 0 for x in daily.get("precipitation_sum", [])[:3])
    et0 = sum(x or 0 for x in daily.get("et0_fao_evapotranspiration", [])[:3])
    if not et0:
        return None
    if rain >= et0:
        return f"About {rain:.0f} mm of rain is forecast over 3 days, roughly matching crop water use (ET₀ ≈ {et0:.0f} mm) — you can probably delay irrigation; check soil moisture first."
    return f"Forecast rain ({rain:.0f} mm) is below expected crop water use (ET₀ ≈ {et0:.0f} mm over 3 days) — plan irrigation, preferably early morning, and avoid wetting leaves."
