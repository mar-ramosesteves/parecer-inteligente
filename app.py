from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins=["https://gestor.thehrkey.tech"])

@app.route("/")
def index():
    return "API no ar! 🚀"

if __name__ == "__main__":
    app.run()

from flask import Flask, request, jsonify
from fpdf import FPDF
from datetime import datetime
import io, os, textwrap, json
from googleapiclient.http import MediaIoBaseUpload
import openai

@app.route("/emitir-parecer-inteligente", methods=["POST"])
def emitir_parecer_inteligente():
    import os
    import io
    import json
    import textwrap
    from fpdf import FPDF
    from datetime import datetime
    from googleapiclient.http import MediaIoBaseUpload
    from openai import OpenAI

    dados = request.json
    empresa = dados["empresa"].lower()
    codrodada = dados["codrodada"].lower()
    emailLider = dados["emailLider"].lower()

    # Localizar pastas no Google Drive
    id_empresa = buscar_id(PASTA_RAIZ, empresa)
    id_rodada = buscar_id(id_empresa, codrodada)
    id_lider = buscar_id(id_rodada, emailLider)

    # Listar arquivos na pasta do líder
    arquivos = drive.ListFile({"q": f"'{id_lider}' in parents and trashed=false"}).GetList()

    def encontrar(nome_parcial, extensao=None):
        for arq in arquivos:
            nome = arq["title"].lower()
            if nome_parcial in nome and (extensao is None or nome.endswith(extensao)):
                return arq
        return None

    # Localizar arquivos-chave
    arquivo_json = encontrar("relatorio_microambiente", ".json")
    guia_arquetipos = encontrar("guia de entendimento - arquétipos", ".pdf")
    guia_micro = encontrar("guia de entendimento - micro ambiente", ".pdf")
    relatorio_arquetipos = encontrar("relatorio_analitico_arquetipos", ".pdf")
    relatorio_microambiente = encontrar("relatorio_analitico_microambiente", ".pdf")
    grafico_waterfall = encontrar("waterfall", ".pdf")
    grafico_termometro = encontrar("termometro", ".pdf")
    logo = encontrar("logo", ".jpg")

    if not arquivo_json:
        return jsonify({"erro": "Arquivo JSON de microambiente não encontrado."}), 400

    # Baixar conteúdo do JSON
    conteudo_json = io.BytesIO()
    drive.CreateFile({'id': arquivo_json['id']}).GetContentFile("temp.json")
    with open("temp.json", "r", encoding="utf-8") as f:
        resumo_json = json.load(f)

    # Montar o prompt
    prompt = f"""
Você é um consultor organizacional com profundo conhecimento em liderança, clima organizacional e inteligência emocional, especialmente com base nas teorias de Daniel Goleman.

Utilize os seguintes insumos:
- Resumo estatístico do Microambiente (JSON): {json.dumps(resumo_json, ensure_ascii=False)}
- Relatório analítico de Microambiente
- Relatório de Arquétipos de Gestão (auto x equipe)
- Gráficos de termômetro, waterfall e autoavaliação
- Guias técnicos fornecidos

Objetivo: Emitir um parecer completo e detalhado (10 a 15 páginas) para a líder {emailLider}, incluindo:
1. Introdução e objetivo do relatório
2. Leitura do Clima da Equipe (com base nos gráficos)
3. Quantidade e tipo de GAPs
4. Classificação do microambiente
5. Cruzamento com estilos de liderança (Arquétipos)
6. Potenciais causas dos problemas
7. Recomendações por estilo de atuação
8. Sugerir 3 planos de ação
9. Conclusão com chamada à ação
10. Tom consultivo e encorajador

Evite generalizações. Seja objetivo e profundo. Use linguagem clara, profissional e acessível.
"""

    # Chamar a API da OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resposta = client.chat.completions.create(
        model="gpt-4",
        temperature=0.6,
        messages=[{"role": "system", "content": prompt}]
    )
    parecer = resposta.choices[0].message.content.strip()

    # Gerar PDF simples com FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "RELATÓRIO DE LIDERANÇA - PROGRAMA DE ALTA PERFORMANCE", ln=True, align="C")
    pdf.set_font("Arial", "", 12)
    pdf.ln(10)

    for linha in textwrap.wrap(parecer, 100):
        pdf.cell(0, 10, linha, ln=True)

    output = io.BytesIO()
    pdf.output(output)
    output.seek(0)

    nome_pdf = f"parecer_inteligente_{emailLider}_{codrodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    drive_pdf = drive.CreateFile({
        "title": nome_pdf,
        "parents": [{"id": id_lider}]
    })
    drive_pdf.SetContentString(output.read().decode("latin1"))
    drive_pdf.Upload()

    return jsonify({"mensagem": "✅ Parecer emitido com sucesso!", "arquivo": nome_pdf})
