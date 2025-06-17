from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import openai
import os
from datetime import datetime
from fpdf import FPDF
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from busca_arquivos_drive import buscar_id
import json

app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "https://gestor.thehrkey.tech"}})

@app.after_request
def aplicar_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


PASTA_RAIZ = "1l4kOZwed-Yc5nHU4RBTmWQz3zYAlpniS"

@app.route("/")
def index():
    return "API no ar! ✅"

@app.route("/emitir-parecer-inteligente", methods=["POST", "OPTIONS"])
def emitir_parecer():
    if request.method == "OPTIONS":
        return '', 204

    try:
        dados = request.get_json()
        empresa = dados["empresa"].lower()
        rodada = dados["codrodada"].lower()
        email_lider = dados["emailLider"].lower()

        # Passo 1: Geração do texto com IA estruturado em 15 seções
        prompt = f"""
Você é um consultor sênior em liderança e cultura organizacional.

Com base nos dados da empresa {empresa}, rodada {rodada} e líder {email_lider}, elabore um parecer profissional com 15 seções:

1. Introdução ao diagnóstico
2. Visão geral cruzada entre arquétipos e microambiente
3. Análise completa do arquétipo dominante
4. Análise do arquétipo secundário
5. Estilos ausentes e riscos associados
6. Questões-chave por arquétipo
7. Perfil geral do microambiente
8. Dimensão por dimensão
9. Subdimensões com maior GAP
10. Questões críticas de microambiente
11. Comparativo entre estilo do líder e ambiente percebido
12. Correlações entre estilo de gestão e GAPs
13. Recomendações para desenvolver microambiente
14. Recomendações para desenvolver estilos de gestão
15. Conclusão e próximos passos

Responda no formato JSON com uma lista chamada 'secoes'. Cada item deve ter "titulo" e "texto".
"""

        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resposta = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )

        parecer_gerado = resposta.choices[0].message.content
        parecer = eval(parecer_gerado)  # Garantido por estrutura padronizada

        # Passo 2: Preencher HTML
        html = render_template("parecer.html",
                               empresa=empresa,
                               rodada=rodada,
                               emailLider=email_lider,
                               data=datetime.now().strftime("%d/%m/%Y"),
                               parecer=parecer)

        # Passo 3: Criar PDF
        nome_pdf = f"parecer_{email_lider}_{rodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        caminho_local = f"/tmp/{nome_pdf}"

        from xhtml2pdf import pisa
        with open(caminho_local, "w+b") as f:
            pisa.CreatePDF(io.StringIO(html), dest=f)

        # Passo 4: Upload no Google Drive
        SCOPES = ['https://www.googleapis.com/auth/drive']
        json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        info = json.loads(json_str)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        service = build("drive", "v3", credentials=creds)

        id_empresa = buscar_id(service, PASTA_RAIZ, empresa)
        id_rodada = buscar_id(service, id_empresa, rodada)
        id_lider = buscar_id(service, id_rodada, email_lider)

        file_metadata = {"name": nome_pdf, "parents": [id_lider]}
        media = MediaIoBaseUpload(open(caminho_local, "rb"), mimetype="application/pdf")
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        return jsonify({"mensagem": f"✅ Parecer salvo com sucesso no Drive: {nome_pdf}"})

    except Exception as e:
        print(f"ERRO: {str(e)}")
        return jsonify({"erro": str(e)}), 500
