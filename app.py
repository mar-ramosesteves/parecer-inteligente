from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import openai
import json
from fpdf import FPDF
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from busca_arquivos_drive import buscar_id
import matplotlib.pyplot as plt
import io

app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "https://gestor.thehrkey.tech"}})

PASTA_RAIZ = "1l4kOZwed-Yc5nHU4RBTmWQz3zYAlpniS"

@app.route("/")
def index():
    return "API no ar! ✅"

@app.route("/emitir-parecer-arquetipos", methods=["POST"])
def emitir_parecer_arquetipos():
    try:
        dados = request.get_json()
        empresa = dados["empresa"].lower()
        rodada = dados["codrodada"].lower()
        email_lider = dados["emailLider"].lower()

        # Autenticação Google Drive
        SCOPES = ['https://www.googleapis.com/auth/drive']
        json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        info = json.loads(json_str)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        service = build("drive", "v3", credentials=creds)

        # Caminho da pasta IA_JSON
        id_empresa = buscar_id(service, PASTA_RAIZ, empresa)
        id_rodada = buscar_id(service, id_empresa, rodada)
        id_lider = buscar_id(service, id_rodada, email_lider)
        id_ia_json = buscar_id(service, id_lider, "IA_JSON")

        # Buscar JSONs de arquétipos
        resultados = service.files().list(
            q=f"'{id_ia_json}' in parents and name contains 'arquetipos' and mimeType='application/json'",
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        arquivos_json = resultados.get("files", [])
        jsons_arquetipos = []
        for arq in arquivos_json:
            conteudo = service.files().get_media(fileId=arq["id"]).execute()
            jsons_arquetipos.append(json.loads(conteudo.decode("utf-8")))

        # Extrair conteúdo do guia apenas de arquétipos
        with open("guias_completos_unificados.txt", "r", encoding="utf-8") as f:
            guia_completo = f.read()
        inicio = guia_completo.lower().find("=== arquétipos de gestão ===")
        fim = guia_completo.lower().find("=== microambiente de equipes ===")
        guia_arquetipos = guia_completo[inicio:fim].strip() if inicio != -1 and fim != -1 else "❌ Guia de Arquétipos não encontrado."

        # Criar PDF
        nome_pdf = f"parecer_arquetipos_{email_lider}_{rodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        caminho_local = f"/tmp/{nome_pdf}"
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_font("Arial", size=12)

        # Capa
        pdf.multi_cell(0, 10, f"PARECER DE ARQUÉTIPOS DE GESTÃO\nEmpresa: {empresa}\nRodada: {rodada}\nLíder: {email_lider}\nData: {datetime.now().strftime('%d/%m/%Y')}\n\n", align="L")

        # Conteúdo do guia
        for linha in guia_arquetipos.split("\n"):
            pdf.multi_cell(0, 8, linha)

        # Gráficos
        for json_grafico in jsons_arquetipos:
            titulo = json_grafico.get("titulo", "Gráfico sem título")
            dados = json_grafico.get("dados", {})
            if not isinstance(dados, dict) or not dados:
                continue

            categorias = list(dados.keys())
            valores = list(dados.values())

            fig, ax = plt.subplots(figsize=(6, 3))
            ax.barh(categorias, valores)
            ax.set_title(titulo)
            ax.invert_yaxis()
            buf = io.BytesIO()
            plt.tight_layout()
            plt.savefig(buf, format="png")
            plt.close(fig)
            buf.seek(0)

            # Inserir imagem no PDF
            pdf.add_page()
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 10, titulo, ln=True)
            pdf.image(buf, x=10, y=30, w=180)
            buf.close()

        pdf.output(caminho_local)

        # Upload no Google Drive
        file_metadata = {"name": nome_pdf, "parents": [id_lider]}
        media = MediaIoBaseUpload(open(caminho_local, "rb"), mimetype="application/pdf")
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        return jsonify({"mensagem": f"✅ Parecer de Arquétipos salvo no Drive: {nome_pdf}"})

    except Exception as e:
        print(f"❌ ERRO: {str(e)}")
        return jsonify({"erro": str(e)}), 500
