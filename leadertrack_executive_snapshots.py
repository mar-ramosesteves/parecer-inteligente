"""Montagem deterministica dos snapshots executivos LeaderTrack.

O modulo trabalha apenas com registros ja normalizados pelo backend. Respostas
individuais entram no calculo em memoria, mas nunca fazem parte do pacote salvo.
"""

from copy import deepcopy
from hashlib import sha256
import json


SNAPSHOT_SCHEMA_VERSION = "leadertrack-executivo-v2"
RECORTE_FIELDS = ("sexo", "etnia", "departamento", "cargo")
EXECUTIVE_GAP_RULE_VERSION = "microambiente-executivo-v1"
EXECUTIVE_GAP_MONITORING_PP = 10.0
EXECUTIVE_GAP_RELEVANT_PP = 20.0
EXECUTIVE_GAP_CRITICAL_PP = 35.0


def _text(value):
    return str(value or "").strip()


def _normalized(value):
    text = _text(value)
    return text if text else "Não identificado"


def _team(records):
    return [row for row in (records or []) if row.get("tipo") == "equipe"]


def _auto(records):
    return [row for row in (records or []) if row.get("tipo") == "autoavaliacao"]


def _rows(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("dados", "rows", "items"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def _number(value):
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("%", "").replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _executive_gap_band(gap_pp):
    magnitude = abs(float(gap_pp))
    if magnitude >= EXECUTIVE_GAP_CRITICAL_PP:
        return "critico"
    if magnitude >= EXECUTIVE_GAP_RELEVANT_PP:
        return "relevante"
    if magnitude >= EXECUTIVE_GAP_MONITORING_PP:
        return "monitoramento"
    return None


def build_executive_microenvironment_gap_summary(leadertrack, max_signals=12):
    """Resume gaps da equipe para a leitura executiva sem tocar a regra individual."""
    micro = (leadertrack or {}).get("microambiente") or {}
    analytic_rows = _rows(micro.get("analitico"))
    signals = []
    by_dimension = {}

    for row in analytic_rows:
        if not isinstance(row, dict):
            continue
        gap = _number(row.get("GAP"))
        band = _executive_gap_band(gap) if gap is not None else None
        if not band:
            continue
        magnitude = round(abs(gap), 1)
        dimension = _text(row.get("DIMENSAO")) or "Não identificado"
        signal = {
            "questao": row.get("QUESTAO"),
            "afirmacao": row.get("AFIRMACAO"),
            "dimensao": dimension,
            "subdimensao": row.get("SUBDIMENSAO"),
            "real": _number(row.get("PONTUACAO_REAL")),
            "ideal": _number(row.get("PONTUACAO_IDEAL")),
            "gap_pp": magnitude,
            "faixa": band,
        }
        signals.append(signal)

        dimension_summary = by_dimension.setdefault(dimension, {
            "dimensao": dimension,
            "sinais_10": 0,
            "relevantes_20": 0,
            "criticos_35": 0,
            "maior_gap_pp": 0.0,
        })
        dimension_summary["sinais_10"] += 1
        if magnitude >= EXECUTIVE_GAP_RELEVANT_PP:
            dimension_summary["relevantes_20"] += 1
        if magnitude >= EXECUTIVE_GAP_CRITICAL_PP:
            dimension_summary["criticos_35"] += 1
        dimension_summary["maior_gap_pp"] = max(
            dimension_summary["maior_gap_pp"], magnitude
        )

    band_priority = {"critico": 0, "relevante": 1, "monitoramento": 2}
    signals.sort(key=lambda item: (
        band_priority.get(item.get("faixa"), 9),
        -float(item.get("gap_pp") or 0),
        _text(item.get("dimensao")).casefold(),
        _text(item.get("questao")).casefold(),
    ))
    dimensions = sorted(
        by_dimension.values(),
        key=lambda item: (
            -item["criticos_35"],
            -item["relevantes_20"],
            -item["sinais_10"],
            -item["maior_gap_pp"],
            item["dimensao"].casefold(),
        ),
    )
    total = len(analytic_rows)
    above_10 = len(signals)
    above_20 = sum(1 for item in signals if item["gap_pp"] >= EXECUTIVE_GAP_RELEVANT_PP)
    above_35 = sum(1 for item in signals if item["gap_pp"] >= EXECUTIVE_GAP_CRITICAL_PP)
    return {
        "versao_regra": EXECUTIVE_GAP_RULE_VERSION,
        "base_calculo": "somente respostas da equipe",
        "limiares_pp": {
            "monitoramento": EXECUTIVE_GAP_MONITORING_PP,
            "relevante": EXECUTIVE_GAP_RELEVANT_PP,
            "critico": EXECUTIVE_GAP_CRITICAL_PP,
        },
        "total_afirmacoes": total,
        "quantidades": {
            "acima_10": above_10,
            "acima_20": above_20,
            "acima_35": above_35,
        },
        "percentual_acima_10": round((above_10 / total) * 100, 1) if total else 0.0,
        "por_dimensao": dimensions,
        "principais_sinais": signals[:max_signals],
    }


def group_source_rows_by_company(rows):
    grouped = {}
    for row in rows or []:
        company = _text(row.get("empresa")).lower()
        if company:
            grouped.setdefault(company, []).append(row)
    return grouped


def source_hash(archetype_rows, microenvironment_rows):
    source = {
        "arquetipos": archetype_rows or [],
        "microambiente": microenvironment_rows or [],
    }
    serialized = json.dumps(
        source,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(serialized).hexdigest()


def snapshot_matches_context(snapshot, requested_context):
    """Confirma que um pacote pertence ao contexto solicitado."""
    scope = (snapshot or {}).get("scope") or {}
    requested = requested_context or {}

    requested_holding = _text(requested.get("holding_id")).lower()
    if requested_holding:
        return _text(scope.get("holding_id")).lower() == requested_holding

    requested_client = _text(requested.get("cliente_id")).lower()
    if requested_client:
        return _text(scope.get("cliente_id")).lower() == requested_client

    requested_name = _text(
        requested.get("contexto_nome")
        or requested.get("holding_nome")
        or requested.get("contexto")
    ).casefold()
    scope_name = _text(
        scope.get("contexto_nome")
        or scope.get("holding_nome")
        or scope.get("contexto")
    ).casefold()
    return bool(requested_name and scope_name and requested_name == scope_name)


def snapshot_for_frontend(snapshot):
    """Remove rastreios internos que nao sao necessarios na devolutiva."""
    public = deepcopy(snapshot or {})
    public.pop("source_hash", None)

    health = public.get("health")
    if isinstance(health, dict):
        health.pop("rastreio_afirmacoes", None)

    for cut in public.get("cuts") or []:
        cut_health = cut.get("health") if isinstance(cut, dict) else None
        if isinstance(cut_health, dict):
            cut_health.pop("rastreio_afirmacoes", None)
    return public


def _candidate_cuts(archetype_records, microenvironment_records):
    team_records = _team(archetype_records) + _team(microenvironment_records)
    candidates = []
    seen = set()

    for field in RECORTE_FIELDS:
        values = sorted({_normalized(row.get(field)) for row in team_records}, key=str.casefold)
        for value in values:
            key = ((field, value.casefold()),)
            if key in seen:
                continue
            seen.add(key)
            candidates.append({
                "type": field,
                "label": f"{field}: {value}",
                "filters": [(field, value)],
            })

    pairs = sorted({
        (_normalized(row.get("sexo")), _normalized(row.get("etnia")))
        for row in team_records
    }, key=lambda pair: (pair[0].casefold(), pair[1].casefold()))
    for gender, ethnicity in pairs:
        key = (("sexo", gender.casefold()), ("etnia", ethnicity.casefold()))
        if key in seen:
            continue
        seen.add(key)
        candidates.append({
            "type": "sexo_etnia",
            "label": f"sexo: {gender} + etnia: {ethnicity}",
            "filters": [("sexo", gender), ("etnia", ethnicity)],
        })
    return candidates


def _matches(record, filters):
    return all(
        _normalized(record.get(field)).casefold() == _normalized(value).casefold()
        for field, value in filters
    )


def _filter_team_keep_all_leaders(records, filters):
    return _auto(records) + [row for row in _team(records) if _matches(row, filters)]


def _sample(archetype_records, microenvironment_records):
    archetype_team = _team(archetype_records)
    micro_team = _team(microenvironment_records)
    leader_ids = {
        _text(row.get("email_lider")).lower()
        for row in (archetype_records or []) + (microenvironment_records or [])
        if _text(row.get("email_lider"))
    }
    return {
        "lideres": len(leader_ids),
        "autoavaliacoes_arquetipos": len(_auto(archetype_records)),
        "autoavaliacoes_microambiente": len(_auto(microenvironment_records)),
        "respondentes_arquetipos": len(archetype_team),
        "respondentes_microambiente": len(micro_team),
    }


def build_scope_snapshot(
    *,
    scope,
    archetype_records,
    microenvironment_records,
    archetype_rows,
    microenvironment_rows,
    health_calculator,
    leadertrack_summarizer,
    minimum_sample=5,
    include_cuts=True,
    max_cuts=40,
):
    sample = _sample(archetype_records, microenvironment_records)
    enough = (
        sample["respondentes_arquetipos"] >= minimum_sample
        and sample["respondentes_microambiente"] >= minimum_sample
    )
    package = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "scope": scope,
        "minimum_sample": minimum_sample,
        "sample": sample,
        "status": "concluido" if enough else "amostra_insuficiente",
        "source_hash": source_hash(archetype_rows, microenvironment_rows),
        "health": None,
        "leadertrack": None,
        "microenvironment_gaps": None,
        "cuts": [],
        "findings": [],
    }
    if not enough:
        return package

    general_health = health_calculator(archetype_records, microenvironment_records)
    package["health"] = general_health
    package["leadertrack"] = leadertrack_summarizer(archetype_records, microenvironment_records)
    package["microenvironment_gaps"] = build_executive_microenvironment_gap_summary(
        package["leadertrack"]
    )
    if not include_cuts:
        return package
    general_score = general_health.get("score_final")

    eligible_candidates = []
    for candidate in _candidate_cuts(archetype_records, microenvironment_records):
        archetype_cut = _filter_team_keep_all_leaders(archetype_records, candidate["filters"])
        micro_cut = _filter_team_keep_all_leaders(microenvironment_records, candidate["filters"])
        cut_sample = _sample(archetype_cut, micro_cut)
        if (
            cut_sample["respondentes_arquetipos"] < minimum_sample
            or cut_sample["respondentes_microambiente"] < minimum_sample
        ):
            continue

        eligible_candidates.append((
            min(
                cut_sample["respondentes_arquetipos"],
                cut_sample["respondentes_microambiente"],
            ),
            candidate,
            archetype_cut,
            micro_cut,
            cut_sample,
        ))

    family_priority = {
        "sexo": 0,
        "etnia": 1,
        "sexo_etnia": 2,
        "departamento": 3,
        "cargo": 4,
    }
    eligible_candidates.sort(key=lambda item: (
        family_priority.get(item[1]["type"], 99),
        -item[0],
        item[1]["label"].casefold(),
    ))

    cuts = []
    for _, candidate, archetype_cut, micro_cut, cut_sample in eligible_candidates[:max_cuts]:

        health = health_calculator(archetype_cut, micro_cut)
        score = health.get("score_final")
        delta = None
        if score is not None and general_score is not None:
            delta = round(float(score) - float(general_score), 1)
        cut_leadertrack = leadertrack_summarizer(archetype_cut, micro_cut)
        cuts.append({
            "type": candidate["type"],
            "label": candidate["label"],
            "filters": dict(candidate["filters"]),
            "sample": cut_sample,
            "health": health,
            "leadertrack": cut_leadertrack,
            "microenvironment_gaps": build_executive_microenvironment_gap_summary(
                cut_leadertrack
            ),
            "delta_health_pp": delta,
        })

    cuts.sort(key=lambda item: abs(float(item.get("delta_health_pp") or 0)), reverse=True)
    package["cuts"] = cuts
    package["findings"] = [
        {
            "type": "health_difference",
            "cut": item["label"],
            "sample": item["sample"],
            "delta_pp": item["delta_health_pp"],
            "interpretation": (
                "Diferença relevante frente ao consolidado; tratar como hipótese "
                "de investigação, nunca como causalidade automática."
            ),
        }
        for item in cuts
        if item.get("delta_health_pp") is not None
        and abs(float(item["delta_health_pp"])) >= 5
    ]
    return package
