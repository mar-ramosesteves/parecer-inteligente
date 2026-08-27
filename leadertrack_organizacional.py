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
        "A linguagem deve refletir conceitos de inteligencia emocional aplicados a cultura: autoconsciencia "
        "organizacional, autorregulacao coletiva, empatia institucional, qualidade das conversas, seguranca "
        "psicologica percebida, clima emocional, repertorio adaptativo de lideranca e capacidade de reparacao. "
        "Use esses conceitos para enriquecer a leitura, sempre ancorado nos dados LeaderTrack. "
        "Separe fato medido, hipotese prudente e recomendacao pratica. "
        "A devolutiva deve ter linguagem de conselho executivo: clara, direta, profunda e acionavel. "
        "Pense que quem recebera e CEO, proprietario, diretoria ou RH estrategico. "
        "Inclua sugestoes de graficos usando apenas dados presentes no pacote. "
        "Nao gere plano de acao formal nesta chamada. Gere sugestoes executivas, perguntas de governanca "
        "e caminhos de investigacao, mas sem transformar o parecer em PDI ou cronograma operacional. "
        "Use com prioridade o campo analise_profunda quando ele existir: microambiente por geracao, "
        "sexo, etnia, departamento/area, interseccoes, afirmacoes impactantes e participacao. "
        "Compare cada recorte com a referencia_contexto, usando delta_gap_vs_contexto ou "
        "delta_gap_medio_vs_contexto quando disponivel. A pergunta central e: este grupo, empresa, "
        "filial, area ou combinacao percebe o microambiente melhor, pior ou diferente da media "
        "da selecao principal? "
        "Para comparativo de empresas da mesma holding, destaque dispersao cultural, empresas mais "
        "tensionadas e empresas mais saudaveis somente quando houver amostra minima. "
        "Responda somente JSON valido, objetivo e denso, com exatamente estas secoes: "
        "resumo_executivo, leitura_por_recortes, cruzamentos_criticos, afirmacoes_impactantes, "
        "participacao_e_aderencia, graficos_recomendados, hipoteses_e_sugestoes, cuidados_de_leitura.\n\n"
        "Regras adicionais de saida:\n"
        "- Em cada achado, informe o dado que sustenta a leitura.\n"
        "- Quando for hipotese, escreva explicitamente que e hipotese.\n"
        "- Quando a amostra for insuficiente, nao gere achado.\n"
        "- Quando nao houver denominador de tokens enviados, nao chame percentual_da_amostra de taxa de resposta.\n"
        "- Nao cite e-mail, nome ou identificador de lider em cruzamentos criticos ou achados interpretativos.\n"
        "- Se lider aparecer no pacote, use apenas como volume anonimizado de aderencia, sem atribuir causa.\n"
        "- Nao use linguagem clinica ou acusatoria.\n"
        "- Nao use saude emocional em nivel individual de lider.\n\n"
        "Formato esperado por secao:\n"
        "- resumo_executivo: objeto com sintese, tensao_central, sinais_fortes, pontos_de_atencao e leitura_para_ceo.\n"
        "- leitura_por_recortes: lista com geracao, sexo, etnia, area/departamento quando houver dados; incluir n, maior gap e leitura.\n"
        "- cruzamentos_criticos: lista de interseccoes relevantes, como sexo+etnia, geracao+sexo, departamento+etnia; incluir n, dado e implicacao.\n"
        "- afirmacoes_impactantes: lista das afirmacoes com maior gap; incluir codigo, afirmacao, dimensao, real, ideal, gap e interpretacao.\n"
        "- participacao_e_aderencia: leitura sobre areas/lideres com maior volume e percentual relativo; deixar claro se nao ha denominador de tokens enviados.\n"
        "- graficos_recomendados: lista com titulo, tipo, eixo/recorte e mensagem_executiva.\n"
        "- hipoteses_e_sugestoes: lista com hipotese_prudente, evidencias_para_confirmar e sugestao_executiva.\n"
        "- cuidados_de_leitura: texto curto sobre limites, amostra e uso agregado.\n\n"
        f"PACOTE_ANALITICO_JSON:\n{json.dumps(pacote, ensure_ascii=False, indent=2, default=str)}"
    )
