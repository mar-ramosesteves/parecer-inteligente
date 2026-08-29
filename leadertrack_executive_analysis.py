"""Contrato enxuto e guardrails da analise executiva LeaderTrack."""

import json
import unicodedata


EXECUTIVE_ANALYSIS_VERSION = "leadertrack-executive-analysis-v4"
ALLOWED_OWNERS = {
    "RH",
    "Diretoria",
    "People Analytics",
    "Comunicacao e Endomarketing",
    "Compliance",
    "Diversidade e Inclusao",
    "Liderancas",
}


def _fold_text(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).casefold()


def _small_delta_overclaim(value):
    text = _fold_text(value)
    return any(term in text for term in (
        "acima da media",
        "abaixo da media",
        "superior",
        "inferior",
        "maior saude",
        "menor saude",
        "mais saudavel",
        "menos saudavel",
        "diferenca relevante",
        "diferenca significativa",
    ))


def _safe_cut_questions(questions, cut_label, small_delta):
    clean = []
    for question in questions or []:
        folded = _fold_text(question)
        if small_delta and (
            _small_delta_overclaim(question)
            or ("por que" in folded and any(word in folded for word in ("maior", "menor", "melhor", "pior")))
            or ("influenc" in folded and any(word in folded for word in ("genero", "mascul", "feminin", "raca", "etnia")))
        ):
            continue
        clean.append(question)
    if small_delta and not clean:
        clean = [
            f"O sinal observado em {cut_label} persiste em uma proxima medicao?",
            "Quais condicoes organizacionais os respondentes relatam ao explicar sua experiencia?",
        ]
    return clean[:5]


def _sanitize_executive_text(value, no_large_health_deltas=False):
    if isinstance(value, list):
        return [_sanitize_executive_text(item, no_large_health_deltas) for item in value]
    if isinstance(value, dict):
        return {
            key: _sanitize_executive_text(item, no_large_health_deltas)
            for key, item in value.items()
        }
    if not isinstance(value, str):
        return value
    replacements = {
        "gaps elevados": "gaps observados",
        "gap elevado": "gap observado",
    }
    if no_large_health_deltas:
        replacements.update({
            "inferior ao consolidado": "proximo ao consolidado",
            "superior ao consolidado": "proximo ao consolidado",
            "acima do consolidado": "proximo ao consolidado",
            "abaixo do consolidado": "proximo ao consolidado",
        })
    text = value
    for source, target in replacements.items():
        text = text.replace(source, target).replace(source.capitalize(), target.capitalize())
    return text


def _outcome_kpis(values):
    process_terms = (
        "numero de",
        "quantidade de",
        "frequencia de",
        "alcance da",
        "alcance das",
        "participantes",
        "participacao",
        "entrevistas realizadas",
        "sessoes realizadas",
        "reunioes realizadas",
    )
    clean = [
        value for value in values or []
        if value and not any(term in _fold_text(value) for term in process_terms)
    ]
    return clean[:5] or [
        "Evolucao do indicador que originou a acao",
        "Persistencia do sinal na proxima medicao comparavel",
    ]


def _data_rows(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("dados", "rows", "items"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def _leader_current_rows(value):
    """Remove expectativa e gaps dos lideres, ausentes da leitura executiva."""
    blocked = ("ideal", "deveria", "esperad", "expect", "gap")
    clean = []
    for row in _data_rows(value):
        if not isinstance(row, dict):
            continue
        clean.append({
            key: item
            for key, item in row.items()
            if not any(term in _fold_text(key) for term in blocked)
        })
    return clean


def _micro_dimensions(micro):
    micro = micro or {}
    return {
        "resultado_organizacional_equipe": _data_rows(micro.get("media_dimensao")),
        "referencia_comparativa_lideres_como_e": _leader_current_rows(micro.get("auto_media_dimensao")),
        "n_avaliacoes_equipe": micro.get("n_avaliacoes_equipe"),
        "n_autoavaliacoes_lideres": micro.get("n_autoavaliacoes_lideres"),
    }


def _health_summary(health):
    health = health or {}
    summary = {
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
    summary["base_calculo"] = "somente respostas da equipe"
    return summary


def _leadertrack_summary(leadertrack):
    leadertrack = leadertrack or {}
    archetypes = leadertrack.get("arquetipos") or {}
    return {
        "arquetipos": {
            "resultado_organizacional_equipe": archetypes.get("mediaEquipe") or {},
            "referencia_comparativa_todos_lideres": archetypes.get("autoavaliacao") or {},
            "n_avaliacoes_equipe": archetypes.get("n_avaliacoes_equipe"),
            "n_autoavaliacoes_lideres": archetypes.get("n_autoavaliacoes_lideres"),
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
        "HIERARQUIA OBRIGATORIA: o resultado organizacional e sempre a media da equipe. O score e as "
        "dimensoes de saude emocional usam somente respostas da equipe. Em arquetipos, descreva primeiro "
        "as predominancias percebidas pela equipe; a media das autoavaliacoes dos lideres serve apenas para "
        "comparacao de percepcao. Em microambiente, use como resultado principal o como e e o como deveria "
        "ser da equipe; o como e dos lideres e apenas referencia comparativa. Nunca classifique uma "
        "autoavaliacao como forca, fragilidade ou resultado da organizacao e nunca fundamente uma acao apenas "
        "na autoavaliacao. "
        "Nao recalcule nenhum numero. Toda forca, ponto de atencao, finding e justificativa de acao "
        "deve indicar a evidencia numerica ou comparativa exata que a sustenta. "
        "REGRAS CONCEITUAIS OBRIGATORIAS: (1) Arquetipos sao perfis de estilo, nao indicadores de "
        "qualidade. Percentual baixo nao e deficiencia, gap ou problema; percentual alto nao e, por si, "
        "forca. Nao recomende elevar, equilibrar ou desenvolver um arquetipo apenas por seu percentual. "
        "Use arquetipos somente para descrever predominancias e divergencias entre autoavaliacao e "
        "percepcao da equipe, sem estabelecer perfil ideal. (2) Em saude emocional, delta absoluto abaixo "
        "de 5 p.p. e variacao exploratoria de menor intensidade. Nao use 'relevante', 'significativo', "
        "'superior', 'inferior', 'desigualdade' ou 'inequidade' para esses deltas e nao proponha intervencao "
        "direcionada com base apenas neles. Se nenhum recorte atingir 5 p.p., declare isso expressamente. "
        "(3) No microambiente, descreva como gap apenas a distancia entre 'como e' e 'como deveria ser'. "
        "Sem limiar fornecido, use 'maior gap observado' ou 'menor gap observado', nunca 'critico', "
        "'elevado' ou 'significativo'. (4) Nao diga que uma dimensao e destaque se ela nao estiver entre "
        "os maiores valores do proprio conjunto apresentado. (5) Classificacoes como Bom ou Regular podem "
        "ser citadas porque sao canonicas; nao as transforme em causalidade. "
        "REGRAS DOS RECORTES: os valores de lideres repetidos dentro de cada recorte sao o benchmark fixo "
        "de todos os lideres, sem filtro demografico. Nunca os atribua ao genero, raca/etnia ou departamento "
        "do recorte e nunca escreva 'gap dos lideres deste recorte'. Para microambiente por recorte, priorize "
        "o gap da equipe entre como e e como deveria ser e compare o como e da equipe ao benchmark atual dos "
        "lideres. Nao exponha nem calcule gap entre atual e ideal dos lideres, pois essa nao e a comparacao "
        "mostrada na leitura executiva. Para delta de saude abaixo de 5 p.p., use exatamente a ideia de que "
        "o score permanece proximo ao consolidado e a variacao esta abaixo do limiar. Nao pergunte por que um "
        "grupo tem saude maior ou menor e nao associe genero ou raca a comportamento, influencia ou capacidade. "
        "Pergunte se o sinal persiste e quais condicoes organizacionais os respondentes relatam. Uma classificacao "
        "Regular pode justificar investigacao por seu valor absoluto, mas nao por comparacao com o consolidado "
        "quando a diferenca for menor que 5 p.p. "
        "Quando nao houver diferenca de 5 p.p., procure padroes entre dimensoes e microambiente, mas os "
        "nomeie como sinais exploratorios de menor intensidade. "
        "Proponha acoes organizacionais concretas e proporcionais, que podem envolver RH, Diretoria, "
        "People Analytics, Comunicacao e Endomarketing, Compliance, Diversidade e Inclusao ou Liderancas. "
        "Comites, campanhas, rituais, treinamentos, KPIs e relatorios devem ser recomendados somente quando "
        "o dado justificar investigacao ou governanca; nunca como receita generica. Antes de uma intervencao "
        "direcionada, prefira um primeiro passo de validacao qualitativa quando a evidencia for exploratoria. "
        "Nao presuma que comunicacao, treinamento ou workshop resolva uma dimensao baixa: primeiro investigue "
        "determinantes organizacionais e somente depois escolha a intervencao. Divergencia entre arquetipos pode "
        "justificar dialogo de calibracao, nunca treinamento para aumentar ou reduzir um estilo. Nao proponha novo "
        "comite sem antes recomendar verificacao das instancias de governanca ja existentes. KPIs devem acompanhar "
        "resultado ou persistencia do sinal, nao apenas contar reunioes, entrevistas ou participantes. "
        "Nao invente metas numericas, cadencias ou instrumentos que nao possam ser acompanhados. "
        "Responda somente JSON valido, com estas chaves exatas: "
        "resumo_executivo, findings, leitura_por_recortes, acoes_organizacionais, governanca, limites. "
        "resumo_executivo deve conter sintese, forcas, pontos_de_atencao e perguntas_para_diretoria. "
        "findings e leitura_por_recortes devem ser listas. Cada item de leitura_por_recortes deve conter "
        "recorte, leitura, implicacao_prudente e perguntas_de_investigacao; nao inclua metricas, pois o "
        "backend as reaplicara. acoes_organizacionais deve conter titulo, justificativa, dono_recomendado, "
        "areas_envolvidas, horizonte, primeiro_passo, entregavel, kpis_sem_meta_inventada e criterio_de_revisao. "
        "governanca deve conter cadencia, comites_a_considerar, comunicacao_e_endomarketing, "
        "compliance_e_diversidade e people_analytics. Gere no maximo 5 acoes e priorize qualidade.\n\n"
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
    cut_deltas = [item.get("delta_saude_pp") for item in cuts.values()]
    numeric_deltas = []
    for value in cut_deltas:
        try:
            numeric_deltas.append(abs(float(value)))
        except (TypeError, ValueError):
            continue
    no_large_health_deltas = bool(numeric_deltas) and all(value < 5 for value in numeric_deltas)
    normalized_reads = []
    for item in analysis.get("leitura_por_recortes") or []:
        if not isinstance(item, dict):
            continue
        canonical = cuts.get(str(item.get("recorte") or "").strip().casefold())
        if not canonical:
            continue
        delta = canonical.get("delta_saude_pp")
        try:
            small_delta = delta is not None and abs(float(delta)) < 5
        except (TypeError, ValueError):
            small_delta = False
        reading = item.get("leitura")
        implication = item.get("implicacao_prudente")
        if small_delta:
            canonical_note = (
                f"A variacao de {float(delta):+.1f} p.p. permanece abaixo do limiar de 5 p.p. "
                "e deve ser tratada como sinal exploratorio de menor intensidade."
            )
            reading = canonical_note
            implication = (
                canonical_note
                + " Nao sustenta, isoladamente, intervencao direcionada nem inferencia causal."
            )
        normalized_reads.append({
            "recorte": canonical.get("recorte"),
            "amostra": canonical.get("amostra") or {},
            "score_saude_emocional": (canonical.get("saude_emocional") or {}).get("score_final"),
            "delta_saude_pp": delta,
            "leitura": reading,
            "implicacao_prudente": implication,
            "perguntas_de_investigacao": _safe_cut_questions(
                [] if small_delta else item.get("perguntas_de_investigacao") or [],
                canonical.get("recorte"),
                small_delta,
            ),
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
            "kpis_sem_meta_inventada": _outcome_kpis(item.get("kpis_sem_meta_inventada") or []),
            "criterio_de_revisao": item.get("criterio_de_revisao"),
        })

    normalized = {
        "versao": EXECUTIVE_ANALYSIS_VERSION,
        "resumo_executivo": analysis.get("resumo_executivo") or {},
        "findings": (analysis.get("findings") or [])[:12],
        "leitura_por_recortes": normalized_reads[:20],
        "acoes_organizacionais": actions[:5],
        "governanca": analysis.get("governanca") or {},
        "limites": analysis.get("limites") or (
            "Leitura agregada e exploratoria; nao estabelece causalidade nem diagnostico individual."
        ),
    }
    return _sanitize_executive_text(normalized, no_large_health_deltas)
