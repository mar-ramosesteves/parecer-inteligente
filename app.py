from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
from fpdf import FPDF
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from busca_arquivos_drive import buscar_id
import json
import matplotlib.pyplot as plt
import tempfile

app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "https://gestor.thehrkey.tech"}})

PASTA_RAIZ = "1l4kOZwed-Yc5nHU4RBTmWQz3zYAlpniS"

def remover_caracteres_invalidos(texto):
    return ''.join(c for c in texto if ord(c) < 256)

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

        # Autenticar Google Drive
        SCOPES = ['https://www.googleapis.com/auth/drive']
        json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        info = json.loads(json_str)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        service = build("drive", "v3", credentials=creds)

        # Localizar pasta do líder
        id_empresa = buscar_id(service, PASTA_RAIZ, empresa)
        id_rodada = buscar_id(service, id_empresa, rodada)
        id_lider = buscar_id(service, id_rodada, email_lider)
        id_ia_json = buscar_id(service, id_lider, "IA_JSON")

        # Coletar JSONs de arquétipos
        resultados = service.files().list(
            q=f"'{id_ia_json}' in parents and name contains 'arquetipos' and mimeType='application/json'",
            spaces='drive',
            fields='files(id, name)'
        ).execute()

        arquivos_json = resultados.get("files", [])
        dados_json = []
        for arq in arquivos_json:
            conteudo = service.files().get_media(fileId=arq["id"]).execute()
            dados_json.append(json.loads(conteudo.decode("utf-8")))

        # Extrair resumo de dados para IA
        resumo_dados = ""
        for item in dados_json:
            if isinstance(item, dict):
                titulo = item.get("titulo", "Sem título")
                resumo_dados += f"\n\n🔹 {titulo}\n"
                for chave, valor in item.items():
                    if chave != "titulo":
                        if isinstance(valor, dict):
                            for subchave, subvalor in valor.items():
                                resumo_dados += f"- {subchave}: {subvalor}\n"
                        elif isinstance(valor, list):
                            for i, elemento in enumerate(valor, start=1):
                                resumo_dados += f"{i}. {elemento}\n"
                        else:
                            resumo_dados += f"- {chave}: {valor}\n"

        # Extrair apenas o guia de Arquétipos
        with open("guias_completos_unificados.txt", "r", encoding="utf-8") as f:
            texto = f.read()
        if "INÍCIO - ARQUÉTIPOS DE GESTÃO" in texto and "FIM - ARQUÉTIPOS DE GESTÃO" in texto:
            guia_arquetipos = texto.split("INÍCIO - ARQUÉTIPOS DE GESTÃO")[1].split("FIM - ARQUÉTIPOS DE GESTÃO")[0].strip()
        else:
            guia_arquetipos = "❌ Guia de Arquétipos não encontrado no arquivo."

        # Montar nome e PDF
        nome_pdf = f"parecer_arquetipos_{email_lider}_{rodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        caminho_local = f"/tmp/{nome_pdf}"
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)

        # Cabeçalho
        cabecalho = f"""
PARECER DE ARQUÉTIPOS DE GESTÃO
Empresa: {empresa}
Rodada: {rodada}
Líder: {email_lider}
Data: {datetime.now().strftime('%d/%m/%Y')}

"""
        pdf.multi_cell(0, 10, remover_caracteres_invalidos(cabecalho), align="L")

        # Conteúdo do guia
        for linha in guia_arquetipos.split("\n"):
            pdf.multi_cell(0, 8, remover_caracteres_invalidos(linha))

        # Inserir gráficos a partir dos JSONs
        for item in dados_json:
            titulo = item.get("titulo", "Sem título")
            dados = item.get("dados", {})
            if isinstance(dados, dict) and all(isinstance(v, (int, float)) for v in dados.values()):
                fig, ax = plt.subplots()
                ax.bar(dados.keys(), dados.values())
                ax.set_title(titulo)
                ax.set_ylabel("Valor (%)")
                plt.xticks(rotation=45)
                fig.tight_layout()

                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_img:
                    plt.savefig(tmp_img.name, bbox_inches='tight')
                    pdf.add_page()
                    pdf.image(tmp_img.name, x=10, y=20, w=180)
                plt.close()

        # Salvar PDF no Drive
        pdf.output(caminho_local)
        file_metadata = {"name": nome_pdf, "parents": [id_lider]}
        media = MediaIoBaseUpload(open(caminho_local, "rb"), mimetype="application/pdf")
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        return jsonify({"mensagem": f"✅ Parecer de Arquétipos gerado com sucesso: {nome_pdf}"})

    except Exception as e:
        print(f"❌ ERRO: {str(e)}")
        return jsonify({"erro": str(e)}), 500
