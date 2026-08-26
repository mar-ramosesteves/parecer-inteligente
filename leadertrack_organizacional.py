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
        "A devolutiva deve ser premium, executiva e visual, mas fiel aos dados. "
        "Inclua sugestoes de graficos usando apenas dados presentes no pacote. "
        "Responda somente JSON valido com as secoes: resumo_executivo, indicadores_chave, "
        "saude_emocional_organizacional, microambiente, arquetipos, achados_prioritarios, "
        "graficos_recomendados, plano_30_60_90, cuidados_de_leitura.\n\n"
        "Regras adicionais de saida:\n"
        "- Em cada achado, informe o dado que sustenta a leitura.\n"
        "- Quando for hipotese, escreva explicitamente que e hipotese.\n"
        "- Quando a amostra for insuficiente, nao gere achado.\n"
        "- Nao use linguagem clinica ou acusatoria.\n"
        "- Nao use saude emocional em nivel individual de lider.\n\n"
        f"PACOTE_ANALITICO_JSON:\n{json.dumps(pacote, ensure_ascii=False, indent=2, default=str)}"
    )
