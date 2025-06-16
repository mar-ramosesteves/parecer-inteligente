from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from fpdf import FPDF
from datetime import datetime
import io, os, textwrap, json
from googleapiclient.http import MediaIoBaseUpload
from openai import OpenAI

# Inicialização
app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "https://gestor.thehrkey.tech"}})

# CORS Middleware
@app.after_request
def aplicar_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response

# Rota básica
@app.route("/")
def index():
    return "API no ar! 🚀"

# Rota principal
@app.route("/emitir-parecer-inteligente", methods=["POST", "OPTIONS"])
def emitir_parecer_inteligente():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response, 200

    try:
        # Entrada
        dados = request.json
        empresa = dados["empresa"].lower()
        codrodada = dados["codrodada"].lower()
        emailLider = dados["emailLider"].lower()

        # Busca de pastas
        id_empresa = buscar_id(PASTA_RAIZ, empresa)
        id_rodada = buscar_id(id_empresa, codrodada)
        id_lider = buscar_id(id_rodada, emailLider)

        # Busca JSON
        arquivos = drive.ListFile({"q": f"'{id_lider}' in parents and trashed=false"}).GetList()
        def encontrar(nome_parcial, extensao=None):
            for arq in arquivos:
                nome = arq["title"].lower()
                if nome_parcial in nome and (extensao is None or nome.endswith(extensao)):
                    return arq
            return None

        arquivo_json = encontrar("relatorio_microambiente", ".json")
        if not arquivo_json:
            return jsonify({"erro": "Arquivo JSON de microambiente não encontrado."}), 400

        drive.CreateFile({'id': arquivo_json['id']}).GetContentFile("temp.json")
        with open("temp.json", "r", encoding="utf-8") as f:
            resumo_json = json.load(f)

        # Prompt para o ChatGPT
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

        # Chamada à API OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resposta = client.chat.completions.create(
            model="gpt-4",
            temperature=0.6,
            messages=[{"role": "system", "content": prompt}]
        )
        parecer = resposta.choices[0].message.content.strip()

        # Gerar PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "RELATÓRIO DE LIDERANÇA - PROGRAMA DE ALTA PERFORMANCE", ln=True, align="C")
        pdf.set_font("Arial", "", 12)
        pdf.ln(10)
        for linha in textwrap.wrap(parecer, 100):
            pdf.cell(0, 10, linha, ln=True)

        # Salvar em memória
        output = io.BytesIO()
        pdf.output(output)
        output.seek(0)

        # Upload no Google Drive
        nome_pdf = f"parecer_inteligente_{emailLider}_{codrodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        drive_pdf = drive.CreateFile({
            "title": nome_pdf,
            "parents": [{"id": id_lider}]
        })
        drive_pdf.SetContentString(output.read().decode("latin1"))
        drive_pdf.Upload()

        return jsonify({"mensagem": f"✅ Parecer para {emailLider} gerado com sucesso!", "arquivo": nome_pdf})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"erro": str(e)}), 500


if __name__ == "__main__":
    app.run()
