from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import openai
import pdfkit
import os
import io
from datetime import datetime
from google.oauth2.credentials import Credentials
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

        # Passo 1: Geração do texto com IA
        prompt = f"""
        Gere um parecer consultivo estruturado sobre o estilo de liderança e o microambiente do líder {email_lider}, com base nos dados das avaliações disponíveis para a rodada {rodada} da empresa {empresa}.
        O parecer deve conter 10 seções e apresentar uma análise clara, consultiva e profissional.
        """
        openai.api_key = os.getenv("OPENAI_API_KEY")
        resposta = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=3000
        )
        parecer_gerado = resposta.choices[0].message.content

        # Passo 2: Preencher HTML
        html = render_template("parecer.html", 
            empresa=empresa, 
            rodada=rodada, 
            emailLider=email_lider,
            parecer=parecer_gerado,
            data=datetime.now().strftime("%d/%m/%Y")
        )

        # Passo 3: Gerar PDF
        nome_pdf = f"parecer_{email_lider}_{rodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        caminho_local = f"/tmp/{nome_pdf}"
        pdfkit.from_string(html, caminho_local)

        # Passo 4: Upload para o Google Drive
        creds = Credentials.from_authorized_user_file("mycreds.txt", ["https://www.googleapis.com/auth/drive"])
        service = build("drive", "v3", credentials=creds)

        id_empresa = buscar_id(service, PASTA_RAIZ, empresa)
        id_rodada = buscar_id(service, id_empresa, rodada)
        id_lider = buscar_id(service, id_rodada, email_lider)

        file_metadata = {"name": nome_pdf, "parents": [id_lider]}
        media = MediaIoBaseUpload(open(caminho_local, "rb"), mimetype="application/pdf")
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        return jsonify({"mensagem": f"✅ Parecer salvo com sucesso no Drive: {nome_pdf}"})

    except Exception as e:
        return jsonify({"erro": str(e)}), 500
