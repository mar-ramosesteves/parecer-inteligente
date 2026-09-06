"""Montagem deterministica dos snapshots executivos LeaderTrack.

O modulo trabalha apenas com registros ja normalizados pelo backend. Respostas
individuais entram no calculo em memoria, mas nunca fazem parte do pacote salvo.
"""

from copy import deepcopy
from hashlib import sha256
import json


SNAPSHOT_SCHEMA_VERSION = "leadertrack-executivo-v3"
RECORTE_FIELDS = ("sexo", "etnia", "departamento", "cargo")
EXECUTIVE_GAP_RULE_VERSION = "microambiente-executivo-v1"
ARCHETYPE_RELATIVE_RULE_VERSION = "arquetipos-assinatura-relativa-v1"
ARCHETYPE_MICRO_CORRELATION_RULE_VERSION = "arquetipos-microambiente-correlacao-v1"
EXECUTIVE_GAP_MONITORING_PP = 10.0
EXECUTIVE_GAP_RELEVANT_PP = 20.0
EXECUTIVE_GAP_CRITICAL_PP = 35.0
RELATIVE_SCALE_BASE = 100.0
RELATIVE_SCALE_MIN = 50.0
RELATIVE_SCALE_MAX = 150.0
CORRELATION_MIN_LEADERS = 10
CORRELATION_MIN_ABS_R = 0.60


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


def _mean(values):
    numeric = [float(value) for value in values if value is not None]
    if not numeric:
        return None
    return sum(numeric) / len(numeric)


def _pearson(pairs):
    clean = [
        (float(x), float(y))
        for x, y in (pairs or [])
        if x is not None and y is not None
    ]
    n = len(clean)
    if n < 2:
        return None
    mean_x = sum(x for x, _ in clean) / n
    mean_y = sum(y for _, y in clean) / n
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in clean)
    denom_x = sum((x - mean_x) ** 2 for x, _ in clean)
    denom_y = sum((y - mean_y) ** 2 for _, y in clean)
    denominator = (denom_x * denom_y) ** 0.5
    if not denominator:
        return None
    return numerator / denominator


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


def _leader_ids(*record_groups):
    return sorted({
        _text(row.get("email_lider")).lower()
        for records in record_groups
        for row in (records or [])
        if _text(row.get("email_lider"))
    })


def _records_for_leader(records, leader_id):
    target = _text(leader_id).lower()
    return [
        row for row in (records or [])
        if _text(row.get("email_lider")).lower() == target
    ]


def _archetype_scores(leadertrack):
    scores = ((leadertrack or {}).get("arquetipos") or {}).get("mediaEquipe") or {}
    return {
        str(name): _number(value)
        for name, value in scores.items()
        if str(name or "").strip() and _number(value) is not None
    }


def _micro_dimension_scores(leadertrack):
    micro = ((leadertrack or {}).get("microambiente") or {}).get("media_dimensao")
    scores = {}
    for row in _rows(micro):
        if not isinstance(row, dict):
            continue
        dimension = _text(row.get("DIMENSAO"))
        value = _number(row.get("REAL_%"))
        if dimension and value is not None:
            scores[dimension] = value
    return scores


def _leader_scores(archetype_records, microenvironment_records, leadertrack_summarizer):
    leaders = []
    for leader_id in _leader_ids(archetype_records, microenvironment_records):
        archetype_rows = _records_for_leader(archetype_records, leader_id)
        micro_rows = _records_for_leader(microenvironment_records, leader_id)
        summary = leadertrack_summarizer(archetype_rows, micro_rows)
        archetypes = _archetype_scores(summary)
        micro_dimensions = _micro_dimension_scores(summary)
        if archetypes or micro_dimensions:
            leaders.append({
                "leader_id": leader_id,
                "arquetipos": archetypes,
                "microambiente_dimensoes": micro_dimensions,
                "n_respostas_arquetipos": len(_team(archetype_rows)),
                "n_respostas_microambiente": len(_team(micro_rows)),
            })
    return leaders


def build_archetype_relative_signature(leadertrack, leader_scores):
    """Calcula a assinatura relativa do contexto sem substituir o grafico absoluto."""
    benchmark = _archetype_scores(leadertrack)
    relative_sums = {name: [] for name in benchmark}
    top_counts = {}

    for leader in leader_scores or []:
        relative = {}
        for name, base in benchmark.items():
            value = (leader.get("arquetipos") or {}).get(name)
            if value is None or not base:
                continue
            index = (float(value) / float(base)) * RELATIVE_SCALE_BASE
            relative[name] = round(index, 1)
            relative_sums[name].append(index)
        if relative:
            top = max(relative.items(), key=lambda item: item[1])[0]
            top_counts[top] = top_counts.get(top, 0) + 1

    archetypes = []
    for name, base in benchmark.items():
        values = relative_sums.get(name) or []
        archetypes.append({
            "arquetipo": name,
            "pontuacao_absoluta_media": round(float(base), 2),
            "indice_relativo_medio": round(_mean(values), 1) if values else None,
            "lideres_acima_da_media": sum(1 for value in values if value > RELATIVE_SCALE_BASE),
            "lideres_top1_relativo": top_counts.get(name, 0),
        })
    archetypes.sort(
        key=lambda item: (
            -(item.get("lideres_top1_relativo") or 0),
            -(item.get("pontuacao_absoluta_media") or 0),
            item.get("arquetipo") or "",
        )
    )
    return {
        "versao_regra": ARCHETYPE_RELATIVE_RULE_VERSION,
        "base_calculo": "media da equipe por lider comparada a media do contexto",
        "escala_fixa": {
            "base": RELATIVE_SCALE_BASE,
            "minimo_visual": RELATIVE_SCALE_MIN,
            "maximo_visual": RELATIVE_SCALE_MAX,
        },
        "benchmark_contexto": benchmark,
        "arquetipos": archetypes,
        "distribuicao_top1_relativo": top_counts,
        "n_lideres_calculados": len([leader for leader in leader_scores or [] if leader.get("arquetipos")]),
    }


def build_archetype_microenvironment_correlations(leader_scores, max_items=8):
    """Relaciona estilos percebidos e microambiente sem inferir causalidade."""
    leaders = [
        leader for leader in (leader_scores or [])
        if leader.get("arquetipos") and leader.get("microambiente_dimensoes")
    ]
    archetypes = sorted({
        name for leader in leaders for name in (leader.get("arquetipos") or {})
    })
    dimensions = sorted({
        name for leader in leaders for name in (leader.get("microambiente_dimensoes") or {})
    })
    correlations = []
    for archetype in archetypes:
        for dimension in dimensions:
            pairs = [
                (
                    (leader.get("arquetipos") or {}).get(archetype),
                    (leader.get("microambiente_dimensoes") or {}).get(dimension),
                )
                for leader in leaders
            ]
            pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
            coefficient = _pearson(pairs)
            if coefficient is None or len(pairs) < CORRELATION_MIN_LEADERS:
                continue
            if abs(coefficient) < CORRELATION_MIN_ABS_R:
                continue
            correlations.append({
                "arquetipo": archetype,
                "dimensao_microambiente": dimension,
                "r": round(coefficient, 3),
                "n_lideres": len(pairs),
                "leitura": "associacao positiva" if coefficient > 0 else "associacao negativa",
            })
    correlations.sort(key=lambda item: (-abs(item["r"]), item["arquetipo"], item["dimensao_microambiente"]))
    return {
        "versao_regra": ARCHETYPE_MICRO_CORRELATION_RULE_VERSION,
        "base_calculo": "correlacao de Pearson entre medias por lider",
        "limiares": {
            "minimo_lideres": CORRELATION_MIN_LEADERS,
            "minimo_abs_r": CORRELATION_MIN_ABS_R,
        },
        "n_lideres_calculados": len(leaders),
        "correlacoes": correlations[:max_items],
        "limite_interpretacao": "associacao estatistica exploratoria, sem causalidade automatica",
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
        "archetype_relative_signature": None,
        "archetype_microenvironment_correlations": None,
        "microenvironment_gaps": None,
        "cuts": [],
        "findings": [],
    }
    if not enough:
        return package

    general_health = health_calculator(archetype_records, microenvironment_records)
    package["health"] = general_health
    package["leadertrack"] = leadertrack_summarizer(archetype_records, microenvironment_records)
    leader_scores = _leader_scores(
        archetype_records,
        microenvironment_records,
        leadertrack_summarizer,
    )
    package["archetype_relative_signature"] = build_archetype_relative_signature(
        package["leadertrack"],
        leader_scores,
    )
    package["archetype_microenvironment_correlations"] = (
        build_archetype_microenvironment_correlations(leader_scores)
    )
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
