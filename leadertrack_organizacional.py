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
        "Esta chamada deve gerar somente o sumario executivo inicial, nao o caderno completo. "
        "O caderno completo sera gerado depois por capitulos para evitar timeout e preservar profundidade. "
        "Responda somente JSON valido, curto e completo, com exatamente estas secoes: "
        "resumo_executivo, indicadores_chave, achados_prioritarios, graficos_recomendados, "
        "plano_30_60_90, cuidados_de_leitura.\n\n"
        "Regras adicionais de saida:\n"
        "- Em cada achado, informe o dado que sustenta a leitura.\n"
        "- Quando for hipotese, escreva explicitamente que e hipotese.\n"
        "- Quando a amostra for insuficiente, nao gere achado.\n"
        "- Nao use linguagem clinica ou acusatoria.\n"
        "- Nao use saude emocional em nivel individual de lider.\n\n"
        "Formato esperado por secao:\n"
        "- resumo_executivo: objeto com sintese, leitura_para_ceo, riscos_centrais e decisoes_recomendadas.\n"
        "- indicadores_chave: ate 5 itens com nome, valor, leitura_executiva e implicacao.\n"
        "- achados_prioritarios: ate 5 itens com titulo, fato_medido, leitura, hipotese_prudente, risco e acao_recomendada.\n"
        "- graficos_recomendados: ate 5 itens com titulo, tipo e mensagem_executiva.\n"
        "- plano_30_60_90: exatamente 3 itens com horizonte, objetivo, acoes, evidencia e indicador_de_acompanhamento.\n"
        "- cuidados_de_leitura: texto curto sobre limites, amostra e uso agregado.\n\n"
        f"PACOTE_ANALITICO_JSON:\n{json.dumps(pacote, ensure_ascii=False, indent=2, default=str)}"
    )
