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
import ast

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

        # Buscar apenas os JSONs de Arquétipos
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

        # Criar resumo dos dados para IA
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

        # Ler guia completo
        with open("guias_completos_unificados.txt", "r", encoding="utf-8") as f:
            guia = f.read()

        # Montar prompt
        mensagens = [
            {"role": "system", "content": "Você é um consultor sênior em liderança e cultura organizacional."},
            {"role": "user", "content": f"""
Você receberá a seguir um guia completo de interpretação sobre Arquétipos de Gestão e Microambiente de Equipes.
Sua tarefa agora é focar **apenas na parte de Arquétipos de Gestão**.

1. Preserve a linguagem consultiva e estruturada.
2. Insira os dados reais da líder {email_lider}, empresa {empresa}, rodada {rodada}.
3. Use os dados extraídos dos relatórios abaixo para análises personalizadas.
4. Gere um parecer ELEGANTE com seções bem organizadas.

📊 Dados da líder:

{resumo_dados}

📚 Guia completo:

{guia}

Responda no formato JSON com uma lista chamada "secoes", onde cada item contém "titulo" e "texto".
"""}
        ]

        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resposta = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=mensagens,
            temperature=0.7
        )

        conteudo_json = resposta.choices[0].message.content.strip()
        if conteudo_json.startswith("```json"):
            conteudo_json = conteudo_json[7:]
        elif conteudo_json.startswith("```"):
            conteudo_json = conteudo_json[3:]
        if conteudo_json.endswith("```"):
            conteudo_json = conteudo_json[:-3]

        parecer = ast.literal_eval(conteudo_json)

        # Gerar PDF
        nome_pdf = f"parecer_arquetipos_{email_lider}_{rodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        caminho_local = f"/tmp/{nome_pdf}"
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 10, f"PARECER DE ARQUÉTIPOS DE GESTÃO\nEmpresa: {empresa}\nRodada: {rodada}\nLíder: {email_lider}\nData: {datetime.now().strftime('%d/%m/%Y')}\n\n")
        for secao in parecer["secoes"]:
            pdf.set_font("Arial", "B", 12)
            pdf.multi_cell(0, 10, f"\n{secao['titulo']}")
            pdf.set_font("Arial", "", 12)
            pdf.multi_cell(0, 10, secao["texto"])
        pdf.output(caminho_local)

        # Enviar ao Google Drive
        file_metadata = {"name": nome_pdf, "parents": [id_lider]}
        media = MediaIoBaseUpload(open(caminho_local, "rb"), mimetype="application/pdf")
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        return jsonify({"mensagem": f"✅ Parecer de Arquétipos salvo com sucesso no Drive: {nome_pdf}"})

    except Exception as e:
        print(f"❌ ERRO: {str(e)}")
        return jsonify({"erro": str(e)}), 500
