import json


ORGANIZATIONAL_REQUIRED_KEYS = {
    "tipo",
    "governanca",
    "amostra",
    "saude_emocional",
    "microambiente",
    "arquetipos",
    "achados_relevantes",
}


def validate_organizational_package(pacote):
    if not isinstance(pacote, dict):
        return False, "pacote_analitico deve ser um objeto JSON."

    missing = sorted(ORGANIZATIONAL_REQUIRED_KEYS - set(pacote.keys()))
    if missing:
        return False, f"pacote_analitico incompleto. Campos ausentes: {', '.join(missing)}."

    if pacote.get("tipo") != "devolutiva_organizacional_leadertrack":
        return False, "tipo do pacote_analitico invalido para devolutiva organizacional LeaderTrack."

    governanca = pacote.get("governanca") or {}
    if governanca.get("saude_emocional_entrega_individual") is not False:
        return False, "governanca invalida: saude emocional precisa estar bloqueada para entrega individual."

    amostra = pacote.get("amostra") or {}
    try:
        respondentes = int(amostra.get("respondentes") or 0)
    except Exception:
        respondentes = 0
    if respondentes <= 0:
        return False, "pacote_analitico sem respondentes suficientes para analise."

    return True, None


def build_organizational_feedback_prompt(pacote):
    return (
        "Voce e o Assistente Inteligente LeaderTrack em modo de devolutiva organizacional "
        "para RH, CEO e diretoria. Use exclusivamente o pacote analitico JSON recebido. "
        "Nao invente percentuais, causas, diagnosticos, nomes, historico ou cruzamentos. "
        "Se um dado ou cruzamento nao estiver no pacote, diga que nao ha informacao suficiente "
        "ou omita o ponto. Saude emocional pode ser analisada somente em nivel organizacional "
        "e agregado; nunca escreva como devolutiva individual para lider. "
        "Nao faca diagnostico clinico, nao atribua culpa a lideres e nao exponha grupos pequenos. "
        "Use Daniel Goleman/HBR apenas como apoio conceitual de repertorio situacional, "
        "sem citacao textual, sem dizer que Goleman prova o resultado e sem substituir o modelo LeaderTrack. "
        "Separe fato medido, hipotese prudente e recomendacao pratica. "
        "A devolutiva deve ter linguagem de conselho executivo: clara, direta, profunda e acionavel. "
        "Pense que quem recebera e CEO, proprietario, diretoria ou RH estrategico. "
        "Inclua sugestoes de graficos usando apenas dados presentes no pacote. "
        "Organize a resposta como um caderno executivo corporativo em JSON, mesmo que resumido nesta primeira chamada. "
        "Responda somente JSON valido com as secoes: capa_executiva, resumo_executivo, leitura_do_contexto, "
        "indicadores_chave, termometro_organizacional, saude_emocional_organizacional, microambiente, "
        "arquetipos_de_lideranca, cruzamentos_relevantes, achados_prioritarios, riscos_organizacionais, "
        "fortalezas_organizacionais, graficos_recomendados, plano_30_60_90, plano_4_semanas_por_frente, "
        "perguntas_para_comite_executivo, recomendacoes_para_rh, cuidados_de_leitura.\n\n"
        "Regras adicionais de saida:\n"
        "- Em cada achado, informe o dado que sustenta a leitura.\n"
        "- Quando for hipotese, escreva explicitamente que e hipotese.\n"
        "- Quando a amostra for insuficiente, nao gere achado.\n"
        "- Nao use linguagem clinica ou acusatoria.\n"
        "- Nao use saude emocional em nivel individual de lider.\n\n"
        "Formato esperado por secao:\n"
        "- resumo_executivo: objeto com sintese, leitura_para_ceo, riscos_centrais e decisoes_recomendadas.\n"
        "- indicadores_chave: lista ou objeto com nome, valor, leitura_executiva e implicacao.\n"
        "- achados_prioritarios: lista com titulo, fato_medido, leitura, hipotese_prudente, risco, acao_recomendada e nivel_prioridade.\n"
        "- cruzamentos_relevantes: lista apenas com recortes existentes no pacote e amostra suficiente.\n"
        "- graficos_recomendados: lista com titulo, tipo, dados_necessarios e mensagem_executiva.\n"
        "- plano_4_semanas_por_frente: lista de frentes priorizadas, cada uma com semana_1, semana_2, semana_3 e semana_4.\n"
        "- plano_30_60_90: lista com horizonte, objetivo, acoes, responsavel_sugerido, evidencia e indicador_de_acompanhamento.\n\n"
        f"PACOTE_ANALITICO_JSON:\n{json.dumps(pacote, ensure_ascii=False, indent=2, default=str)}"
    )
