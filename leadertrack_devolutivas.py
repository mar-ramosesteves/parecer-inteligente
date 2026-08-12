import json
import re
from datetime import datetime


def fix_text(value):
    text = str(value or "")
    replacements = {
        "ColaboraÃ§Ã£o MÃºtua": "Colaboracao Mutua",
        "ColaboraÃƒÂ§ÃƒÂ£o MÃƒÂºtua": "Colaboracao Mutua",
        "Colaboração Mútua": "Colaboracao Mutua",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.strip()


def slug(value):
    text = fix_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")[:60] or "item"


def parse_percent(value, default=0):
    if value in (None, ""):
        return default
    try:
        return float(str(value).replace("%", "").replace(",", ".").strip())
    except Exception:
        return default


def parse_json_response(raw):
    if isinstance(raw, dict):
        parsed = raw
    elif isinstance(raw, str):
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        parsed = json.loads(text)
    else:
        raise ValueError("Resposta da IA nao e texto nem objeto JSON.")

    if isinstance(parsed, dict) and isinstance(parsed.get("saida_obrigatoria"), dict):
        return parsed["saida_obrigatoria"]
    return parsed


def archetype_summary(dados_arquetipos_comparativo):
    chart = dados_arquetipos_comparativo or {}
    team = {fix_text(k): float(v or 0) for k, v in (chart.get("mediaEquipe") or {}).items()}
    auto = {fix_text(k): float(v or 0) for k, v in (chart.get("autoavaliacao") or {}).items()}
    ordered = sorted(team.items(), key=lambda item: item[1], reverse=True)
    return {
        "autoavaliacao": auto,
        "percepcao_equipe": team,
        "dominantes": [name for name, value in ordered if value >= 60],
        "suporte": [name for name, value in ordered if 50 <= value < 60],
        "menos_ativos": [name for name, value in sorted(team.items(), key=lambda item: item[1]) if value < 50],
    }


def microenvironment_affirmations(dados_microambiente_analitico):
    rows = (dados_microambiente_analitico or {}).get("dados") or []
    normalized = []
    for row in rows:
        gap_original = parse_percent(row.get("GAP", 0))
        real = parse_percent(row.get("PONTUACAO_REAL", 0))
        ideal = parse_percent(row.get("PONTUACAO_IDEAL", 0))
        gap_calculado = abs(ideal - real)
        gap = abs(gap_original) if gap_original else gap_calculado
        normalized.append({
            "questao": fix_text(row.get("QUESTAO")),
            "afirmacao": fix_text(row.get("AFIRMACAO")),
            "dimensao": fix_text(row.get("DIMENSAO")),
            "subdimensao": fix_text(row.get("SUBDIMENSAO")),
            "real_percentual": real,
            "ideal_percentual": ideal,
            "gap_percentual": gap,
            "gap_original_percentual": gap_original,
            "criticidade": classify_gap(gap),
        })
    return sorted(normalized, key=lambda item: item["gap_percentual"], reverse=True)


def classify_gap(gap):
    gap = float(gap or 0)
    if gap >= 35:
        return "critico"
    if gap >= 25:
        return "moderado_alto"
    if gap >= 20:
        return "relevante"
    return "monitoramento"


def filter_gaps(items, gap_minimo=20):
    return [item for item in items if float(item.get("gap_percentual") or 0) >= float(gap_minimo or 20)]


def low_reference_affirmations(items, threshold=70):
    threshold = float(threshold or 70)
    return [
        item for item in items
        if float(item.get("real_percentual") or 0) < threshold
        and float(item.get("ideal_percentual") or 0) < threshold
    ]


def severity_summary(items, low_reference_items=None):
    low_reference_items = low_reference_items or []
    return {
        "total_afirmacoes": len(items),
        "gaps_relevantes_acima_20": len(filter_gaps(items, 20)),
        "gaps_moderados_altos_acima_25": len(filter_gaps(items, 25)),
        "gaps_criticos_acima_35": len(filter_gaps(items, 35)),
        "baixa_referencia_abaixo_70": len(low_reference_items),
        "regua_sugerida": {
            "20": "todos_os_gaps_relevantes",
            "25": "gaps_moderados_altos",
            "35": "gaps_criticos",
        },
    }


def feedback_mode(gaps, low_reference_items=None, few_gaps_limit=3):
    low_reference_items = low_reference_items or []
    gap_count = len(gaps or [])
    if gap_count == 0 and not low_reference_items:
        return {
            "modo": "sustentacao_e_repertorio",
            "titulo": "Microambiente sem gaps relevantes",
            "leitura": (
                "O lider nao deve ficar sem devolutiva. O foco passa a ser manter os niveis positivos, "
                "prevenir queda de qualidade do microambiente e ampliar repertorio de arquetipos."
            ),
        }
    if gap_count <= few_gaps_limit:
        return {
            "modo": "evolucao_seletiva",
            "titulo": "Poucos gaps relevantes",
            "leitura": (
                "Ha poucos pontos de atencao. A devolutiva deve tratar os gaps existentes sem transformar "
                "a experiencia em plano corretivo pesado, combinando melhoria seletiva, sustentacao e repertorio."
            ),
        }
    return {
        "modo": "desenvolvimento_por_gaps",
        "titulo": "Gaps relevantes de microambiente",
        "leitura": (
            "Ha volume suficiente de gaps para organizar ciclos trimestrais de PDI, priorizando severidade, "
            "impacto operacional e faseamento anual."
        ),
    }


def build_sustainability_plan(gaps, low_reference_items=None):
    low_reference_items = low_reference_items or []
    return {
        "objetivo": "Manter niveis positivos de microambiente e evitar regressao dos gaps baixos.",
        "quando_usar": "Usar quando nao houver gaps relevantes ou quando houver poucos gaps no corte definido.",
        "acoes_sugeridas": [
            "Identificar quais praticas de gestao sustentam os melhores resultados atuais.",
            "Manter rituais de alinhamento, feedback, reconhecimento e acompanhamento que ja funcionam.",
            "Criar indicadores de manutencao para nao descobrir queda apenas na proxima rodada anual.",
            "Realizar revisoes leves trimestrais com evidencias e percepcao da equipe, sem novo inventario.",
        ],
        "perguntas_para_o_lider": [
            "Quais praticas atuais explicam os melhores resultados do seu microambiente?",
            "O que nao pode ser perdido nos proximos meses?",
            "Que sinal precoce indicaria que a equipe esta perdendo clareza, energia ou colaboracao?",
        ],
        "indicadores_sugeridos": [
            "Sinais de manutencao de produtividade e qualidade.",
            "Retrabalho, prazos e SLA sem deterioracao.",
            "Feedbacks espontaneos de clareza, colaboracao e suporte.",
            "Evidencias de continuidade dos rituais de gestao.",
        ],
        "baixa_referencia": {
            "existe": bool(low_reference_items),
            "leitura": (
                "Quando real e ideal ficam abaixo de 70%, o plano deve elevar ambicao de referencia, "
                "pois a equipe pode estar se contentando com um patamar baixo."
            ),
            "afirmacoes": low_reference_items,
        },
    }


def build_archetype_development_plan(arquetipos):
    dominantes = arquetipos.get("dominantes") or []
    suporte = arquetipos.get("suporte") or []
    menos_ativos = arquetipos.get("menos_ativos") or []
    targets = suporte + menos_ativos
    if not targets:
        targets = [
            name for name in (arquetipos.get("percepcao_equipe") or {}).keys()
            if name not in dominantes
        ]
    return {
        "objetivo": "Ampliar repertorio de lideranca sem desvalorizar os arquetipos dominantes.",
        "premissa": "Todo arquetipo tem potencia positiva. O desenvolvimento busca escolha consciente do estilo certo para cada situacao.",
        "arquetipos_dominantes_a_preservar": dominantes,
        "arquetipos_a_explorar": targets,
        "acoes_sugeridas": [
            "Comparar autoavaliacao e percepcao da equipe para aumentar realismo de autopercepcao.",
            "Escolher um arquetipo nao dominante por ciclo para praticar em situacoes reais.",
            "Definir uma situacao concreta em que o novo arquetipo sera usado de forma intencional.",
            "Registrar evidencias de comportamento e pedir feedback qualitativo ao final do ciclo.",
        ],
        "perguntas_para_o_lider": [
            "Em quais situacoes seus arquetipos dominantes ajudam muito?",
            "Em quais situacoes eles podem limitar sua resposta como lider?",
            "Que arquetipo pouco ativo poderia ampliar sua efetividade neste trimestre?",
        ],
        "resultado_esperado": (
            "Lider com maior flexibilidade comportamental, autopercepcao mais realista e capacidade de sustentar "
            "microambiente positivo mesmo sem gaps relevantes."
        ),
    }


def annual_phasing(items, gaps_per_cycle=4):
    cycles = []
    for index in range(0, len(items), gaps_per_cycle):
        cycle_number = index // gaps_per_cycle
        start_week = cycle_number * 12 + 1
        end_week = start_week + 11
        cycle_items = items[index:index + gaps_per_cycle]
        cycles.append({
            "ciclo": f"Ciclo {cycle_number + 1}",
            "periodo_sugerido": f"Semanas {start_week} a {end_week}",
            "objetivo": (
                "Intervencao imediata nos gaps mais criticos"
                if cycle_number == 0
                else "Proximo bloco de gaps, apos revisao consultiva do ciclo anterior"
            ),
            "quantidade_afirmacoes": len(cycle_items),
            "afirmacoes": cycle_items,
            "revisao_informal_ao_final": "Revisar evidencias, percepcao do lider e sinais da equipe sem nova rodada formal.",
        })
    return {
        "premissa": "A rodada oficial e anual. Os gaps podem ser trabalhados em ciclos trimestrais de PDI, sem nova rodada entre ciclos.",
        "maximo_recomendado_por_ciclo": gaps_per_cycle,
        "total_afirmacoes_faseadas": len(items),
        "ciclos": cycles,
    }


def thematic_grouping(items, max_items_per_group=6):
    groups_by_key = {}
    for item in items or []:
        dimensao = item.get("dimensao") or "Sem dimensao"
        subdimensao = item.get("subdimensao") or "Sem subdimensao"
        key = f"{dimensao}|{subdimensao}"
        if key not in groups_by_key:
            groups_by_key[key] = {
                "grupo_id": f"grupo_{slug(dimensao)}_{slug(subdimensao)}",
                "titulo": f"{dimensao} / {subdimensao}",
                "dimensao": dimensao,
                "subdimensao": subdimensao,
                "afirmacoes": [],
            }
        groups_by_key[key]["afirmacoes"].append(item)

    groups = []
    for group in groups_by_key.values():
        afirmacoes = sorted(
            group["afirmacoes"],
            key=lambda gap: float(gap.get("gap_percentual") or 0),
            reverse=True,
        )
        gap_medio = (
            sum(float(gap.get("gap_percentual") or 0) for gap in afirmacoes) / len(afirmacoes)
            if afirmacoes else 0
        )
        gap_maximo = max((float(gap.get("gap_percentual") or 0) for gap in afirmacoes), default=0)
        questoes = [gap.get("questao") for gap in afirmacoes if gap.get("questao")]
        group["afirmacoes"] = afirmacoes[:max_items_per_group]
        group["total_afirmacoes"] = len(afirmacoes)
        group["questoes"] = questoes
        group["gap_medio_percentual"] = round(gap_medio, 2)
        group["gap_maximo_percentual"] = round(gap_maximo, 2)
        group["criticidade"] = classify_gap(gap_maximo)
        group["plano_integrado_sugerido"] = {
            "tipo": "estrutura_sem_ia",
            "objetivo": (
                f"Tratar de forma integrada {len(afirmacoes)} afirmacao(oes) conectada(s) "
                f"a {group['dimensao']} / {group['subdimensao']}."
            ),
            "premissa": (
                "Quando varias afirmacoes apontam para a mesma dimensao ou subdimensao, "
                "o PDI pode ser organizado por tema para reduzir volume, aumentar foco e facilitar execucao."
            ),
            "como_usar": [
                "Apresentar ao lider que o plano cobre um conjunto de afirmacoes relacionadas.",
                "Escolher rituais e comportamentos que ataquem a causa comum do grupo.",
                "Registrar semanalmente quais afirmacoes foram impactadas por cada acao.",
                "Revisar evidencias nas semanas 4, 8 e 12 antes de abrir novo bloco de desenvolvimento.",
            ],
            "observacao": (
                "Esta estrutura e uma sugestao tecnica sem IA profunda. A geracao detalhada pode ser feita "
                "posteriormente pelo LeaderTrackbot para o grupo selecionado."
            ),
        }
        groups.append(group)

    return sorted(
        groups,
        key=lambda group: (
            int(group.get("total_afirmacoes") or 0),
            float(group.get("gap_maximo_percentual") or 0),
        ),
        reverse=True,
    )


def maintenance_grouping(all_items, low_reference_items=None, max_items=6):
    all_items = all_items or []
    low_reference_items = low_reference_items or []
    if not all_items:
        return []

    pontos_de_atencao = sorted(
        all_items,
        key=lambda item: float(item.get("gap_percentual") or 0),
        reverse=True,
    )[:max_items]
    melhores_pontos = sorted(
        all_items,
        key=lambda item: float(item.get("real_percentual") or 0),
        reverse=True,
    )[:max_items]
    afirmacoes = pontos_de_atencao or melhores_pontos
    gap_maximo = max((float(item.get("gap_percentual") or 0) for item in afirmacoes), default=0)
    gap_medio = (
        sum(float(item.get("gap_percentual") or 0) for item in afirmacoes) / len(afirmacoes)
        if afirmacoes else 0
    )
    return [
        {
            "grupo_id": "grupo_manutencao_microambiente",
            "titulo": "Manutencao do Microambiente / Prevencao de Gaps",
            "dimensao": "Manutencao do Microambiente",
            "subdimensao": "Prevencao de Gaps",
            "tipo": "manutencao_sem_gap_relevante",
            "criticidade": "sustentacao",
            "total_afirmacoes": len(afirmacoes),
            "questoes": [item.get("questao") for item in afirmacoes if item.get("questao")],
            "gap_medio_percentual": round(gap_medio, 2),
            "gap_maximo_percentual": round(gap_maximo, 2),
            "afirmacoes": afirmacoes,
            "melhores_pontos": melhores_pontos,
            "pontos_de_atencao_sub_20": pontos_de_atencao,
            "baixa_referencia": low_reference_items,
            "plano_integrado_sugerido": {
                "tipo": "manutencao_e_prevencao",
                "objetivo": (
                    "Parabenizar o lider pela ausencia de gaps relevantes, preservar as praticas que sustentam "
                    "os melhores resultados e atuar preventivamente nos maiores gaps abaixo do corte."
                ),
                "premissa": (
                    "A ausencia de gaps acima do corte nao elimina a necessidade de PDI; muda o foco para "
                    "manutencao, reforco positivo, ampliacao de repertorio e prevencao de queda na proxima rodada."
                ),
                "como_usar": [
                    "Abrir a devolutiva reconhecendo os melhores sinais do microambiente.",
                    "Identificar quais praticas do lider explicam esses resultados.",
                    "Dar atencao aos maiores gaps abaixo do corte como sinais preventivos.",
                    "Definir rituais de manutencao e indicadores leves de acompanhamento.",
                ],
                "observacao": (
                    "Plano gerado para lideres sem gaps relevantes no corte atual, com foco em sustentar "
                    "o que esta forte e reduzir risco de regressao futura."
                ),
            },
        }
    ]


def diagnostic_schema():
    return {
        "gap": {},
        "diagnostico_tecnico": {
            "sintese_executiva": "",
            "hipoteses_provaveis": [],
            "impacto_no_microambiente": "",
            "impacto_na_rotina_da_equipe": "",
            "impacto_operacional_esperado": "",
            "pontos_de_atencao_na_devolutiva": [],
            "cuidados_de_confidencialidade": [],
        },
        "indicadores_de_efetividade": {
            "indicadores_operacionais_sugeridos": [],
            "por_que_medir": "",
            "como_estabelecer_linha_de_base": "",
            "como_comparar_evolucao_sem_nova_rodada": "",
            "cuidados_para_nao_confundir_causalidade": [],
        },
        "cruzamento_arquetipos": {
            "dominantes": [],
            "como_podem_ajudar": [],
            "riscos_de_excesso": [],
            "arquetipos_a_desenvolver": [],
            "como_desenvolver_arquetipos_complementares": [],
            "correlacao_goleman": [],
            "justificativa_desenvolvimento": "",
        },
        "conducao_da_devolutiva": {
            "objetivo_da_conversa": "",
            "abertura_sugerida": "",
            "perguntas_para_o_lider": [],
            "perguntas_para_planejar_com_a_equipe": [],
            "o_que_validar_antes_de_agir": [],
            "o_que_evitar": [],
            "resultado_esperado_da_devolutiva": "",
        },
    }


def weekly_chunk_schema(start_week, end_week):
    schema = {
        "criterio_de_encerramento": "",
        "plano_12_semanas": [],
        "campos_obrigatorios_por_semana": {
            "semana": start_week,
            "foco_da_semana": "",
            "tipo_de_intervencao": "reuniao|pratica_diaria|autodesenvolvimento|alinhamento_com_superior|treinamento|leitura|observacao_em_campo|comunicacao|experimento_operacional|feedback_1a1",
            "afirmacao_ou_assunto_especifico": "",
            "diferenca_objetiva_da_semana_anterior": "",
            "proxima_pratica_observavel": "",
            "objetivo": "",
            "arquetipo_dominante_a_acionar": "",
            "como_usar_arquetipo_dominante": "",
            "arquetipo_complementar_a_desenvolver": "",
            "pratica_para_desenvolver_arquetipo": "",
            "acoes_praticas": [],
            "perguntas_para_equipe": [],
            "tarefa_do_lider": [],
            "tarefa_da_equipe": [],
            "indicador": "",
            "resultado_esperado": "",
            "status": "nao_iniciado",
        },
    }
    if end_week in (4, 8, 12):
        schema["revisao_parcial_informal"] = {
            "momento": f"Semana {end_week}",
            "objetivo": "",
            "perguntas_de_revisao": [],
            "evidencias_a_observar": [],
            "decisao": "manter_ajustar_ou_repriorizar",
        }
    return schema


def build_diagnostic_prompt(leader, arquetipos, gap, indicadores_disponiveis):
    payload = {
        "lider": leader,
        "arquetipos": arquetipos,
        "afirmacao_critica": gap,
        "indicadores_operacionais_disponiveis": indicadores_disponiveis,
        "saida_obrigatoria": diagnostic_schema(),
    }
    return (
        "Gere apenas o diagnostico tecnico para uma devolutiva individual LeaderTrack, sem plano semanal. "
        "Analise o gap, a dimensao/subdimensao de microambiente, os arquetipos dominantes, riscos de excesso e arquetipos a desenvolver. "
        "Inclua impacto operacional esperado e indicadores reais que a empresa deveria acompanhar para avaliar efetividade. "
        "Nao invente valores nem metas. Se nao houver indicador operacional disponivel, sugira o que coletar como linha de base. "
        "Nao use saude emocional no relatorio individual. Responda somente JSON valido no formato de saida_obrigatoria.\n\n"
        f"CONTEXTO_JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_weekly_prompt(leader, arquetipos, gap, diagnostic, start_week, end_week, indicadores_disponiveis):
    diagnostic = diagnostic or {}
    diagnostico_tecnico = diagnostic.get("diagnostico_tecnico") or {}
    cruzamento = diagnostic.get("cruzamento_arquetipos") or {}
    indicadores = diagnostic.get("indicadores_de_efetividade") or {}
    diagnostic_resumo = {
        "sintese_executiva": diagnostico_tecnico.get("sintese_executiva"),
        "hipoteses_provaveis": diagnostico_tecnico.get("hipoteses_provaveis"),
        "impacto_operacional_esperado": diagnostico_tecnico.get("impacto_operacional_esperado"),
        "arquetipos_dominantes": cruzamento.get("dominantes"),
        "arquetipos_a_desenvolver": cruzamento.get("arquetipos_a_desenvolver"),
        "riscos_de_excesso": cruzamento.get("riscos_de_excesso"),
        "indicadores_sugeridos": indicadores.get("indicadores_operacionais_sugeridos"),
    }
    payload = {
        "lider": leader,
        "arquetipos": arquetipos,
        "afirmacao_critica": gap,
        "diagnostico_tecnico": diagnostic_resumo,
        "indicadores_operacionais_disponiveis": indicadores_disponiveis,
        "semanas_a_gerar": [start_week, end_week],
        "saida_obrigatoria": weekly_chunk_schema(start_week, end_week),
    }
    return (
        f"Gere as semanas {start_week} a {end_week} de um PDI LeaderTrack, mas inclua somente semanas com intervencao nova e util. "
        "A rodada oficial e anual; estas semanas sao acompanhamento informal, sem nova rodada e sem novo inventario. "
        "Se a ultima acao relevante ocorrer antes do fim solicitado, pare nessa semana e explique em criterio_de_encerramento. "
        "Nao preencha semanas apenas para completar 12; um plano de 3, 5 ou 8 semanas e melhor do que 12 semanas repetitivas. "
        "Conecte as tarefas semanais a indicadores operacionais reais quando possivel. "
        "Nao invente numeros. Sugira metrica base e evolucao operacional a observar. "
        "Em cada semana, indique qual arquetipo dominante do lider deve ser acionado e qual arquetipo complementar deve ser desenvolvido. "
        "Cada semana deve citar explicitamente a afirmacao, dimensao, subdimensao ou comportamento especifico envolvido. "
        "Construa uma progressao real: diagnosticar, alinhar expectativa, praticar nova conduta, observar em campo, ajustar comunicacao, consolidar evidencia e revisar aprendizado. "
        "Duas semanas consecutivas nao podem ter o mesmo tipo_de_intervencao nem o mesmo objetivo central. "
        "E proibido criar 'diagnostico aprofundado' logo depois de uma semana de diagnostico, conversa individual ou mapeamento; isso e repeticao. "
        "Depois de diagnosticar, a semana seguinte deve necessariamente converter achados em pacto comportamental, pratica observavel, experimento operacional, comunicacao estruturada, treino de speech, observacao em campo, alinhamento com superior ou revisao de evidencia. "
        "Cada semana deve preencher diferenca_objetiva_da_semana_anterior explicando o que mudou na natureza da intervencao, nao apenas no texto. "
        "Cada semana deve preencher proxima_pratica_observavel com uma conduta concreta que o lider ou a equipe executara no trabalho real. "
        "Varie o tipo_de_intervencao: nao use reuniao como solucao padrao. Inclua, quando fizer sentido, autodesenvolvimento, treino de speech, leitura orientada, observacao em campo, alinhamento com superior, feedback 1:1, comunicacao estruturada, experimento operacional e pratica emocional aplicada. "
        "Limite reuniao/feedback_1a1 a momentos realmente necessarios; depois de uma semana com conversa, a semana seguinte deve transformar o combinado em pratica observavel, comunicacao, experimento, estudo ou acompanhamento de indicador. "
        "Se a acao sugerida for conversar, informe o roteiro especifico, o speech sugerido, o que deve ser observado depois e qual mudanca concreta devera aparecer no comportamento ou indicador. "
        "Nao repita perguntas, acoes ou tarefas de semanas anteriores; se uma pergunta for parecida, reescreva com finalidade diferente. "
        "Antes de incluir uma semana, compare com as semanas ja propostas: se o leitor pudesse confundir com a semana anterior, nao inclua; substitua por uma intervencao diferente ou encerre o plano. "
        "Inclua acoes praticas detalhadas, perguntas para equipe, tarefa do lider, tarefa da equipe, indicador e resultado esperado. "
        "Use a correlacao com Daniel Goleman apenas como apoio conceitual quando ajudar a desenvolver repertorio emocional e situacional; nao cite textualmente o artigo nem diga que Goleman prova o resultado. "
        "Seja especifico e consultivo, com detalhamento suficiente para o lider perceber que o plano foi feito para aquela afirmacao. "
        "Responda somente JSON valido no formato de saida_obrigatoria.\n\n"
        f"CONTEXTO_JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def integrated_plan_schema(start_week=1, end_week=12):
    start_week = max(1, min(12, int(start_week or 1)))
    end_week = max(start_week, min(12, int(end_week or 12)))
    schema = {
        "tipo": "pdi_integrado_por_tema",
        "semanas_geradas": {
            "inicio": start_week,
            "fim": end_week,
        },
        "tema": "",
        "dimensao": "",
        "subdimensao": "",
        "afirmacoes_abrangidas": [],
        "diagnostico_integrado": {
            "sintese_executiva": "",
            "causa_comum_provavel": "",
            "como_os_gaps_se_conectam": [],
        },
        "cruzamento_arquetipos": {
            "arquetipos_dominantes_que_ajudam": [],
            "arquetipos_a_desenvolver": [],
        },
        "criterio_de_encerramento": "",
        "plano_12_semanas": [],
        "campos_obrigatorios_por_semana": {
            "semana": start_week,
            "foco_da_semana": "",
            "tipo_de_intervencao": "reuniao|pratica_diaria|autodesenvolvimento|alinhamento_com_superior|treinamento|leitura|observacao_em_campo|comunicacao|experimento_operacional|feedback_1a1",
            "afirmacoes_impactadas": [],
            "assunto_especifico_das_afirmacoes": "",
            "diferenca_objetiva_da_semana_anterior": "",
            "proxima_pratica_observavel": "",
            "objetivo": "",
            "arquetipo_dominante_a_acionar": "",
            "como_usar_arquetipo_dominante": "",
            "arquetipo_complementar_a_desenvolver": "",
            "pratica_para_desenvolver_arquetipo": "",
            "acoes_praticas": [],
            "perguntas_para_equipe": [],
            "tarefa_do_lider": [],
            "tarefa_da_equipe": [],
            "indicador": "",
            "resultado_esperado": "",
            "status": "nao_iniciado",
        },
        "resultado_esperado_do_ciclo": "",
        "observacao_para_pdi": "Plano integrado gerado a partir de multiplas afirmacoes LeaderTrack relacionadas ao mesmo tema.",
    }
    if end_week in (4, 8, 12):
        schema["revisoes_parciais_informais"] = [
            {
                "semana": end_week,
                "objetivo": "",
                "perguntas_de_revisao": [],
                "evidencias_a_observar": [],
                "decisao": "encerrar_ampliar_ou_fasear_proximo_tema" if end_week == 12 else "manter_ajustar_ou_repriorizar",
            }
        ]
    return schema


def build_integrated_plan_prompt(leader, arquetipos, group, indicadores_disponiveis, start_week=1, end_week=12):
    start_week = max(1, min(12, int(start_week or 1)))
    end_week = max(start_week, min(12, int(end_week or 12)))
    payload = {
        "lider": leader,
        "arquetipos": arquetipos,
        "grupo_tematico": group,
        "afirmacoes_abrangidas": group.get("afirmacoes") or [],
        "indicadores_operacionais_disponiveis": indicadores_disponiveis,
        "semanas_a_gerar": {
            "inicio": start_week,
            "fim": end_week,
        },
        "saida_obrigatoria": integrated_plan_schema(start_week, end_week),
    }
    return (
        f"Gere as semanas {start_week} a {end_week} de um PDI integrado LeaderTrack para um grupo de afirmacoes relacionadas ao mesmo tema de microambiente, mas inclua somente semanas com intervencao nova e util. "
        "Se a ultima acao relevante ocorrer antes do fim solicitado, pare nessa semana e explique em criterio_de_encerramento. "
        "Nao preencha semanas apenas para completar 12; um plano menor, objetivo e forte e preferivel a um plano longo e repetitivo. "
        "Se o grupo for de manutencao sem gap relevante, parabenize o lider, destaque o que aparece de melhor, preserve as praticas que explicam os bons resultados e trabalhe preventivamente os maiores gaps abaixo do corte. "
        "O objetivo e reduzir volume para o lider sem perder rastreabilidade: mencione sempre quais afirmacoes o plano cobre e quais afirmacoes cada semana impacta. "
        "Analise a causa comum do grupo, a dimensao/subdimensao, os arquetipos dominantes que podem ajudar, riscos de excesso e arquetipos a desenvolver. "
        "Em cada semana, indique qual arquetipo dominante do lider deve ser acionado, como usa-lo, qual arquetipo complementar deve ser desenvolvido e uma pratica concreta para esse desenvolvimento. "
        "Construa uma progressao real: diagnosticar, alinhar expectativa, praticar nova conduta, observar em campo, ajustar comunicacao, consolidar evidencia e revisar aprendizado. "
        "Duas semanas consecutivas nao podem ter o mesmo tipo_de_intervencao nem o mesmo objetivo central. "
        "E proibido criar 'diagnostico aprofundado' logo depois de uma semana de diagnostico, conversa individual ou mapeamento; isso e repeticao. "
        "Depois de diagnosticar, a semana seguinte deve necessariamente converter achados em pacto comportamental, pratica observavel, experimento operacional, comunicacao estruturada, treino de speech, observacao em campo, alinhamento com superior ou revisao de evidencia. "
        "Cada semana deve preencher diferenca_objetiva_da_semana_anterior explicando o que mudou na natureza da intervencao, nao apenas no texto. "
        "Cada semana deve preencher proxima_pratica_observavel com uma conduta concreta que o lider ou a equipe executara no trabalho real. "
        "Varie o tipo_de_intervencao: nao use reuniao como solucao padrao. Inclua, quando fizer sentido, autodesenvolvimento, treino de speech, leitura orientada, observacao em campo, alinhamento com superior, feedback 1:1, comunicacao estruturada, experimento operacional e pratica emocional aplicada. "
        "Limite reuniao/feedback_1a1 a momentos realmente necessarios; depois de uma semana com conversa, a semana seguinte deve transformar o combinado em pratica observavel, comunicacao, experimento, estudo ou acompanhamento de indicador. "
        "Se a acao sugerida for conversar, informe o roteiro especifico, o speech sugerido, o que deve ser observado depois e qual mudanca concreta devera aparecer no comportamento ou indicador. "
        "Cada semana deve mencionar assuntos especificos das afirmacoes envolvidas, nao apenas o nome generico da dimensao. "
        "Nao repita perguntas, acoes ou tarefas entre semanas. Se uma acao for continuidade de outra, deixe claro o avanço novo daquela semana. "
        "Antes de incluir uma semana, compare com as semanas ja propostas: se o leitor pudesse confundir com a semana anterior, nao inclua; substitua por uma intervencao diferente ou encerre o plano. "
        "Inclua acoes praticas detalhadas, perguntas para equipe, tarefa do lider, tarefa da equipe, indicador e resultado esperado. "
        "Use a correlacao com Daniel Goleman apenas como apoio conceitual quando ajudar a desenvolver repertorio emocional e situacional; nao cite textualmente o artigo nem diga que Goleman prova o resultado. "
        "Inclua revisoes informais somente quando a semana 4, 8 ou 12 estiver dentro do intervalo solicitado. "
        "Conecte as acoes a indicadores operacionais reais quando possivel, mas nao invente numeros. "
        "Mantenha profundidade consultiva suficiente para o lider perceber que o plano foi feito para aquele grupo especifico. "
        "Nao use saude emocional na devolutiva individual. Responda somente JSON valido no formato de saida_obrigatoria.\n\n"
        f"CONTEXTO_JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_empty_devolutiva(
    empresa,
    contexto,
    codrodada,
    email_lider,
    nome_lider,
    gaps,
    arquetipos,
    maximo_gaps_por_ciclo,
    todas_afirmacoes=None,
    baixa_referencia=None,
    gap_minimo=20,
    baixa_referencia_threshold=70,
    contexto_ids=None,
):
    todas_afirmacoes = todas_afirmacoes or []
    baixa_referencia = baixa_referencia or []
    contexto_ids = contexto_ids or {}
    modo_devolutiva = feedback_mode(gaps, baixa_referencia)
    agrupamentos = thematic_grouping(gaps, maximo_gaps_por_ciclo + 2)
    if not agrupamentos:
        agrupamentos = maintenance_grouping(todas_afirmacoes, baixa_referencia, maximo_gaps_por_ciclo + 2)
    return {
        "status": "preparada_para_geracao",
        "gerado_em": datetime.utcnow().isoformat(),
        "persistencia": "nao_salvo_nesta_versao_local",
        "empresa": empresa,
        "contexto": contexto,
        "contexto_ids": {
            "cliente_id": contexto_ids.get("cliente_id"),
            "holding_id": contexto_ids.get("holding_id"),
            "empresa_id": contexto_ids.get("empresa_id"),
            "filial_id": contexto_ids.get("filial_id"),
        },
        "codrodada": codrodada,
        "email_lider": email_lider,
        "nome_lider": nome_lider,
        "arquetipos": arquetipos,
        "criterios_de_leitura": {
            "gap_minimo_percentual": gap_minimo,
            "baixa_referencia_threshold_percentual": baixa_referencia_threshold,
            "baixa_referencia_regra": "pontuacao_real_e_ideal_abaixo_do_threshold",
        },
        "todas_afirmacoes_microambiente": todas_afirmacoes,
        "gaps_priorizados": gaps,
        "baixa_referencia": baixa_referencia,
        "modo_devolutiva": modo_devolutiva,
        "resumo_severidade": severity_summary(todas_afirmacoes, baixa_referencia),
        "plano_sustentacao_microambiente": build_sustainability_plan(gaps, baixa_referencia),
        "plano_desenvolvimento_arquetipos": build_archetype_development_plan(arquetipos),
        "faseamento_anual_sugerido": annual_phasing(gaps, maximo_gaps_por_ciclo),
        "agrupamentos_tematicos": agrupamentos,
        "pdis": [],
        "historico_profissional": {
            "politica": "Todo PDI gerado, aprovado, alterado, acompanhado ou encerrado deve gerar evento historico.",
            "novo_pdi_nao_apaga_historico_anterior": True,
            "linha_do_tempo_de_desenvolvimento": True,
        },
        "avaliacao_desempenho": {
            "pode_sugerir_meta_obrigatoria": True,
            "requer_validacao_consultiva": True,
            "nao_e_punicao_automatica": True,
        },
        "avisos": [
            "Saude emocional nao incluida na devolutiva individual.",
            "Revisoes parciais sao informais e nao geram nova rodada.",
            "Indicadores operacionais devem usar dados reais da empresa; nao inventar valores.",
            "Historico do PDI deve ser preservado como linha do tempo do profissional.",
            "Meta de desempenho relacionada ao PDI deve permitir validacao consultiva e contexto.",
        ],
    }


def build_history_event(empresa, contexto, email_lider, nome_lider, codrodada, gap_id, event_type, description, payload):
    return {
        "profissional_email": email_lider,
        "profissional_nome": nome_lider,
        "empresa": empresa,
        "contexto": contexto,
        "origem": "leadertrack_devolutiva",
        "codrodada": codrodada,
        "gap_id": gap_id,
        "tipo_evento": event_type,
        "descricao_evento": description,
        "dados_depois": payload,
        "registrado_por": "sistema_devolutivas_leadertrack",
        "data_evento": datetime.utcnow().isoformat(),
    }


def build_performance_goal_suggestion(email_lider, empresa, contexto, codrodada, gap_id, gap):
    return {
        "email_lider": email_lider,
        "empresa": empresa,
        "contexto": contexto,
        "codrodada_leadertrack": codrodada,
        "gap_id": gap_id,
        "status": "sugerida",
        "meta_sugerida": (
            "Cumprir e evidenciar o ciclo de PDI aprovado, realizando as acoes planejadas, "
            "registrando evolucao semanal, participando das revisoes informais e acompanhando "
            "indicadores operacionais relacionados."
        ),
        "criterios_avaliacao": [
            "Execucao das acoes semanais aprovadas.",
            "Qualidade das evidencias registradas.",
            "Participacao nas revisoes informais.",
            "Acompanhamento dos indicadores operacionais relacionados.",
            "Evolucao observavel na rotina de gestao e no microambiente.",
        ],
        "peso_sugerido": None,
        "requer_validacao_consultiva": True,
        "nao_e_punicao_automatica": True,
        "observacao": (
            "A meta deve considerar contexto, recursos disponiveis e maturidade do gap. "
            "O resultado deve apoiar carreira e desenvolvimento, nao punir automaticamente."
        ),
        "referencia_gap": {
            "questao": gap.get("questao"),
            "dimensao": gap.get("dimensao"),
            "subdimensao": gap.get("subdimensao"),
            "gap_percentual": gap.get("gap_percentual"),
        },
    }
