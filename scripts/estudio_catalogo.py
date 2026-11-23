"""Normalize a study label into the type this clinic manages, plus a specification.

Family stays on ``estudio_tipo``. The study is the service the clinic performs
(Exámenes de laboratorio, Ecografía, Rayos X). The specification is the named
exam under that service (Hematología completa, Ecografía abdominal). A page
that only says the service has no specification. Names the clinic does not
manage (a bare "Estudio" or "Imagenología") stay out of the catalog.

  PYTHONPATH=scripts .venv/bin/python scripts/estudio_catalogo.py
  PYTHONPATH=scripts .venv/bin/python scripts/estudio_catalogo.py --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from invoice_rules import fold

UNMANAGED = {"Estudio", "Imagenología"}

SPELLING = {
    "Densitometria": "Densitometría",
    "Flujometria": "Flujometría",
    "Audiometria": "Audiometría",
    "Espirometria": "Espirometría",
    "Citologico": "Citología",
    "Trigliceridos": "Triglicéridos",
    "Factor rematoideo": "Factor reumatoideo",
    "Glucemia": "Glicemia",
    "Albumina": "Albúmina",
    "Fluorangiografía": "Fluororetinografía",
    "Asto": "ASTO",
    "Glicemia venoso": "Glicemia",
}

# Longer names first so "Orina completa" wins over "Orina".
LAB_SPECS = (
    "Hematología completa",
    "Fosfatasa alcalina",
    "Factor reumatoideo",
    "Antiestreptolisina",
    "Orina completa",
    "Perfil tiroideo",
    "Sangre oculta",
    "Citomegalovirus",
    "Perfil renal",
    "Ácido úrico",
    "Triglicéridos",
    "Hemoglobina",
    "Urocultivo",
    "Toxoplasmosis",
    "Antibiograma",
    "Bilirrubina",
    "Transaminasa",
    "Creatinina",
    "Colesterol",
    "Hemograma",
    "Serología",
    "Vitamina D",
    "Ferritina",
    "Prolactina",
    "Troponina",
    "Plaquetas",
    "Albúmina",
    "Insulina",
    "Glicemia",
    "Cortisol",
    "NT-proBNP",
    "Helicobacter",
    "Urea",
    "Orina",
    "TSH",
    "PCR",
    "PSA",
    "GGT",
    "VDRL",
    "ANA",
    "ASTO",
)

EXACT = {
    "Cateterismo": ("corazon", "Coronariografía", None),
    "Ecomamografía": ("ecografia", "Ecografía", "Ecografía mamaria"),
    "Fistulografía": ("rayos_x", "Fistulografía", None),
    "Videogastroscopia": ("endoscopia", "Endoscopia digestiva superior", "Videogastroscopia"),
    "Videoendoscopia": ("endoscopia", "Endoscopia digestiva superior", "Videogastroscopia"),
    "Videocolonoscopia": ("endoscopia", "Colonoscopia", "Videocolonoscopia"),
    "Videocistoscopia": ("endoscopia", "Cistoscopia", "Videocistoscopia"),
    "Uretrocistoscopia": ("endoscopia", "Cistoscopia", "Uretrocistoscopia"),
    "ANA de mano": ("laboratorio", "Exámenes de laboratorio", "ANA"),
    "Densitometría": ("densitometria", "Densitometría", None),
    "Mamografía": ("mamografia", "Mamografía", None),
    "Campo visual": ("oftalmologia", "Campo visual", None),
    "Fluororetinografía": ("oftalmologia", "Fluororetinografía", None),
}

# prefix, family, study, spec mode. "forced" is a fixed specification.
# False means extra words on the line are not a specification.
PREFIXES: tuple[tuple[str, str, str, bool | str], ...] = (
    ("Endoscopia digestiva superior", "endoscopia", "Endoscopia digestiva superior", False),
    ("Electrocardiograma", "corazon", "Electrocardiograma", False),
    ("Ecocardiograma", "corazon", "Ecocardiograma", False),
    ("Coronariografía", "corazon", "Coronariografía", False),
    ("Resonancia magnética", "resonancia", "Resonancia magnética", True),
    ("Angiotomografía", "tomografia", "Angiotomografía", True),
    ("Urotomografía", "tomografia", "Tomografía", "Tomografía urológica"),
    ("Electroencefalograma", "funcional", "Electroencefalograma", False),
    ("Electromiografía", "funcional", "Electromiografía", False),
    ("Tomografía", "tomografia", "Tomografía", True),
    ("Ecografía", "ecografia", "Ecografía", True),
    ("Colposcopia", "endoscopia", "Colposcopia", False),
    ("Colonoscopia", "endoscopia", "Colonoscopia", False),
    ("Cistoscopia", "endoscopia", "Cistoscopia", False),
    ("Laringoscopia", "endoscopia", "Laringoscopia", False),
    ("Flujometría", "funcional", "Flujometría", True),
    ("Audiometría", "funcional", "Audiometría", False),
    ("Espirometría", "funcional", "Espirometría", False),
    ("Citología", "anatomia_patologica", "Citología", True),
    ("Rayos X", "rayos_x", "Rayos X", True),
    ("Biopsia", "anatomia_patologica", "Biopsia", True),
    ("Holter", "corazon", "Holter", False),
    ("MAPA", "corazon", "MAPA", True),
)

# Longest phrase first. Canonical region tokens.
_PHRASES = (
    ("columna cervical dorsal lumbar", "columna"),
    ("columna lumbar dorsal", "columna lumbar"),
    ("columna cervical", "columna cervical"),
    ("columna dorsal", "columna dorsal"),
    ("columna lumbar", "columna lumbar"),
    ("de columna", "columna"),
    ("de cráneo", "cráneo"),
    ("de tórax", "tórax"),
    ("de rodilla", "rodilla"),
    ("de hombro", "hombro"),
    ("de tobillo", "tobillo"),
    ("de cadera", "cadera"),
    ("de abdomen", "abdomen"),
    ("de mano", "mano"),
    ("de pie", "pie"),
    ("transrectal", "transrectal"),
    ("transvaginal", "transvaginal"),
    ("testicular", "testicular"),
    ("obstétrica", "obstétrica"),
    ("carotídea", "carotídea"),
    ("hepática", "hepática"),
    ("vesicular", "vesicular"),
    ("urológica", "urológica"),
    ("contrastada", "contrastada"),
    ("contrastado", "contrastada"),
    ("abdominal", "abdominal"),
    ("pélvica", "pélvica"),
    ("pelvica", "pélvica"),
    ("mamaria", "mamaria"),
    ("mamario", "mamaria"),
    ("tiroidea", "tiroidea"),
    ("tiroides", "tiroidea"),
    ("cerebral", "cerebral"),
    ("cervical", "cervical"),
    ("arterial", "arterial"),
    ("venosa", "venosa"),
    ("venoso", "venosa"),
    ("columna", "columna"),
    ("cráneo", "cráneo"),
    ("tórax", "tórax"),
    ("rodilla", "rodilla"),
    ("hombro", "hombro"),
    ("tobillo", "tobillo"),
    ("cadera", "cadera"),
    ("abdomen", "abdomen"),
    ("dorsal", "dorsal"),
    ("lumbar", "lumbar"),
    ("renal", "renal"),
    ("mano", "mano"),
    ("pie", "pie"),
)

_COMBOS = {
    ("abdominal", "pélvica"): "abdominal pélvica",
    ("renal", "pélvica"): "renal pélvica",
    ("pélvica", "transrectal"): "pélvica transrectal",
    ("arterial", "venosa"): "arterial venosa",
    ("venosa", "arterial"): "arterial venosa",
}

_SPINE = {"cervical": "columna cervical", "dorsal": "columna dorsal", "lumbar": "columna lumbar"}

_ECO = {
    "abdominal",
    "pélvica",
    "abdominal pélvica",
    "mamaria",
    "renal",
    "renal pélvica",
    "tiroidea",
    "venosa",
    "arterial",
    "arterial venosa",
    "transrectal",
    "transvaginal",
    "pélvica transrectal",
    "testicular",
    "obstétrica",
    "carotídea",
    "hepática",
    "vesicular",
}
_RX = {
    "tórax",
    "columna",
    "columna lumbar",
    "columna cervical",
    "columna dorsal",
    "rodilla",
    "hombro",
    "pie",
    "mano",
    "tobillo",
    "abdomen",
    "cráneo",
    "cadera",
}
_TAC = {
    "urológica",
    "cráneo",
    "tórax",
    "abdomen",
    "cerebral",
    "hombro",
    "columna",
    "columna lumbar",
    "columna cervical",
    "columna dorsal",
    "renal",
    "pélvica",
}
_ANGIO = {"cerebral", "abdominal", "pélvica", "abdomen"}
_RM = {"cerebral", "rodilla", "columna lumbar", "columna cervical", "columna dorsal", "columna", "hombro"}

_RX_NOUNS = {"tórax", "columna", "columna lumbar", "columna cervical", "columna dorsal", "rodilla", "hombro", "pie", "mano", "tobillo", "abdomen", "cráneo", "cadera"}
_TAC_DE = {"cráneo", "tórax", "abdomen", "hombro", "columna", "columna lumbar", "columna cervical", "columna dorsal"}
_RM_DE = {"rodilla", "columna lumbar", "columna cervical", "columna dorsal", "columna", "hombro"}


def code_of(name: str) -> str:
    text = fold(name).lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _regions(text: str) -> list[str]:
    lowered = text.lower()
    occupied = [False] * len(lowered)
    hits: list[tuple[int, str]] = []
    for phrase, canonical in sorted(_PHRASES, key=lambda item: len(item[0]), reverse=True):
        start = 0
        while True:
            index = lowered.find(phrase, start)
            if index < 0:
                break
            end = index + len(phrase)
            before = lowered[index - 1] if index else " "
            after = lowered[end] if end < len(lowered) else " "
            if before.isalnum() or after.isalnum() or any(occupied[index:end]):
                start = index + 1
                continue
            for position in range(index, end):
                occupied[position] = True
            hits.append((index, canonical))
            start = end
    hits.sort()
    found: list[str] = []
    for _, canonical in hits:
        if not found or found[-1] != canonical:
            found.append(canonical)
    return found


def _spec_key(regions: list[str], *, spine: bool) -> str | None:
    if not regions:
        return None
    first, second = regions[0], regions[1] if len(regions) > 1 else None
    if second and (first, second) in _COMBOS:
        return _COMBOS[(first, second)]
    if spine and first in _SPINE:
        return _SPINE[first]
    return first


def _imaging_spec(study: str, rest: str) -> str | None:
    regions = _regions(rest)
    if study == "Ecografía":
        key = _spec_key(regions, spine=False)
        if key == "abdomen":
            key = "abdominal"
        if key == "tiroides":
            key = "tiroidea"
        if not key or key not in _ECO:
            return None
        return f"Ecografía {key}"
    if study == "Rayos X":
        key = _spec_key(regions, spine=True)
        if not key or key not in _RX:
            return None
        if key in _RX_NOUNS:
            return f"Rayos X de {key}"
        return f"Rayos X {key}"
    if study == "Tomografía":
        key = _spec_key(regions, spine=True)
        if key == "abdominal":
            key = "abdomen"
        if not key or key not in _TAC:
            return None
        if key in _TAC_DE:
            return f"Tomografía de {key}"
        if key == "urológica":
            return "Tomografía urológica"
        if key == "pélvica":
            return "Tomografía pélvica"
        if key == "cerebral":
            return "Tomografía cerebral"
        if key == "renal":
            return "Tomografía renal"
        return f"Tomografía {key}"
    if study == "Angiotomografía":
        key = _spec_key(regions, spine=False)
        if key == "abdomen":
            key = "abdominal"
        if not key or key not in _ANGIO:
            return None
        return f"Angiotomografía {key}"
    if study == "Resonancia magnética":
        key = _spec_key(regions, spine=True)
        if not key or key not in _RM:
            return None
        if key in _RM_DE:
            return f"Resonancia magnética de {key}"
        return f"Resonancia magnética {key}"
    if study == "Flujometría":
        return "Flujometría urinaria" if "urinaria" in rest.lower() else None
    if study == "MAPA":
        return "MAPA arterial" if "arterial" in rest.lower() else None
    if study == "Citología":
        key = _spec_key(regions, spine=False)
        if key == "transvaginal":
            return "Citología transvaginal"
        if key == "cervical":
            return "Citología cervical"
        return None
    if study == "Biopsia":
        key = _spec_key(regions, spine=False)
        if key == "cervical":
            return "Biopsia cervical"
        if key == "mamaria":
            return "Biopsia de mama"
        if key == "renal":
            return "Biopsia renal"
        return None
    return None


def _lab_spec(label: str) -> str | None:
    if label == "Exámenes de laboratorio":
        return None
    head = SPELLING.get(label.split(" · ")[0].strip(), label.split(" · ")[0].strip())
    for spec in LAB_SPECS:
        if head == spec or head.startswith(spec + " "):
            return spec
    return None


def _spell(label: str) -> str:
    text = label.strip()
    if text in SPELLING:
        return SPELLING[text]
    for raw, fixed in sorted(SPELLING.items(), key=lambda item: len(item[0]), reverse=True):
        if text.startswith(raw + " ") or text.startswith(raw + " ·"):
            return fixed + text[len(raw):]
    return text


def normalize_study(family: str | None, label: str) -> tuple[str, str, str | None] | None:
    """Return ``(family, study, specification or None)``.

    ``None`` means the label is not a study type this clinic manages.
    """
    text = _spell(label)
    if text in UNMANAGED:
        return None
    if text in EXACT:
        return EXACT[text]
    for prefix, kind, study, mode in PREFIXES:
        if text == prefix or text.startswith(prefix + " "):
            if mode is False:
                return (kind, study, None)
            if isinstance(mode, str):
                return (kind, study, mode)
            return (kind, study, _imaging_spec(study, text[len(prefix) :].strip()))
    if text == "Exámenes de laboratorio" or family == "laboratorio" or text in {"ANA"}:
        return ("laboratorio", "Exámenes de laboratorio", _lab_spec(text))
    return None


def _cell(row, key: str, index: int):
    if isinstance(row, dict):
        return row[key]
    return row[index]


def assign_catalog(cur) -> dict[str, int]:
    """Rebuild the clinic catalog from current estudio labels and link each row."""
    cur.execute(
        """
        SELECT id::text AS id, coalesce(estudio_tipo_code, '') AS family, label
        FROM avila.estudio
        """
    )
    source = cur.fetchall()
    studies: dict[str, tuple[str, str, str]] = {}
    specs: dict[str, tuple[str, str, str, str]] = {}
    links: list[tuple[str, str | None]] = []
    for row in source:
        estudio_id = _cell(row, "id", 0)
        family = _cell(row, "family", 1) or None
        label = _cell(row, "label", 2)
        normalized = normalize_study(family, label)
        if not normalized:
            links.append((estudio_id, None))
            continue
        kind, study, spec = normalized
        parent = code_of(study)
        studies[parent] = (parent, study, kind)
        code = parent
        if spec:
            code = code_of(spec)
            specs[code] = (code, spec, kind, parent)
        links.append((estudio_id, code))

    cur.execute("UPDATE avila.estudio SET catalogo_id = NULL")
    cur.execute("DELETE FROM avila.estudio_catalogo WHERE level = 2")
    cur.execute("DELETE FROM avila.estudio_catalogo WHERE level = 1")
    if studies:
        cur.executemany(
            """
            INSERT INTO avila.estudio_catalogo (code, name_es, estudio_tipo_code, level, sort_order)
            VALUES (%s, %s, %s, 1, 0)
            """,
            list(studies.values()),
        )
    if specs:
        cur.executemany(
            """
            INSERT INTO avila.estudio_catalogo (code, name_es, estudio_tipo_code, parent_id, level, sort_order)
            SELECT %s, %s, %s, p.id, 2, 0
            FROM avila.estudio_catalogo p
            WHERE p.code = %s AND p.level = 1
            """,
            [(code, name, kind, parent) for code, name, kind, parent in specs.values()],
        )
    paired = [(estudio_id, code) for estudio_id, code in links if code]
    if paired:
        ids, codes = zip(*paired)
        cur.execute(
            """
            UPDATE avila.estudio AS e
            SET catalogo_id = c.id,
                estudio_tipo_code = coalesce(e.estudio_tipo_code, c.estudio_tipo_code)
            FROM unnest(%s::uuid[], %s::text[]) AS m(estudio_id, code)
            JOIN avila.estudio_catalogo c ON c.code = m.code
            WHERE e.id = m.estudio_id
            """,
            (list(ids), list(codes)),
        )
    return {
        "catalogo_estudios": len(studies),
        "catalogo_especificaciones": len(specs),
        "catalogo_enlazados": len(paired),
        "catalogo_sin_tipo": len(links) - len(paired),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from env_load import load_env
    import psycopg
    from psycopg.rows import dict_row

    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL_UNPOOLED missing from .env")
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        counts = assign_catalog(cur)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    print("apply" if args.apply else "dry-run", counts, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
