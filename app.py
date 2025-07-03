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
import tempfile

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

        # Autenticando no Google Drive
        SCOPES = ['https://www.googleapis.com/auth/drive']
        json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        info = json.loads(json_str)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        service = build("drive", "v3", credentials=creds)

        id_empresa = buscar_id(service, PASTA_RAIZ, empresa)
        id_rodada = buscar_id(service, id_empresa, rodada)
        id_lider = buscar_id(service, id_rodada, email_lider)
        id_ia_json = buscar_id(service, id_lider, "IA_JSON")

        # Função para carregar JSON do gráfico
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

        # Carrega conteúdo do guia
        with open("guias_completos_unificados.txt", "r", encoding="utf-8") as f:
            texto = f.read()

        inicio = texto.find("##### INÍCIO ARQUÉTIPOS #####")
        fim = texto.find("##### FIM ARQUÉTIPOS #####")
        if inicio != -1 and fim != -1:
            guia = texto[inicio + len("##### INÍCIO ARQUÉTIPOS #####"):fim].strip()
        else:
            guia = "Guia de Arquétipos não encontrado."

        # Cria PDF
        nome_pdf = f"parecer_arquetipos_{email_lider}_{rodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        caminho_local = f"/tmp/{nome_pdf}"
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 10, f"PARECER DE ARQUÉTIPOS DE GESTÃO\nEmpresa: {empresa}\nRodada: {rodada}\nLíder: {email_lider}\nData: {datetime.now().strftime('%d/%m/%Y')}\n\n")

        # Divide texto do guia em partes e insere gráfico onde for a frase-âncora
        linhas = guia.splitlines()
        for linha in linhas:
            pdf.multi_cell(0, 10, linha)
            if "Abaixo, o resultado da análise de Arquétipos relativa ao modo como voce lidera em sua visão" in linha and json_auto_vs_equipe:
                # Gera gráfico
                labels = list(json_auto_vs_equipe["autoavaliacao"].keys())
                auto = list(json_auto_vs_equipe["autoavaliacao"].values())
                equipe = list(json_auto_vs_equipe["mediaEquipe"].values())
                x = range(len(labels))

                plt.figure(figsize=(10, 5))
                plt.bar(x, auto, width=0.4, label="Autoavaliação", align='center')
                plt.bar([i + 0.4 for i in x], equipe, width=0.4, label="Equipe", align='center')
                plt.xticks([i + 0.2 for i in x], labels, rotation=45)
                plt.ylim(0, 100)

                # Título e subtítulo
                titulo = "ARQUÉTIPOS AUTO VS EQUIPE"
                subtitulo = f"{empresa} / {rodada} / {email_lider} / {datetime.now().strftime('%m/%Y')}"
                plt.title(f"{titulo}\n{subtitulo}")

                # Linhas de corte
                plt.axhline(50, color='gray', linestyle='--', linewidth=1)
                plt.axhline(60, color='black', linestyle='--', linewidth=1)

                # Rótulos
                for i in x:
                    plt.text(i, auto[i] + 1, f"{auto[i]}%", ha='center', fontsize=8)
                    plt.text(i + 0.4, equipe[i] + 1, f"{equipe[i]}%", ha='center', fontsize=8)

                plt.legend()
                plt.tight_layout()
                caminho_img = "/tmp/grafico_auto_vs_equipe.png"
                plt.savefig(caminho_img)
                plt.close()

                pdf.image(caminho_img, w=190)
                pdf.ln(10)

        # Salva e envia PDF para o Drive
        pdf.output(caminho_local)
        file_metadata = {"name": nome_pdf, "parents": [id_lider]}
        media = MediaIoBaseUpload(open(caminho_local, "rb"), mimetype="application/pdf")
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        return jsonify({"mensagem": f"✅ Parecer com gráfico salvo no Drive: {nome_pdf}"})

    except Exception as e:
        return jsonify({"erro": str(e)}), 500
