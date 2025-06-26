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

@app.route("/emitir-parecer-inteligente", methods=["POST"])
def emitir_parecer():
    try:
        dados = request.get_json()
        empresa = dados["empresa"].lower()
        rodada = dados["codrodada"].lower()
        email_lider = dados["emailLider"].lower()

        import ast
        from openai import OpenAI

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        def ler_txt(caminho):
            with open(caminho, "r", encoding="utf-8") as f:
                return f.read()

        conteudo_completo = ler_txt("guias_completos_unificados.txt")

        mensagens = []
        mensagens.append({
            "role": "system",
            "content": "Você é um consultor sênior em liderança e cultura organizacional."
        })
        mensagens.append({
            "role": "user",
            "content": f"""
Você receberá a seguir um guia completo de interpretação sobre Arquétipos de Gestão e Microambiente de Equipes. Este guia servirá como BASE FIXA do parecer.

A sua tarefa será:

1. Preservar todo o conteúdo e estrutura dos guias.
2. Inserir os dados individuais do líder nos trechos mais adequados, sempre com clareza e transição natural.
3. Incluir análises personalizadas baseadas nos relatórios extraídos do Google Drive.
4. Manter uma linguagem consultiva, estruturada e elegante.

Guia completo abaixo:

{conteudo_completo}
"""
        })
        mensagens.append({
            "role": "user",
            "content": f"""
Agora, com base nesse conteúdo, elabore um parecer inteligente da líder {email_lider} da empresa {empresa}, na rodada {rodada}. Insira os dados e análises personalizadas nos locais apropriados do texto.

Responda no formato JSON com uma lista chamada \"secoes\", onde cada item contém \"titulo\" e \"texto\".
"""
        })

        resposta = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=mensagens,
            temperature=0.7,
        )

        conteudo_json = resposta.choices[0].message.content.strip()

        if conteudo_json.startswith("```json"):
            conteudo_json = conteudo_json[7:]
        elif conteudo_json.startswith("```"):
            conteudo_json = conteudo_json[3:]

        if conteudo_json.endswith("```"):
            conteudo_json = conteudo_json[:-3]

        try:
            parecer = ast.literal_eval(conteudo_json)
        except Exception as erro_json:
            print("❌ ERRO AO INTERPRETAR O JSON:", erro_json)
            print("🔎 CONTEÚDO ORIGINAL DA IA:")
            print(conteudo_json[:1000])
            return jsonify({"erro": "A IA respondeu em formato inválido. Verifique o console para analisar."}), 500

        nome_pdf = f"parecer_{email_lider}_{rodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        caminho_local = f"/tmp/{nome_pdf}"
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 10, f"PARECER INTELIGENTE\nEmpresa: {empresa}\nRodada: {rodada}\nLíder: {email_lider}\nData: {datetime.now().strftime('%d/%m/%Y')}\n\n")

        for secao in parecer["secoes"]:
            titulo = secao.get("titulo", "")
            texto = secao.get("texto", "")
            pdf.set_font("Arial", "B", 12)
            pdf.multi_cell(0, 10, f"\n{titulo}")
            pdf.set_font("Arial", "", 12)
            pdf.multi_cell(0, 10, texto)

        pdf.output(caminho_local)

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
