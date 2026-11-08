"""Traçabilité : liste les observations sources d'un résultat (station, date, élément, valeur, flags, lot).

Chaque résultat de F1-F4 contient un champ « sources » qui se passe tel quel à cette fonction :
- F1, F2 : une station, un élément, un intervalle de dates ;
- F3 : une zone, un élément, une année et un mois (toutes les observations de la zone ce mois-là) ;
- F4 : les preuves sont déjà dans le résultat ; la trace d'une station et d'un jour donne la ligne d'origine.
"""

import calendar
from datetime import date

from weatherscope.services.common import fetch

SQL = """
SELECT o.station, o.date, o.element, o.value, o.mflag, o.qflag, o.sflag, o.obs_time, o.batch_id
FROM observations o JOIN stations s ON s.id = o.station
WHERE {where}
ORDER BY o.station, o.element, o.date
"""


def records(conn, station: str | None = None, zone: str | None = None, element: str | None = None,
            start: date | None = None, end: date | None = None,
            year: int | None = None, month: int | None = None, flagged_only: bool = False) -> dict:
    if year and month:
        start, end = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    if not (station or zone) or not (start and end):
        raise ValueError("préciser une station ou une zone, et une période")
    where = ["o.date BETWEEN %(start)s AND %(end)s"]
    if station:
        where.append("o.station = %(station)s")
    if zone:
        where.append("s.zone = %(zone)s")
    if element:
        where.append("o.element = %(element)s")
    if flagged_only:
        where.append("(o.qflag IS NOT NULL OR o.mflag IS NOT NULL)")
    params = {"station": station, "zone": zone, "element": element, "start": start, "end": end}
    rows = fetch(conn, SQL.format(where=" AND ".join(where)), params)
    for r in rows:
        r["date"] = r["date"].isoformat()
    return {"service": "trace",
            "params": {k: (v.isoformat() if isinstance(v, date) else v) for k, v in params.items()},
            "count": len(rows), "records": rows}
