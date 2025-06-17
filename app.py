from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import openai
import os
from fpdf import FPDF
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from busca_arquivos_drive import buscar_id

app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "https://gestor.thehrkey.tech"}})

PASTA_RAIZ = "1l4kOZwed-Yc5nHU4RBTmWQz3zYAlpniS"

@app.route("/")
def index():
    return "API no ar! ✅"

@app.route("/emitir-parecer-inteligente", methods=["POST"])
def emitir_parecer():
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

        Responda no formato JSON com uma lista chamada 'secoes'. Cada item deve conter "titulo" e "texto".
        """

        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        resposta = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )

        conteudo_json = resposta.choices[0].message.content.strip()
        parecer = eval(conteudo_json)  # assume estrutura correta

        

        # Passo 2: Criar PDF com FPDF (mais compatível com Render)
        nome_pdf = f"parecer_{email_lider}_{rodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        caminho_local = f"/tmp/{nome_pdf}"
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 10, f"PARECER INTELIGENTE\nEmpresa: {empresa}\nRodada: {rodada}\nLíder: {email_lider}\nData: {datetime.now().strftime('%d/%m/%Y')}\n\n")
        for paragrafo in parecer_gerado.split("\n"):
            pdf.multi_cell(0, 10, paragrafo)
        pdf.output(caminho_local)

        # Passo 3: Autenticar no Google Drive com conta de serviço
        import json

        SCOPES = ['https://www.googleapis.com/auth/drive']
        json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        info = json.loads(json_str)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

        service = build("drive", "v3", credentials=creds)

        # Passo 4: Criar estrutura de pastas e subir PDF
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


@app.after_request
def aplicar_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response

