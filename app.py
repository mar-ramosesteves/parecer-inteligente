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

app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "https://gestor.thehrkey.tech"}})

PASTA_RAIZ = "1l4kOZwed-Yc5nHU4RBTmWQz3zYAlpniS"

@app.route("/emitir-parecer-arquetipos", methods=["POST"])
def emitir_parecer_arquetipos():
    try:
        dados = request.get_json()
        empresa = dados["empresa"].lower()
        rodada = dados["codrodada"].lower()
        email_lider = dados["emailLider"].lower()

        # Autenticacao no Google Drive
        SCOPES = ['https://www.googleapis.com/auth/drive']
        json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        info = json.loads(json_str)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        service = build("drive", "v3", credentials=creds)

        # Localizar pastas
        id_empresa = buscar_id(service, PASTA_RAIZ, empresa)
        id_rodada = buscar_id(service, id_empresa, rodada)
        id_lider = buscar_id(service, id_rodada, email_lider)
        id_ia_json = buscar_id(service, id_lider, "IA_JSON")

        # Carregar JSON de graficos
        def carregar_json(nome_parcial):
            resultados = service.files().list(
                q=f"'{id_ia_json}' in parents and name contains '{nome_parcial}' and mimeType='application/json'",
                spaces='drive', fields='files(id, name)').execute()
            arquivos = resultados.get("files", [])
            if arquivos:
                conteudo = service.files().get_media(fileId=arquivos[0]['id']).execute()
                return json.loads(conteudo.decode("utf-8"))
            return None

        json_auto_vs_equipe = carregar_json("AUTO_VS_EQUIPE")

        # Ler guia de entendimento
        with open("guias_completos_unificados.txt", "r", encoding="utf-8") as f:
            texto = f.read()
        inicio = texto.find("##### INICIO ARQUETIPOS #####")
        fim = texto.find("##### FIM ARQUETIPOS #####")
        if inicio != -1 and fim != -1:
            guia = texto[inicio + len("##### INICIO ARQUETIPOS #####"):fim].strip()
        else:
            guia = "Guia de Arquétipos não encontrado."

        # Criar PDF
        nome_pdf = f"parecer_arquetipos_{email_lider}_{rodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        caminho_local = f"/tmp/{nome_pdf}"
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 10, "PARECER DE ARQUETIPOS DE GESTAO")
        pdf.multi_cell(0, 10, f"Empresa: {empresa}")
        pdf.multi_cell(0, 10, f"Rodada: {rodada}")
        pdf.multi_cell(0, 10, f"Lider: {email_lider}")
        pdf.multi_cell(0, 10, f"Data: {datetime.now().strftime('%d/%m/%Y')}")
        pdf.ln(5)
        pdf.multi_cell(0, 8, guia)

        # Inserir grafico
        if json_auto_vs_equipe:
            pdf.add_page()
            labels = list(json_auto_vs_equipe["autoavaliacao"].keys())
            auto = list(json_auto_vs_equipe["autoavaliacao"].values())
            equipe = list(json_auto_vs_equipe["mediaEquipe"].values())
            x = range(len(labels))
            plt.figure(figsize=(10, 5))
            plt.bar(x, auto, width=0.4, label="Autoavaliacao", align='center')
            plt.bar([i + 0.4 for i in x], equipe, width=0.4, label="Equipe", align='center')
            plt.xticks([i + 0.2 for i in x], labels, rotation=45)
            plt.ylim(0, 100)
            plt.title("ARQUETIPOS - AUTO VS EQUIPE")
            plt.legend()
            caminho_grafico = "/tmp/grafico_auto_vs_equipe.png"
            plt.tight_layout()
            plt.savefig(caminho_grafico)
            plt.close()
            pdf.image(caminho_grafico, w=190)

        pdf.output(caminho_local)

        # Subir para o Drive
        file_metadata = {"name": nome_pdf, "parents": [id_lider]}
        media = MediaIoBaseUpload(open(caminho_local, "rb"), mimetype="application/pdf")
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        return jsonify({"mensagem": f"Relatorio salvo com sucesso: {nome_pdf}"})

    except Exception as e:
        return jsonify({"erro": str(e)}), 500
