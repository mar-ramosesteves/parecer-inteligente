"""Calculo de saude emocional para a previsualizacao de snapshots LeaderTrack.

Este modulo replica a cadeia do dashboard LeaderTrack: cada resposta da equipe
e localizada primeiro na matriz oficial e so depois entra na media da questao e
da categoria. Ele nao grava dados e nao chama IA.
"""

from statistics import mean


MAP_FORM_TO_MATRIX = {
    "Q01": "Q01", "Q02": "Q12", "Q03": "Q23", "Q04": "Q34", "Q05": "Q44", "Q06": "Q45",
    "Q07": "Q46", "Q08": "Q47", "Q09": "Q48", "Q10": "Q02", "Q11": "Q03", "Q12": "Q04",
    "Q13": "Q05", "Q14": "Q06", "Q15": "Q07", "Q16": "Q08", "Q17": "Q09", "Q18": "Q10",
    "Q19": "Q11", "Q20": "Q13", "Q21": "Q14", "Q22": "Q15", "Q23": "Q16", "Q24": "Q17",
    "Q25": "Q18", "Q26": "Q19", "Q27": "Q20", "Q28": "Q21", "Q29": "Q22", "Q30": "Q24",
    "Q31": "Q25", "Q32": "Q26", "Q33": "Q27", "Q34": "Q28", "Q35": "Q29", "Q36": "Q30",
    "Q37": "Q31", "Q38": "Q32", "Q39": "Q33", "Q40": "Q35", "Q41": "Q36", "Q42": "Q37",
    "Q43": "Q38", "Q44": "Q39", "Q45": "Q40", "Q46": "Q41", "Q47": "Q42", "Q48": "Q43",
}
MAP_MATRIX_TO_FORM = {value: key for key, value in MAP_FORM_TO_MATRIX.items()}
CATEGORIAS_SAUDE = (
    "Prevenção de Estresse",
    "Ambiente Psicológico Seguro",
    "Suporte Emocional",
    "Comunicação Positiva",
    "Equilíbrio Vida-Trabalho",
)


def _numero(value):
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("%", "").replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _inteiro(value):
    numero = _numero(value)
    return int(numero) if numero is not None else None


def _registros_equipe(registros):
    return [
        registro for registro in (registros or [])
        if registro.get("tipo") == "equipe" and isinstance(registro.get("respostas"), dict)
    ]


def _linhas_saude(linhas_csv):
    linhas = []
    for row in linhas_csv or []:
        tipo = str(row.get("TIPO") or "").strip().upper()
        codigo = str(row.get("COD_AFIRMACAO") or "").strip()
        categoria = str(row.get("DIMENSAO_SAUDE_EMOCIONAL") or "").strip()
        categoria = categoria.replace("Equilíbrio Vida- Trabalho", "Equilíbrio Vida-Trabalho")
        if codigo and categoria and (tipo.startswith("ARQ") or tipo.startswith("MICRO")):
            linhas.append({"tipo": "arquetipos" if tipo.startswith("ARQ") else "microambiente", "codigo": codigo, "categoria": categoria})
    return linhas


def _classificacao(score):
    if score is None:
        return "Sem dados"
    if score >= 95:
        return "Excelente"
    if score >= 85:
        return "Ótimo"
    if score >= 75:
        return "Bom"
    if score >= 65:
        return "Regular"
    return "Não adequado"


def calcular_saude_emocional_dashboard(registros_arquetipos, registros_microambiente, matriz_arquetipos, matriz_microambiente, linhas_saude):
    """Replica o bloco de score final do dashboard, sem pandas nem persistencia."""
    arq_por_chave = {str(row.get("CHAVE") or ""): row for row in (matriz_arquetipos or [])}
    micro_por_chave = {str(row.get("CHAVE") or ""): row for row in (matriz_microambiente or [])}

    # O dashboard usa a primeira ocorrencia da matriz para definir o arquetipo
    # associado a uma afirmacao de saude emocional.
    primeiro_arquetipo_por_questao = {}
    for row in matriz_arquetipos or []:
        codigo = str(row.get("COD_AFIRMACAO") or "").strip()
        arquetipo = str(row.get("ARQUETIPO") or "").strip()
        if codigo and arquetipo:
            primeiro_arquetipo_por_questao.setdefault(codigo, arquetipo)

    valores_por_categoria = {categoria: [] for categoria in CATEGORIAS_SAUDE}
    rastreio = []
    arq_equipe = _registros_equipe(registros_arquetipos)
    micro_equipe = _registros_equipe(registros_microambiente)

    for item in _linhas_saude(linhas_saude):
        categoria = item["categoria"]
        if categoria not in valores_por_categoria:
            valores_por_categoria[categoria] = []

        if item["tipo"] == "arquetipos":
            codigo = item["codigo"]
            arquetipo = primeiro_arquetipo_por_questao.get(codigo)
            percentuais = []
            soma_estrelas = 0
            for registro in arq_equipe:
                estrelas = _inteiro(registro["respostas"].get(codigo))
                if estrelas is None or not arquetipo:
                    continue
                linha = arq_por_chave.get(f"{arquetipo}{estrelas}{codigo}")
                percentual = _numero((linha or {}).get("% Tendência"))
                if percentual is None:
                    continue
                percentuais.append(percentual * 100)
                soma_estrelas += estrelas
            if not percentuais:
                continue
            percentual_medio = round(mean(percentuais), 2)
            media_estrelas = round(soma_estrelas / len(percentuais))
            linha_tendencia = arq_por_chave.get(f"{arquetipo}{media_estrelas}{codigo}") or {}
            tendencia = str(linha_tendencia.get("Tendência") or "")
            valor = max(0.0, 100.0 - percentual_medio) if "DESFAVORÁVEL" in tendencia.upper() else percentual_medio
            valores_por_categoria[categoria].append(valor)
            rastreio.append({
                "tipo": "arquetipos", "codigo": codigo, "categoria": categoria,
                "arquetipo": arquetipo, "n": len(percentuais), "valor": round(valor, 2),
            })
            continue

        codigo_matriz = item["codigo"]
        codigo_formulario = MAP_MATRIX_TO_FORM.get(codigo_matriz, codigo_matriz)
        reais, ideais = [], []
        for registro in micro_equipe:
            respostas = registro["respostas"]
            real = _inteiro(respostas.get(f"{codigo_formulario}C"))
            ideal = _inteiro(respostas.get(f"{codigo_formulario}k"))
            if real is None or ideal is None:
                continue
            linha = micro_por_chave.get(f"{codigo_matriz}_I{ideal}_R{real}")
            real_matriz = _numero((linha or {}).get("PONTUACAO_REAL"))
            ideal_matriz = _numero((linha or {}).get("PONTUACAO_IDEAL"))
            if real_matriz is None or ideal_matriz is None:
                continue
            reais.append(real_matriz)
            ideais.append(ideal_matriz)
        if not reais:
            continue
        real_medio = round(mean(reais), 2)
        ideal_medio = round(mean(ideais), 2)
        gap = round(ideal_medio - real_medio, 2)
        valor = max(0.0, 100.0 - gap)
        valores_por_categoria[categoria].append(valor)
        rastreio.append({
            "tipo": "microambiente", "codigo": codigo_matriz, "categoria": categoria,
            "n": len(reais), "real": real_medio, "ideal": ideal_medio,
            "gap": gap, "valor": round(valor, 2),
        })

    # O dashboard mantem a precisao das medias das categorias para calcular o
    # score final; o arredondamento para uma casa acontece apenas na exibicao.
    medias_categorias = {
        categoria: mean(valores) if valores else 0.0
        for categoria, valores in valores_por_categoria.items()
    }
    categorias = {
        categoria: round(valor, 1)
        for categoria, valor in medias_categorias.items()
    }
    validas = [valor for valor in medias_categorias.values() if valor > 0]
    score = round(mean(validas), 1) if validas else None
    return {
        "score_final": score,
        "classificacao": _classificacao(score),
        "dimensoes": categorias,
        "quantidade_afirmacoes_calculadas": len(rastreio),
        "respondentes_arquetipos": len(arq_equipe),
        "respondentes_microambiente": len(micro_equipe),
        "rastreio_afirmacoes": rastreio,
        "versao_regra": "dashboard-leadertrack-saude-emocional-v1",
    }
