"""Contrato enxuto e guardrails da analise executiva LeaderTrack."""

import json


EXECUTIVE_ANALYSIS_VERSION = "leadertrack-executive-analysis-v1"
ALLOWED_OWNERS = {
    "RH",
    "Diretoria",
    "People Analytics",
    "Comunicacao e Endomarketing",
    "Compliance",
    "Diversidade e Inclusao",
    "Liderancas",
}


def _data_rows(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("dados", "rows", "items"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def _micro_dimensions(micro):
    micro = micro or {}
    return {
        "lideres": _data_rows(micro.get("auto_media_dimensao")),
        "equipe": _data_rows(micro.get("media_dimensao")),
        "n_autoavaliacoes_lideres": micro.get("n_autoavaliacoes_lideres"),
        "n_avaliacoes_equipe": micro.get("n_avaliacoes_equipe"),
    }


def _health_summary(health):
    health = health or {}
    return {
        key: health.get(key)
        for key in (
            "score_final",
            "classificacao",
            "label",
            "dimensoes",
            "categorias",
            "quantidade_afirmacoes_calculadas",
            "respondentes_arquetipos",
            "respondentes_microambiente",
            "versao_regra",
        )
        if health.get(key) is not None
    }


def _leadertrack_summary(leadertrack):
    leadertrack = leadertrack or {}
    archetypes = leadertrack.get("arquetipos") or {}
    return {
        "arquetipos": {
            "autoavaliacao_todos_lideres": archetypes.get("autoavaliacao") or {},
            "percepcao_equipe": archetypes.get("mediaEquipe") or {},
            "n_autoavaliacoes_lideres": archetypes.get("n_autoavaliacoes_lideres"),
            "n_avaliacoes_equipe": archetypes.get("n_avaliacoes_equipe"),
        },
        "microambiente_dimensoes": _micro_dimensions(leadertrack.get("microambiente")),
    }


def compact_snapshot_for_analysis(snapshot):
    """Mantem apenas agregados necessarios para a chamada de IA."""
    snapshot = snapshot or {}
    cuts = []
    for cut in snapshot.get("cuts") or []:
        cuts.append({
            "recorte": cut.get("label"),
            "filtros": cut.get("filters") or {},
            "amostra": cut.get("sample") or {},
            "saude_emocional": _health_summary(cut.get("health")),
            "delta_saude_pp": cut.get("delta_health_pp"),
            "leadertrack": _leadertrack_summary(cut.get("leadertrack")),
        })
    return {
        "versao": EXECUTIVE_ANALYSIS_VERSION,
        "escopo": snapshot.get("scope") or {},
        "amostra": snapshot.get("sample") or {},
        "saude_emocional": _health_summary(snapshot.get("health")),
        "leadertrack": _leadertrack_summary(snapshot.get("leadertrack")),
        "recortes_elegiveis": cuts,
        "findings_quantitativos": snapshot.get("findings") or [],
        "governanca": {
            "uso": "exclusivamente agregado e organizacional",
            "pdi_individual": False,
            "diagnostico_clinico": False,
            "causalidade_automatica": False,
            "amostra_minima": snapshot.get("minimum_sample"),
        },
    }


def build_executive_analysis_prompt(package):
    return (
        "Voce e um consultor executivo de RH do LeaderTrack. Analise exclusivamente o JSON abaixo. "
        "Esta e uma devolutiva executiva agregada, nunca um PDI de lider. Nao invente fatos, causas, "
        "percentuais, historico, politicas, indicadores realizados ou caracteristicas dos grupos. "
        "Nao faca diagnostico clinico e nao atribua culpa. Diferencas entre grupos sao percepcoes "
        "agregadas e devem ser tratadas como hipoteses para investigacao. "
        "As autoavaliacoes representam todos os lideres e os filtros se aplicam apenas aos respondentes. "
        "Nao recalcule nenhum numero. Nos textos, evite repetir numeros; use os campos estruturados. "
        "Quando nao houver diferenca de 5 p.p., ainda procure padroes consistentes entre dimensoes, "
        "arquetipos e microambiente, deixando claro que sao sinais de menor intensidade. "
        "Proponha acoes organizacionais concretas e proporcionais, que podem envolver RH, Diretoria, "
        "People Analytics, Comunicacao e Endomarketing, Compliance, Diversidade e Inclusao ou Liderancas. "
        "Comites, campanhas, rituais, KPIs e relatorios devem ser recomendados somente quando o dado "
        "justificar investigacao ou governanca; nunca como receita generica. Nao invente metas numericas. "
        "Responda somente JSON valido, com estas chaves exatas: "
        "resumo_executivo, findings, leitura_por_recortes, acoes_organizacionais, governanca, limites. "
        "resumo_executivo deve conter sintese, forcas, pontos_de_atencao e perguntas_para_diretoria. "
        "findings e leitura_por_recortes devem ser listas. Cada item de leitura_por_recortes deve conter "
        "recorte, leitura, implicacao_prudente e perguntas_de_investigacao; nao inclua metricas, pois o "
        "backend as reaplicara. acoes_organizacionais deve conter titulo, justificativa, dono_recomendado, "
        "areas_envolvidas, horizonte, primeiro_passo, entregavel, kpis_sem_meta_inventada e criterio_de_revisao. "
        "governanca deve conter cadencia, comites_a_considerar, comunicacao_e_endomarketing, "
        "compliance_e_diversidade e people_analytics. Gere no maximo 8 acoes e priorize qualidade.\n\n"
        "SNAPSHOT_EXECUTIVO_JSON:\n"
        + json.dumps(package, ensure_ascii=False, separators=(",", ":"), default=str)
    )


def normalize_executive_analysis(analysis, package):
    """Reaplica metricas canonicas e limita a estrutura devolvida pela IA."""
    if not isinstance(analysis, dict):
        raise ValueError("A analise executiva precisa ser um objeto JSON.")

    cuts = {
        str(item.get("recorte") or "").strip().casefold(): item
        for item in package.get("recortes_elegiveis") or []
        if str(item.get("recorte") or "").strip()
    }
    normalized_reads = []
    for item in analysis.get("leitura_por_recortes") or []:
        if not isinstance(item, dict):
            continue
        canonical = cuts.get(str(item.get("recorte") or "").strip().casefold())
        if not canonical:
            continue
        normalized_reads.append({
            "recorte": canonical.get("recorte"),
            "amostra": canonical.get("amostra") or {},
            "score_saude_emocional": (canonical.get("saude_emocional") or {}).get("score_final"),
            "delta_saude_pp": canonical.get("delta_saude_pp"),
            "leitura": item.get("leitura"),
            "implicacao_prudente": item.get("implicacao_prudente"),
            "perguntas_de_investigacao": item.get("perguntas_de_investigacao") or [],
        })

    actions = []
    for item in analysis.get("acoes_organizacionais") or []:
        if not isinstance(item, dict):
            continue
        owner = str(item.get("dono_recomendado") or "RH").strip()
        if owner not in ALLOWED_OWNERS:
            owner = "RH"
        actions.append({
            "titulo": item.get("titulo"),
            "justificativa": item.get("justificativa"),
            "dono_recomendado": owner,
            "areas_envolvidas": item.get("areas_envolvidas") or [],
            "horizonte": item.get("horizonte"),
            "primeiro_passo": item.get("primeiro_passo"),
            "entregavel": item.get("entregavel"),
            "kpis_sem_meta_inventada": item.get("kpis_sem_meta_inventada") or [],
            "criterio_de_revisao": item.get("criterio_de_revisao"),
        })

    return {
        "versao": EXECUTIVE_ANALYSIS_VERSION,
        "resumo_executivo": analysis.get("resumo_executivo") or {},
        "findings": (analysis.get("findings") or [])[:12],
        "leitura_por_recortes": normalized_reads[:20],
        "acoes_organizacionais": actions[:8],
        "governanca": analysis.get("governanca") or {},
        "limites": analysis.get("limites") or (
            "Leitura agregada e exploratoria; nao estabelece causalidade nem diagnostico individual."
        ),
    }
