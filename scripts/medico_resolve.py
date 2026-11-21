#!/usr/bin/env python3
"""Decide médicos, especialidades, and patient links from clinical-truth.jsonl. No Neon.

  PYTHONPATH=scripts .venv/bin/python scripts/medico_resolve.py

Reads output/runs/clinical-truth.jsonl (clinical_extract.py) and writes
output/runs/clinical-decisions.jsonl with three record types:

- ``medico``: one per doctor cluster (MPPS first, then provisional name key).
- ``atencion``: one per report with the treating doctor, visit especialidad,
  procedure, patient link rule, status, and every doctor mention.
- ``review``: medico_mpps_conflict, medico_duplicate, atencion_patient.

Rules:

1. Mentions sharing an MPPS are one doctor. Two names under one MPPS that each
   appear twice and do not match open ``medico_mpps_conflict``.
2. A mention without MPPS joins the only MPPS cluster whose name matches it.
   Otherwise it joins or opens a provisional cluster (two name tokens minimum).
   A body-zone ``referido`` mention never opens a cluster.
3. Two MPPS clusters with matching names open ``medico_duplicate``; they are
   not merged automatically.
4. Doctor primary especialidad: most evidence, then a subespecialidad replaces
   its parent when it has at least max(2, 30%) of the parent's evidence.
5. Visit especialidad: label, doctor_title, report_title, fiscal_line, a single
   auth_line especialidad, the doctor's primary, then the procedure's owner.
6. Patient: ci_exact, name_on_invoice, sole_beneficiario, self_visit, else review.
   A person is never created from a report.

Stdout and the md report are counts only.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from clinical_parse import page_procedure, referred_specialty, visit_specialty  # noqa: E402
from clinical_parse import _best_from_dicts as best_from_terms  # noqa: E402
from especialidad_normalize import default_catalog, osa_distance  # noqa: E402
from invoice_rules import fold  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
IN_JSONL = ROOT / "output" / "runs" / "clinical-truth.jsonl"
OUT_JSONL = ROOT / "output" / "runs" / "clinical-decisions.jsonl"
OUT_MD = ROOT / "output" / "runs" / "clinical-decisions.md"

RULE_CONFIDENCE = {
    "label_tratante": 0.95,
    "label_solicitante": 0.9,
    "stamp_dr": 0.95,
    "stamp_or": 0.85,
    "stamp_bare_name": 0.8,
    "stamp_license_only": 0.7,
    "dr_line": 0.6,
}
SOURCE_CONFIDENCE = {
    "label": 0.95,
    "doctor_title": 0.9,
    "report_title": 0.8,
    "fiscal_line": 0.7,
    "auth_line": 0.7,
    "medico_primary": 0.6,
    "procedure": 0.5,
}
PERSON_CONFIDENCE = {"ci_exact": 0.98, "name_on_invoice": 0.9, "sole_beneficiario": 0.75, "self_visit": 0.7}
ZONE_RANK = {"footer": 0, "header": 1, "body": 2}
# A lab or imaging report with no other clue belongs to the service that ran it.
KIND_ESPECIALIDAD = {"laboratorio": "laboratorio_clinico", "imagen": "radiologia"}
MIN_NAME_TOKENS = 2


def name_tokens(name_folded: str | None) -> tuple[str, ...]:
    return tuple(t for t in (name_folded or "").split() if len(t) > 2)


def _token_hit(token: str, others: tuple[str, ...]) -> bool:
    if token in others:
        return True
    if len(token) < 5:
        return False
    return any(len(o) >= 5 and osa_distance(token, o, 1) <= 1 for o in others)


def name_match(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """Every token of the shorter name appears in the longer one (one OCR edit allowed)."""
    if len(a) < MIN_NAME_TOKENS or len(b) < MIN_NAME_TOKENS:
        return False
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return all(_token_hit(t, long_) for t in short)


def mpps_hash(mpps: str) -> str:
    return hashlib.sha256(mpps.encode("ascii")).hexdigest()[:24]


def _digits(raw: str | None) -> str:
    return re.sub(r"\D", "", raw or "")


@dataclass
class Cluster:
    key: str
    mpps: str | None = None
    names: Counter = field(default_factory=Counter)
    display: dict = field(default_factory=dict)
    titles: Counter = field(default_factory=Counter)
    degrees: Counter = field(default_factory=Counter)
    universities: Counter = field(default_factory=Counter)
    colegios: Counter = field(default_factory=Counter)
    rifs: Counter = field(default_factory=Counter)
    title_especialidades: Counter = field(default_factory=Counter)
    label_especialidades: Counter = field(default_factory=Counter)
    mentions: int = 0

    @property
    def name_folded(self) -> str | None:
        if not self.names:
            return None
        return max(self.names.items(), key=lambda kv: (kv[1], len(kv[0])))[0]

    @property
    def tokens(self) -> tuple[str, ...]:
        return name_tokens(self.name_folded)

    def strong_variants(self) -> list[tuple[str, ...]]:
        out = [self.tokens]
        out.extend(name_tokens(n) for n, c in self.names.items() if c >= 2 and n != self.name_folded)
        return [t for t in out if len(t) >= MIN_NAME_TOKENS]

    def add(self, doctor: dict) -> None:
        self.mentions += 1
        if doctor.get("name_folded"):
            self.names[doctor["name_folded"]] += 1
            self.display.setdefault(doctor["name_folded"], doctor.get("name"))
        for counter, key in (
            (self.titles, "title"),
            (self.degrees, "degree"),
            (self.universities, "degree_university"),
            (self.colegios, "colegio"),
            (self.rifs, "rif"),
        ):
            if doctor.get(key):
                counter[doctor[key]] += 1
        if doctor.get("especialidad") and doctor.get("role") in ("firmante", "tratante", "solicitante"):
            self.title_especialidades[doctor["especialidad"]] += 1


def _top(counter: Counter) -> str | None:
    return counter.most_common(1)[0][0] if counter else None


def primary_especialidad(counts: Counter) -> str | None:
    if not counts:
        return None
    catalog = default_catalog()
    best, best_count = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    floor = max(2, 0.3 * best_count)
    children = [
        (code, n) for code, n in counts.items() if code != best and catalog.is_descendant(code, best) and n >= floor
    ]
    if children:
        return max(children, key=lambda kv: (kv[1], kv[0]))[0]
    return best


class DoctorIndex:
    """MPPS clusters, then provisional clusters, with a token index for matching."""

    def __init__(self) -> None:
        self.clusters: dict[str, Cluster] = {}
        self._by_token: dict[str, set[str]] = defaultdict(set)

    def _index(self, cluster: Cluster) -> None:
        for variant in cluster.strong_variants():
            for token in variant:
                self._by_token[token].add(cluster.key)

    def candidates(self, tokens: tuple[str, ...], mpps_only: bool) -> list[str]:
        keys: set[str] = set()
        for token in tokens:
            keys |= self._by_token.get(token, set())
        out = []
        for key in sorted(keys):
            cluster = self.clusters[key]
            if mpps_only and not cluster.mpps:
                continue
            if any(name_match(tokens, v) for v in cluster.strong_variants()):
                out.append(key)
        return out

    def build(self, mentions: list[dict]) -> dict[int, str | None]:
        """Assign each mention (by position) to a cluster key, or None."""
        assigned: dict[int, str | None] = {}
        for i, doctor in enumerate(mentions):
            if doctor.get("mpps"):
                key = f"mpps:{doctor['mpps']}"
                cluster = self.clusters.setdefault(key, Cluster(key=key, mpps=doctor["mpps"]))
                cluster.add(doctor)
                assigned[i] = key
        for cluster in list(self.clusters.values()):
            self._index(cluster)

        pending = [i for i, d in enumerate(mentions) if not d.get("mpps")]
        by_name: dict[str, list[int]] = defaultdict(list)
        for i in pending:
            by_name[mentions[i].get("name_folded") or ""].append(i)
        for name in sorted(by_name, key=lambda n: (-len(by_name[n]), n)):
            idxs = by_name[name]
            tokens = name_tokens(name)
            if len(tokens) < MIN_NAME_TOKENS:
                for i in idxs:
                    assigned[i] = None
                continue
            hits = self.candidates(tokens, mpps_only=True)
            if len(hits) == 1:
                key = hits[0]
            else:
                provisional = [k for k in self.candidates(tokens, mpps_only=False) if not self.clusters[k].mpps]
                if provisional:
                    key = provisional[0]
                elif all(mentions[i].get("role") == "referido" for i in idxs):
                    for i in idxs:
                        assigned[i] = None
                    continue
                else:
                    key = f"name:{' '.join(tokens)}"
                    self.clusters[key] = Cluster(key=key)
            cluster = self.clusters[key]
            for i in idxs:
                cluster.add(mentions[i])
                assigned[i] = key
            self._index(cluster)
        return assigned

    def mpps_conflicts(self) -> list[dict]:
        out = []
        for cluster in self.clusters.values():
            if not cluster.mpps:
                continue
            main = cluster.tokens
            others = [
                (n, c)
                for n, c in cluster.names.items()
                if c >= 2 and n != cluster.name_folded and len(name_tokens(n)) >= MIN_NAME_TOKENS
            ]
            clash = [(n, c) for n, c in others if not name_match(main, name_tokens(n))]
            if len(main) >= MIN_NAME_TOKENS and clash:
                out.append(
                    {
                        "kind": "medico_mpps_conflict",
                        "dedupe_key": f"medico_mpps_conflict:{cluster.mpps}",
                        "medico_key": cluster.key,
                        "other_medico_key": None,
                        "primary_document_id": None,
                        "score": round(clash[0][1] / max(1, cluster.mentions), 3),
                        "evidence": {
                            "mentions": cluster.mentions,
                            "names": [{"name": n, "count": c} for n, c in [(cluster.name_folded, cluster.names[cluster.name_folded])] + clash],
                        },
                    }
                )
        return out

    def duplicates(self) -> list[dict]:
        out = []
        seen: set[tuple[str, str]] = set()
        for cluster in self.clusters.values():
            if len(cluster.tokens) < MIN_NAME_TOKENS:
                continue
            for other_key in self.candidates(cluster.tokens, mpps_only=False):
                if other_key == cluster.key:
                    continue
                other = self.clusters[other_key]
                pair = tuple(sorted((cluster.key, other_key)))
                if pair in seen:
                    continue
                seen.add(pair)
                if cluster.mpps and other.mpps:
                    out.append(
                        {
                            "kind": "medico_duplicate",
                            "dedupe_key": f"medico_duplicate:{pair[0]}|{pair[1]}",
                            "medico_key": pair[0],
                            "other_medico_key": pair[1],
                            "primary_document_id": None,
                            "score": 0.8 if cluster.tokens == other.tokens else 0.6,
                            "evidence": {
                                "names": [self.clusters[pair[0]].name_folded, self.clusters[pair[1]].name_folded],
                                "mentions": [self.clusters[pair[0]].mentions, self.clusters[pair[1]].mentions],
                            },
                        }
                    )
        return out

    def medico_record(self, cluster: Cluster) -> dict:
        especialidades = []
        primary = primary_especialidad(cluster.title_especialidades + cluster.label_especialidades)
        for code in sorted(set(cluster.title_especialidades) | set(cluster.label_especialidades)):
            source = "ocr_label" if cluster.label_especialidades[code] >= cluster.title_especialidades[code] else "ocr_title"
            especialidades.append(
                {
                    "code": code,
                    "source": source,
                    "evidence_count": cluster.title_especialidades[code] + cluster.label_especialidades[code],
                    "is_primary": code == primary,
                }
            )
        name_folded = cluster.name_folded
        full_name = cluster.display.get(name_folded) if name_folded else None
        return {
            "type": "medico",
            "key": cluster.key,
            "mpps": cluster.mpps,
            "provisional_key": None if cluster.mpps else cluster.key,
            "title": _top(cluster.titles),
            "full_name": full_name,
            "name_folded": name_folded,
            "degree": _top(cluster.degrees),
            "degree_university": _top(cluster.universities),
            "colegio_number": _top(cluster.colegios),
            "rif": _top(cluster.rifs),
            "mentions": cluster.mentions,
            "primary_especialidad": primary,
            "especialidades": especialidades,
        }


def _person_tokens(name: str | None) -> set[str]:
    return {t for t in fold(name or "").split() if len(t) > 2}


def person_name_match(page: set[str], person: set[str]) -> bool:
    if len(page) < 2 or len(person) < 2:
        return False
    other = tuple(person)
    shared = sum(1 for t in page if _token_hit(t, other))
    return shared >= 2 and shared >= 0.66 * min(len(page), len(person))


class PersonIndex:
    """Every invoice person seen in the extract, to point a reviewer at a likely invoice mix-up."""

    def __init__(self, reports: list[dict]) -> None:
        self.tokens: dict[str, set[str]] = {}
        self.ci: dict[str, set[str]] = defaultdict(set)
        self._by_token: dict[str, set[str]] = defaultdict(set)
        for report in reports:
            for person in report.get("invoice_persons") or []:
                pid = person["person_id"]
                if pid in self.tokens:
                    continue
                self.tokens[pid] = _person_tokens(person.get("full_name"))
                for token in self.tokens[pid]:
                    self._by_token[token].add(pid)
                digits = _digits(person.get("identity_number"))
                if digits:
                    self.ci[digits].add(pid)

    def elsewhere(self, report: dict) -> list[str]:
        patient = report.get("patient") or {}
        on_invoice = {p["person_id"] for p in report.get("invoice_persons") or []}
        ci = _digits(patient.get("ci"))
        if ci and self.ci.get(ci):
            return sorted(self.ci[ci] - on_invoice)
        tokens = _person_tokens(patient.get("name"))
        pool: set[str] = set()
        for token in tokens:
            pool |= self._by_token.get(token, set())
        return sorted(pid for pid in pool - on_invoice if person_name_match(tokens, self.tokens[pid]))[:5]


def link_patient(report: dict) -> tuple[str | None, str | None, list[str]]:
    """(person_id, rule, candidate person ids) for one report."""
    persons = report.get("invoice_persons") or []
    patient = report.get("patient") or {}
    ci = _digits(patient.get("ci"))
    if ci:
        hits = [p for p in persons if _digits(p.get("identity_number")) == ci]
        if len({p["person_id"] for p in hits}) == 1:
            return hits[0]["person_id"], "ci_exact", []
    tokens = _person_tokens(patient.get("name"))
    if len(tokens) >= 2:
        hits = [p for p in persons if person_name_match(tokens, _person_tokens(p.get("full_name")))]
        ids = sorted({p["person_id"] for p in hits})
        if len(ids) == 1:
            return ids[0], "name_on_invoice", []
        if len(ids) > 1:
            return None, "review", ids
    if ci or len(tokens) >= 2:
        return None, "review", sorted({p["person_id"] for p in persons})
    beneficiarios = sorted({p["person_id"] for p in persons if p["role"] == "beneficiario"})
    titulares = sorted({p["person_id"] for p in persons if p["role"] == "titular"})
    if len(beneficiarios) == 1:
        return beneficiarios[0], "sole_beneficiario", []
    if not beneficiarios and len(titulares) == 1:
        return titulares[0], "self_visit", []
    if persons:
        return None, "review", sorted({p["person_id"] for p in persons})
    return None, None, []


def treating_index(doctors: list[dict], assigned: list[str | None]) -> int | None:
    def rank(i: int) -> tuple:
        d = doctors[i]
        return (
            0 if d["role"] == "tratante" else 1,
            0 if d.get("mpps") else 1,
            ZONE_RANK.get(d["zone"], 3),
            -RULE_CONFIDENCE.get(d["rule_id"], 0.5),
            i,
        )

    signers = [i for i, d in enumerate(doctors) if assigned[i] and d["role"] in ("tratante", "firmante")]
    if signers:
        return min(signers, key=rank)
    requesters = [i for i, d in enumerate(doctors) if assigned[i] and d["role"] == "solicitante"]
    return min(requesters, key=rank) if requesters else None


def visit_especialidad(report: dict, medico_primary: str | None, procedimiento: str | None) -> tuple[str | None, str | None]:
    code, source = visit_specialty(report.get("terms") or [])
    if code:
        return code, source
    fiscal = best_from_terms(report.get("fiscal_terms") or [])
    if fiscal:
        return fiscal, "fiscal_line"
    auth = report.get("auth_especialidades") or []
    if len(auth) == 1:
        return auth[0], "auth_line"
    if medico_primary:
        return medico_primary, "medico_primary"
    if procedimiento:
        owner = default_catalog().procedimientos.get(procedimiento, {}).get("especialidad_code")
        if owner:
            return owner, "procedure"
    if report.get("report_kind") in KIND_ESPECIALIDAD:
        return KIND_ESPECIALIDAD[report["report_kind"]], "procedure"
    return None, None


def report_procedure(report: dict) -> str | None:
    found = page_procedure(report.get("terms") or [])
    if found:
        return found
    fiscal = {t["procedimiento"] for t in report.get("fiscal_terms") or [] if t.get("procedimiento")}
    return fiscal.pop() if len(fiscal) == 1 else None


def link_status(duplicate: bool, person_rule: str | None, has_person: bool, has_medico: bool, has_esp: bool) -> str:
    if duplicate:
        return "duplicate"
    if person_rule == "review":
        return "review"
    if has_person and has_medico and has_esp:
        return "complete"
    if not (has_person or has_medico or has_esp):
        return "unmatched"
    return "partial"


def resolve(reports: list[dict]) -> tuple[list[dict], Counter]:
    stats: Counter = Counter()
    mentions: list[dict] = []
    owner: list[tuple[int, int]] = []
    for r_idx, report in enumerate(reports):
        for d_idx, doctor in enumerate(report.get("doctors") or []):
            mentions.append(doctor)
            owner.append((r_idx, d_idx))
    index = DoctorIndex()
    assigned_flat = index.build(mentions)
    assigned: dict[int, list[str | None]] = defaultdict(list)
    for flat, (r_idx, _) in enumerate(owner):
        assigned[r_idx].append(assigned_flat.get(flat))

    for r_idx, report in enumerate(reports):
        doctors = report.get("doctors") or []
        t_idx = treating_index(doctors, assigned[r_idx]) if doctors else None
        code, source = visit_specialty(report.get("terms") or [])
        if t_idx is not None and source == "label" and code:
            index.clusters[assigned[r_idx][t_idx]].label_especialidades[code] += 1

    out: list[dict] = []
    for cluster in sorted(index.clusters.values(), key=lambda c: c.key):
        record = index.medico_record(cluster)
        out.append(record)
        stats["medicos"] += 1
        stats["medicos_mpps" if cluster.mpps else "medicos_provisional"] += 1
        if record["primary_especialidad"]:
            stats["medicos_with_especialidad"] += 1
    primary_of = {r["key"]: r["primary_especialidad"] for r in out}

    reviews = index.mpps_conflicts() + index.duplicates()
    people = PersonIndex(reports)
    fingerprints: dict[str, str] = {}
    for r_idx, report in enumerate(reports):
        doctors = report.get("doctors") or []
        keys = assigned[r_idx]
        t_idx = treating_index(doctors, keys) if doctors else None
        medico_key = keys[t_idx] if t_idx is not None else None
        procedimiento = report_procedure(report)
        code, source = visit_especialidad(report, primary_of.get(medico_key), procedimiento)
        person_id, rule, candidates = link_patient(report)
        has_content = bool(doctors or report.get("diagnosis") or (report.get("patient") or {}).get("name"))
        duplicate_of = fingerprints.get(report["fingerprint"]) if has_content else None
        if has_content and not duplicate_of:
            fingerprints[report["fingerprint"]] = report["primary_document_id"]
        status = link_status(bool(duplicate_of), rule, bool(person_id), bool(medico_key), bool(code))
        parts = [
            RULE_CONFIDENCE.get(doctors[t_idx]["rule_id"], 0.5) if t_idx is not None else 0.0,
            SOURCE_CONFIDENCE.get(source or "", 0.0),
            PERSON_CONFIDENCE.get(rule or "", 0.0),
        ]
        mention_rows = []
        for d_idx, doctor in enumerate(doctors):
            if not keys[d_idx]:
                stats["mentions_unassigned"] += 1
                continue
            mention_rows.append(
                {
                    "document_id": doctor["document_id"],
                    "medico_key": keys[d_idx],
                    "role": doctor["role"],
                    "zone": doctor["zone"],
                    "mpps_raw_hash": mpps_hash(doctor["mpps"]) if doctor.get("mpps") else None,
                    "name_folded": doctor.get("name_folded") or f"MPPS {doctor.get('mpps')}",
                    "confidence": RULE_CONFIDENCE.get(doctor["rule_id"], 0.5) if doctor["role"] != "referido" else 0.5,
                    "rule_id": doctor["rule_id"],
                }
            )
        out.append(
            {
                "type": "atencion",
                "primary_document_id": report["primary_document_id"],
                "document_ids": report["document_ids"],
                "invoice_id": report.get("invoice_id"),
                "person_id": person_id,
                "person_link_rule": rule,
                "medico_key": medico_key,
                "especialidad": code,
                "especialidad_source": source,
                "procedimiento": procedimiento,
                "referred_especialidad": referred_specialty(report.get("terms") or []),
                "encounter_date": report.get("encounter_date"),
                "diagnosis_text": report.get("diagnosis"),
                "report_kind": report["report_kind"],
                "link_status": status,
                "duplicate_of_document": duplicate_of,
                "confidence": round(sum(parts) / 3, 3),
                "extractor_version": report["extractor_version"],
                "text_fingerprint": report["fingerprint"],
                "source_ref": report["source_ref"],
                "mentions": mention_rows,
                "observations": [t for t in report.get("terms") or []],
            }
        )
        stats["atenciones"] += 1
        stats[f"status:{status}"] += 1
        stats[f"person_rule:{rule or 'none'}"] += 1
        stats[f"especialidad_source:{source or 'none'}"] += 1
        if procedimiento:
            stats["with_procedimiento"] += 1
        stats["mentions_assigned"] += len(mention_rows)
        if rule == "review" and not duplicate_of:
            elsewhere = people.elsewhere(report)
            if elsewhere:
                stats["review_patient_on_other_invoice"] += 1
            suggestion = next((ids[0] for ids in (candidates, elsewhere) if len(ids) == 1), None)
            if suggestion:
                stats["review_patient_with_suggestion"] += 1
            reviews.append(
                {
                    "kind": "atencion_patient",
                    "dedupe_key": f"atencion_patient:{report['primary_document_id']}",
                    "person_id": suggestion,
                    "medico_key": medico_key,
                    "other_medico_key": None,
                    "primary_document_id": report["primary_document_id"],
                    "invoice_id": report.get("invoice_id"),
                    "score": 0.5,
                    "evidence": {
                        "candidates": candidates,
                        "person_on_other_invoice": elsewhere,
                        "page_has_ci": bool((report.get("patient") or {}).get("ci")),
                        "page_has_name": bool((report.get("patient") or {}).get("name")),
                    },
                }
            )
    for review in reviews:
        out.append(dict(review, type="review"))
        stats[f"review:{review['kind']}"] += 1
    return out, stats


def render_md(stats: Counter) -> str:
    lines = ["# Clinical decisions", "", "Counts only.", "", "| Counter | Value |", "| --- | ---: |"]
    lines += [f"| {key} | {stats[key]} |" for key in sorted(stats)]
    return "\n".join(lines) + "\n"


def main() -> int:
    if not IN_JSONL.is_file():
        sys.exit(f"Missing {IN_JSONL.relative_to(ROOT)}; run clinical_extract.py first")
    reports = [json.loads(line) for line in IN_JSONL.read_text(encoding="utf-8").splitlines() if line.strip()]
    records, stats = resolve(reports)
    with OUT_JSONL.open("w", encoding="utf-8") as out:
        for record in records:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    OUT_MD.write_text(render_md(stats), encoding="utf-8")
    print({key: stats[key] for key in sorted(stats)}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
