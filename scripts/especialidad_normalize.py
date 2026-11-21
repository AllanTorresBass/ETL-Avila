"""One normalizer for every especialidad string (OCR, fiscal lines, workbooks).

Levels:
- L0 raw term plus the context it was read from (label, doctor_title, ...).
- L1 cleaned tokens: folded, punctuation and digits dropped, university
  suffixes removed, -LOGA / CIRUJANA / MEDICA folded to the masculine form.
- L2 lexical match, first rule wins: exact, phrase, glued prefix split,
  suffix_fragment, guarded fuzzy. Anything else is ``none``.
- L3 kind from the catalog: discipline / practitioner / adjective resolve to an
  especialidad; procedure to a procedimiento; role, degree, and stop never make
  a doctor's specialty.
- L4 hierarchy (area > especialidad > subespecialidad) lives in the catalog.

The catalog is the committed CSVs under scripts/data/. No database access.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from invoice_rules import fold

DATA_DIR = Path(__file__).resolve().parent / "data"

CONTEXTS = (
    "label",
    "doctor_title",
    "report_title",
    "referral",
    "fiscal_line",
    "workbook_servicio",
    "auth_line",
    "directory",
)
SPECIALTY_KINDS = ("discipline", "practitioner", "adjective")
# "CARDIOLOGICO" names a specialty only in a title or a service line
# ("INFORME CARDIOLOGICO", "CONSULTA CARDIOLOGICA"); elsewhere it is exam prose.
ADJECTIVE_CONTEXTS = frozenset({"report_title", "fiscal_line", "auth_line", "workbook_servicio"})

UNIVERSITIES = frozenset(
    {"LUZ", "ULA", "UNEFM", "UNERG", "UCV", "UCLA", "UDO", "USM", "UC", "UNELLEZ", "UNERMB", "UNET", "UNESR", "UCAB"}
)
GLUE_PREFIXES = ("ESPECIALIDAD", "ESPECIALISTA", "CONSULTA", "INFORME", "MEDICO", "DRA", "DR")
# Shorter tokens are usually cut-off fragments ("ROLOGO" is UROLOGO or NEUROLOGO).
MIN_FUZZY = 7
# Tokens shaped like a specialty, procedure, or practitioner word. Only these
# are tried fuzzily and only these become backlog entries when unmatched.
SPECIALTY_SHAPE = re.compile(
    r"(LOGIA|LOGO|LOGICO|IATRIA|IATRA|ISTA|PEDIA|SCOPIA|GRAFIA|GRAMA|TERAPIA|"
    r"CIRUGIA|CIRUJANO|OBSTETRA|OBSTETRICIA)$"
)
# Connector words fixed before phrase matching so "MEDIGO CIRUJANO" stays a degree.
_CONNECTORS = ("MEDICO",)


@dataclass(frozen=True)
class Term:
    term: str
    kind: str
    target: str | None
    especialidad: str | None
    procedimiento: str | None
    degree: str | None


@dataclass
class Match:
    raw: str
    l1: str
    context: str
    method: str
    distance: int | None = None
    term: Term | None = None
    university: str | None = None

    @property
    def kind(self) -> str | None:
        return self.term.kind if self.term else None

    @property
    def especialidad(self) -> str | None:
        return self.term.especialidad if self.term else None

    @property
    def procedimiento(self) -> str | None:
        return self.term.procedimiento if self.term else None

    @property
    def degree(self) -> str | None:
        return self.term.degree if self.term else None

    @property
    def is_specialty(self) -> bool:
        """True when this match may name the especialidad of a doctor or visit."""
        if not self.term or self.term.kind not in SPECIALTY_KINDS:
            return False
        return self.term.kind != "adjective" or self.context in ADJECTIVE_CONTEXTS


@dataclass
class Catalog:
    areas: dict[str, dict] = field(default_factory=dict)
    especialidades: dict[str, dict] = field(default_factory=dict)
    procedimientos: dict[str, dict] = field(default_factory=dict)
    single: dict[str, Term] = field(default_factory=dict)
    phrases: dict[tuple[str, ...], Term] = field(default_factory=dict)
    max_phrase: int = 1

    def parent_of(self, code: str | None) -> str | None:
        row = self.especialidades.get(code or "")
        return (row or {}).get("parent_code") or None

    def is_descendant(self, child: str | None, parent: str | None) -> bool:
        return bool(child and parent and self.parent_of(child) == parent)

    def concept(self, term: Term) -> tuple[str, str | None]:
        return (term.kind, term.target)


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]


def load_catalog(data_dir: Path = DATA_DIR) -> Catalog:
    catalog = Catalog()
    for row in _read_csv(data_dir / "especialidad_areas.csv"):
        catalog.areas[row["code"]] = row
    for row in _read_csv(data_dir / "especialidades.csv"):
        catalog.especialidades[row["code"]] = row
    for row in _read_csv(data_dir / "procedimientos.csv"):
        catalog.procedimientos[row["code"]] = row
    for row in _read_csv(data_dir / "especialidad_terms.csv"):
        kind = row["kind"]
        target = row["target_code"] or None
        esp = proc = degree = None
        if kind in SPECIALTY_KINDS:
            esp = target
        elif kind == "procedure":
            proc = target
        elif kind == "degree":
            degree = target
        elif kind == "role" and target:
            if target in catalog.especialidades:
                esp = target
            else:
                proc = target
        term = Term(fold(row["term_folded"]), kind, target, esp, proc, degree)
        tokens = tuple(term.term.split())
        if len(tokens) == 1:
            catalog.single[term.term] = term
        else:
            catalog.phrases[tokens] = term
            catalog.max_phrase = max(catalog.max_phrase, len(tokens))
    return catalog


@lru_cache(maxsize=1)
def default_catalog() -> Catalog:
    return load_catalog()


def osa_distance(a: str, b: str, limit: int) -> int:
    """Damerau (optimal string alignment) distance, capped at ``limit + 1``."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2: list[int] = []
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        best = cur[0]
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            value = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                value = min(value, prev2[j - 2] + 1)
            cur[j] = value
            best = min(best, value)
        if best > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[len(b)]


def _max_distance(length: int) -> int:
    if length < 9:
        return 1
    if length < 14:
        return 2
    return 3


def _gender_fold(token: str) -> str:
    if token.endswith("LOGA"):
        return token[:-1] + "O"
    if token in {"CIRUJANA", "MEDICA"}:
        return token[:-1] + "O"
    return token


def clean_tokens(raw: str) -> tuple[list[str], str | None]:
    """L1: folded tokens with universities removed (returned separately)."""
    text = re.sub(r"[^A-Z\s]", " ", fold(raw or ""))
    tokens: list[str] = []
    university = None
    for token in text.split():
        if token in UNIVERSITIES:
            university = university or token
            # "CIRUJANO ULA" is the degree even when MEDICO was not read.
            if tokens and tokens[-1] == "CIRUJANO" and (len(tokens) < 2 or tokens[-2] != "MEDICO"):
                tokens.insert(len(tokens) - 1, "MEDICO")
            continue
        token = _gender_fold(token)
        if len(token) == 6 and token not in _CONNECTORS:
            for word in _CONNECTORS:
                if osa_distance(token, word, 1) == 1 and token[0] == word[0]:
                    token = word
                    break
        tokens.append(token)
    return tokens, university


def _unique(candidates: list[Term], catalog: Catalog) -> Term | None:
    concepts = {catalog.concept(term) for term in candidates}
    return candidates[0] if len(concepts) == 1 else None


def _suffix_fragment(token: str, catalog: Catalog) -> tuple[Term, int] | None:
    if len(token) < 7:
        return None
    candidates = [term for key, term in catalog.single.items() if key != token and key.endswith(token)]
    term = _unique(candidates, catalog) if candidates else None
    if not term:
        return None
    return term, len(term.term) - len(token)


def _fuzzy(token: str, catalog: Catalog) -> tuple[Term, int] | None:
    if len(token) < MIN_FUZZY:
        return None
    limit = _max_distance(len(token))
    best = limit + 1
    found: list[Term] = []
    for key, term in catalog.single.items():
        distance = osa_distance(token, key, limit)
        if distance > limit:
            continue
        if distance < best:
            best, found = distance, [term]
        elif distance == best:
            found.append(term)
    if not found:
        return None
    term = _unique(found, catalog)
    return (term, best) if term else None


def _shaped(token: str, catalog: Catalog) -> bool:
    if SPECIALTY_SHAPE.search(token):
        return True
    head = token[:5]
    return len(token) >= 6 and any(key.startswith(head) for key in catalog.single)


def match_token(token: str, context: str, catalog: Catalog) -> Match | None:
    """L2 for one cleaned token. ``None`` means the token is not specialty-shaped."""
    if token in catalog.single:
        return Match(token, token, context, "exact", 0, catalog.single[token])
    if token.endswith("ICA") and token[:-1] + "O" in catalog.single:
        masculine = token[:-1] + "O"
        return Match(token, masculine, context, "exact", 0, catalog.single[masculine])
    for prefix in GLUE_PREFIXES:
        rest = token[len(prefix):]
        if not token.startswith(prefix) or len(rest) < 5:
            continue
        phrase = catalog.phrases.get((prefix, rest))
        if phrase:
            return Match(token, f"{prefix} {rest}", context, "exact", 0, phrase)
        inner = match_token(rest, context, catalog)
        if inner and inner.term:
            inner.raw = token
            return inner
    if not _shaped(token, catalog):
        return None
    hit = _suffix_fragment(token, catalog)
    if hit:
        return Match(token, token, context, "suffix_fragment", hit[1], hit[0])
    hit = _fuzzy(token, catalog)
    if hit:
        return Match(token, token, context, "fuzzy", hit[1], hit[0])
    if len(token) >= MIN_FUZZY and SPECIALTY_SHAPE.search(token):
        return Match(token, token, context, "none")
    return None


def normalize_text(raw: str, context: str, catalog: Catalog | None = None) -> list[Match]:
    """Every catalog hit in one line, longest phrase first, in reading order."""
    if context not in CONTEXTS:
        raise ValueError(f"unknown context {context}")
    catalog = catalog or default_catalog()
    tokens, university = clean_tokens(raw)
    out: list[Match] = []
    i = 0
    while i < len(tokens):
        hit = None
        for size in range(min(catalog.max_phrase, len(tokens) - i), 1, -1):
            key = tuple(tokens[i:i + size])
            term = catalog.phrases.get(key)
            if term:
                hit = Match(" ".join(key), " ".join(key), context, "phrase", 0, term)
                i += size
                break
        if hit is None:
            hit = match_token(tokens[i], context, catalog)
            i += 1
        if hit is None:
            continue
        if hit.term and hit.term.kind == "degree":
            hit.university = university
        if hit.term and hit.term.kind == "adjective" and context not in ADJECTIVE_CONTEXTS:
            continue
        out.append(hit)
    return out


def best_specialty(matches: list[Match]) -> Match | None:
    """The most specific specialty match: subespecialidad beats its parent."""
    specialties = [m for m in matches if m.is_specialty]
    if not specialties:
        return None
    catalog = default_catalog()
    for match in specialties:
        if any(catalog.is_descendant(match.especialidad, other.especialidad) for other in specialties):
            return match
    return specialties[0]


def first_procedure(matches: list[Match]) -> Match | None:
    for match in matches:
        if match.procedimiento and match.kind == "procedure":
            return match
    return None


def degree_of(matches: list[Match]) -> Match | None:
    for match in matches:
        if match.kind == "degree":
            return match
    return None
