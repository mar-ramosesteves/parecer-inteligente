from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

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
    dados = request.json
    empresa = dados["empresa"].lower()
    codrodada = dados["codrodada"].lower()
    emailLider = dados["emailLider"].lower()

    # 1. Localizar pasta do líder
    id_empresa = buscar_id(PASTA_RAIZ, empresa)
    id_rodada = buscar_id(id_empresa, codrodada)
    id_lider = buscar_id(id_rodada, emailLider)

    # 2. Identificar arquivos relevantes
    arquivos = drive.ListFile({"q": f"'{id_lider}' in parents and trashed=false"}).GetList()

    def encontrar(nome_parcial, extensao=None):
        for arq in arquivos:
            nome = arq["title"].lower()
            if nome_parcial in nome and (extensao is None or nome.endswith(extensao)):
                return arq
        return None

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

    # 3. Ler conteúdo do JSON
    drive.CreateFile({'id': arquivo_json['id']}).GetContentFile("temp.json")
    with open("temp.json", "r", encoding="utf-8") as f:
        dados_json = json.load(f)

    # 4. Construção do prompt
    prompt = f"""
Você é um consultor organizacional com profundo conhecimento em liderança, clima organizacional e inteligência emocional, especialmente baseado nas teorias de Daniel Goleman.

Utilize os seguintes insumos:
- Resumo estatístico do Microambiente (extraído do JSON)
- Relatório analítico de Microambiente
- Relatório de Arquétipos de Gestão (auto x equipe)
- Gráficos de termômetro, waterfall e autoavaliação
- Guias técnicos fornecidos

Objetivo: Emitir um parecer completo (10 a 15 páginas) para a líder {emailLider}, incluindo:
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

Baseie-se exclusivamente nos dados analisados e nos guias fornecidos. Evite generalizações. Use linguagem acessível e profissional.
"""

    # 5. Chamada à IA
    openai.api_key = os.getenv("OPENAI_API_KEY")
    resposta = openai.ChatCompletion.create(
        model="gpt-4",
        temperature=0.6,
        messages=[{"role": "system", "content": prompt}]
    )
    parecer = resposta.choices[0].message.content.strip()

    # 6. Gerar PDF
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

    # 7. Upload no Drive
    drive_pdf = drive.CreateFile({
        "title": nome_pdf,
        "parents": [{"id": id_lider}]
    })

    media = MediaIoBaseUpload(output, mimetype="application/pdf", resumable=True)
    drive_pdf.Upload(media_body=media)

    return jsonify({"mensagem": "✅ Parecer emitido com sucesso!", "arquivo": nome_pdf})
