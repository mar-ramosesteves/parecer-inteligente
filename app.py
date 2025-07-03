from flask import Flask, request, jsonify
from flask_cors import CORS
import os
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

        SCOPES = ['https://www.googleapis.com/auth/drive']
        json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        info = json.loads(json_str)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        service = build("drive", "v3", credentials=creds)

        id_empresa = buscar_id(service, PASTA_RAIZ, empresa)
        id_rodada = buscar_id(service, id_empresa, rodada)
        id_lider = buscar_id(service, id_rodada, email_lider)
        id_ia_json = buscar_id(service, id_lider, "IA_JSON")

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
        json_analitico = carregar_json("RELATORIO_ANALITICO_ARQUETIPOS")

        with open("guias_completos_unificados.txt", "r", encoding="utf-8") as f:
            texto = f.read()
        inicio = texto.find("INÍCIO - ARQUÉTIPOS DE GESTÃO")
        fim = texto.find("FIM - ARQUÉTIPOS DE GESTÃO")
        guia = texto[inicio + len("INÍCIO - ARQUÉTIPOS DE GESTÃO"):fim].strip() if inicio != -1 and fim != -1 else "Guia de Arquétipos não encontrado."

        nome_pdf = f"parecer_arquetipos_{email_lider}_{rodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        caminho_local = f"/tmp/{nome_pdf}"
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 10, f"PARECER DE ARQUÉTIPOS DE GESTÃO\nEmpresa: {empresa}\nRodada: {rodada}\nLíder: {email_lider}\nData: {datetime.now().strftime('%d/%m/%Y')}\n\n")
        pdf.set_font("Arial", size=11)
        for paragrafo in guia.split("\n\n"):
            pdf.multi_cell(0, 8, paragrafo.strip())
            pdf.ln()

        if json_auto_vs_equipe:
            pdf.add_page()
            plt.figure(figsize=(10, 5))
            labels = list(json_auto_vs_equipe["autoavaliacao"].keys())
            auto = list(json_auto_vs_equipe["autoavaliacao"].values())
            equipe = list(json_auto_vs_equipe["mediaEquipe"].values())
            x = range(len(labels))
            plt.bar(x, auto, width=0.4, label="Autoavaliação", align='center')
            plt.bar([i + 0.4 for i in x], equipe, width=0.4, label="Equipe", align='center')
            plt.xticks([i + 0.2 for i in x], labels, rotation=45)
            plt.ylim(0, 100)
            plt.title("ARQUÉTIPOS AUTO VS EQUIPE")
            plt.legend()
            caminho_grafico1 = "/tmp/grafico1.png"
            plt.tight_layout()
            plt.savefig(caminho_grafico1)
            plt.close()
            pdf.image(caminho_grafico1, w=190)

        if json_analitico and "analise" in json_analitico:
            try:
                pdf.add_page()
                labels = [item.get("arquetipo", f"Arquetipo {i+1}") for i, item in enumerate(json_analitico["analise"])]
                valores = [item.get("pontuacao", 0) for item in json_analitico["analise"]]
                plt.figure(figsize=(10, 5))
                plt.bar(labels, valores, color='gray')
                plt.ylim(0, 100)
                plt.title("RELATÓRIO ANALÍTICO DE ARQUÉTIPOS")
                plt.xticks(rotation=45)
                caminho_grafico2 = "/tmp/grafico2.png"
                plt.tight_layout()
                plt.savefig(caminho_grafico2)
                plt.close()
                pdf.image(caminho_grafico2, w=190)
            except Exception as erro:
                print(f"Erro ao gerar gráfico analítico: {erro}")

        pdf.output(caminho_local)
        file_metadata = {"name": nome_pdf, "parents": [id_lider]}
        media = MediaIoBaseUpload(open(caminho_local, "rb"), mimetype="application/pdf")
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        return jsonify({"mensagem": f"✅ Parecer com gráficos salvo com sucesso no Drive: {nome_pdf}"})

    except Exception as e:
        return jsonify({"erro": str(e)}), 500
