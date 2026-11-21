"""Neon ids for the loaded catalog and especialidad_observation writes."""

from __future__ import annotations

from dataclasses import dataclass

import provenance
from especialidad_normalize import Match


@dataclass
class CatalogIds:
    especialidad: dict[str, str]
    procedimiento: dict[str, str]
    term: dict[str, str]


def load_ids(cur) -> CatalogIds:
    cur.execute("SELECT code, id::text AS id FROM avila.especialidad")
    esp = {row["code"]: row["id"] for row in cur.fetchall()}
    cur.execute("SELECT code, id::text AS id FROM avila.procedimiento")
    proc = {row["code"]: row["id"] for row in cur.fetchall()}
    cur.execute("SELECT term_folded, id::text AS id FROM avila.especialidad_term")
    term = {row["term_folded"]: row["id"] for row in cur.fetchall()}
    if not esp or not term:
        raise SystemExit("especialidad catalog is empty; run especialidad_catalog.py load --apply")
    return CatalogIds(esp, proc, term)


def observation_rows(matches: list[Match], source_ref: str, ids: CatalogIds) -> list[tuple]:
    run_id = provenance.current_run_id()
    rows = []
    seen: set[tuple[str, str]] = set()
    for match in matches:
        key = (match.context, match.l1)
        if key in seen:
            continue
        seen.add(key)
        term_id = ids.term.get(match.term.term) if match.term else None
        rows.append(
            (match.raw[:80], match.l1[:80], match.context, source_ref, match.method, match.distance, term_id, run_id)
        )
        provenance.counters[f"obs:{match.method}"] += 1
    return rows


def observation_rows_from_dicts(terms: list[dict], source_ref: str, ids: CatalogIds) -> list[tuple]:
    """Same rows as observation_rows, from the JSON form clinical_extract writes."""
    run_id = provenance.current_run_id()
    rows = []
    seen: set[tuple[str, str]] = set()
    for term in terms:
        key = (term["context"], term["l1"])
        if key in seen or not term["l1"]:
            continue
        seen.add(key)
        term_id = ids.term.get(term["term"]) if term.get("term") else None
        rows.append(
            (
                term["raw"][:80],
                term["l1"][:80],
                term["context"],
                source_ref,
                term["method"],
                term.get("distance"),
                term_id,
                run_id,
            )
        )
        provenance.counters[f"obs:{term['method']}"] += 1
    return rows


def write_observations(cur, rows: list[tuple]) -> None:
    if not rows:
        return
    cur.executemany(
        """
        INSERT INTO avila.especialidad_observation (
          raw_term, l1_term, context, source_ref, match_method, distance, term_id, run_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s::uuid, %s::uuid)
        ON CONFLICT (source_ref, context, l1_term) DO UPDATE SET
          raw_term = EXCLUDED.raw_term,
          match_method = EXCLUDED.match_method,
          distance = EXCLUDED.distance,
          term_id = EXCLUDED.term_id,
          run_id = EXCLUDED.run_id
        """,
        rows,
    )
