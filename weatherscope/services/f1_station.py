"""F1 — Explorer une station : recherche dans une zone, puis résumé mensuel sur un intervalle.

Le résumé donne, par élément et par mois : jours attendus, observations présentes, valides,
invalides (qflag), traces (T), présumées nulles (P), moyenne (TMAX, TMIN) ou cumul (PRCP), min, max,
et la disponibilité (valides / jours attendus). Requête sur une seule station : en distribué,
un seul worker est contacté.
"""

import calendar
from datetime import date, timedelta
from fractions import Fraction

from weatherscope.services.common import UNITS, VALID, Area, fetch, round2, unit_value

SQL_SEARCH = """
SELECT s.id, s.zone, s.name, s.lat, s.lon, s.elevation
FROM stations s WHERE {area} AND (%(name)s::text IS NULL OR s.name ILIKE '%%' || %(name)s || '%%')
ORDER BY s.id
"""

SQL_SUMMARY = f"""
SELECT o.element, extract(year FROM o.date)::int AS year, extract(month FROM o.date)::int AS month,
       count(*) AS n_obs,
       count(*) FILTER (WHERE {VALID}) AS n_valid,
       count(*) FILTER (WHERE o.qflag IS NOT NULL) AS n_flagged,
       count(*) FILTER (WHERE o.qflag IS NULL AND o.mflag = 'T') AS n_trace,
       count(*) FILTER (WHERE o.qflag IS NULL AND o.mflag = 'P') AS n_presumed,
       sum(o.value) FILTER (WHERE {VALID}) AS sum_value,
       min(o.value) FILTER (WHERE {VALID}) AS min_value,
       max(o.value) FILTER (WHERE {VALID}) AS max_value
FROM observations o
WHERE o.station = %(station)s AND o.date BETWEEN %(start)s AND %(end)s
GROUP BY 1, 2, 3
"""


def search(conn, area: Area, name: str | None = None) -> dict:
    where, params = area.sql()
    rows = fetch(conn, SQL_SEARCH.format(area=where), {**params, "name": name})
    for r in rows:
        r["lat"], r["lon"] = float(r["lat"]), float(r["lon"])
        r["elevation"] = None if r["elevation"] is None else float(r["elevation"])
    return {"service": "F1-search", "params": {**area.describe(), "name": name}, "stations": rows}


def expected_days(year: int, month: int, start: date, end: date) -> int:
    """Jours du mois compris dans [start, end]."""
    first = max(date(year, month, 1), start)
    last = min(date(year, month, calendar.monthrange(year, month)[1]), end)
    return max((last - first).days + 1, 0)


def months(start: date, end: date) -> list[tuple[int, int]]:
    out, d = [], date(start.year, start.month, 1)
    while d <= end:
        out.append((d.year, d.month))
        d = (d + timedelta(days=32)).replace(day=1)
    return out


def summary(conn, station: str, start: date, end: date) -> dict:
    params = {"station": station, "start": start, "end": end}
    meta = fetch(conn, "SELECT id, zone, name, lat, lon, elevation FROM stations WHERE id = %(station)s", params)
    if not meta:
        raise LookupError(f"station inconnue : {station}")
    got = {(r["element"], r["year"], r["month"]): r for r in fetch(conn, SQL_SUMMARY, params)}

    rows, totals = [], {}
    for element in ("TMAX", "TMIN", "PRCP"):
        tot = totals.setdefault(element, {"expected": 0, "n_obs": 0, "n_valid": 0, "n_flagged": 0,
                                          "n_trace": 0, "n_presumed": 0})
        for y, m in months(start, end):
            r = got.get((element, y, m), {})
            exp = expected_days(y, m, start, end)
            n_valid = r.get("n_valid", 0)
            s = r.get("sum_value")
            row = {
                "element": element, "year": y, "month": m, "expected": exp,
                "n_obs": r.get("n_obs", 0), "n_valid": n_valid, "n_flagged": r.get("n_flagged", 0),
                "n_trace": r.get("n_trace", 0), "n_presumed": r.get("n_presumed", 0),
                "availability": round2(Fraction(n_valid, exp)) if exp else None,
                # Moyenne pour les températures ; cumul pour la pluie (sur les jours valides seulement).
                "mean": round2(Fraction(s, n_valid * 10)) if n_valid and element != "PRCP" else None,
                "total": unit_value(s) if s is not None and element == "PRCP" else None,
                "min": unit_value(r.get("min_value")), "max": unit_value(r.get("max_value")),
                "unit": UNITS[element],
            }
            rows.append(row)
            for k in tot:
                tot[k] += exp if k == "expected" else row[k]
        tot["availability"] = round2(Fraction(tot["n_valid"], tot["expected"])) if tot["expected"] else None

    st = meta[0]
    st.update(lat=float(st["lat"]), lon=float(st["lon"]),
              elevation=None if st["elevation"] is None else float(st["elevation"]))
    return {"service": "F1", "params": {"station": station, "start": start.isoformat(), "end": end.isoformat()},
            "station": st, "totals": totals, "months": rows,
            "sources": {"station": station, "start": start.isoformat(), "end": end.isoformat()}}
