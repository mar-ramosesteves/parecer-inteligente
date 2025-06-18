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

        # Passo 1: Geração do texto com IA (GPT-3.5 + guias em .txt)

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
            "content": "Você é um consultor sênior em liderança e cultura organizacional. Irá receber guias teóricos e depois deverá gerar um parecer detalhado com base neles."
        })
        mensagens.append({
            "role": "user",
            "content": f"Esses são os guias de base obrigatória (arquétipos + microambiente):\n\n{conteudo_completo}"
        })
        mensagens.append({
            "role": "user",
            "content": f"""
Agora, com base nesses conteúdos e nos dados da líder {email_lider} da empresa {empresa} na rodada {rodada}, elabore um parecer completo com as seguintes 15 seções:

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

Responda no formato JSON com uma lista chamada "secoes", onde cada item contém "titulo" e "texto".
"""
        })

        resposta = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=mensagens,
            temperature=0.7,
        )

        conteudo_json = resposta.choices[0].message.content.strip()

        # Remove marcação de bloco de código, se presente
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

        
        # Passo 2: Criar PDF com FPDF usando o JSON estruturado
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

        # Passo 3: Autenticar no Google Drive
        SCOPES = ['https://www.googleapis.com/auth/drive']
        json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        info = json.loads(json_str)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

        service = build("drive", "v3", credentials=creds)

        # Passo 4: Criar pastas e subir PDF
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









from flask import Flask, request, jsonify
from flask_cors import CORS
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from busca_arquivos_drive import buscar_id
import os
import json
import fitz  # PyMuPDF

app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "https://gestor.thehrkey.tech"}})

PASTA_RAIZ = "1l4kOZwed-Yc5nHU4RBTmWQz3zYAlpniS"

@app.route("/extrair-pdfs-da-pasta", methods=["POST"])
@cross_origin(origins=["https://gestor.thehrkey.tech"])
def extrair_conteudo_pdfs():
    try:
        dados = request.get_json()
        empresa = dados["empresa"].lower()
        codrodada = dados["codrodada"].lower()
        emailLider = dados["emailLider"].lower()

        # ID da pasta raiz onde estão os dados
        PASTA_RAIZ = "1l4kOZwed-Yc5nHU4RBTmWQz3zYAlpniS"
        id_empresa = buscar_id(PASTA_RAIZ, empresa)
        id_rodada = buscar_id(id_empresa, codrodada)
        id_lider = buscar_id(id_rodada, emailLider)

        # Listar todos os arquivos .pdf na pasta do líder
        arquivos = (
            service.files()
            .list(q=f"'{id_lider}' in parents and mimeType='application/pdf'",
                  fields="files(name, id)")
            .execute()
        )

        pdfs = arquivos.get("files", [])
        resultados = {}

        for pdf in pdfs:
            nome = pdf["name"]
            file_id = pdf["id"]

            # Baixar o conteúdo do PDF
            request_file = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request_file)
            done = False
            while not done:
                status, done = downloader.next_chunk()

            # Ler o conteúdo usando PyMuPDF
            texto = ""
            with fitz.open(stream=fh.getvalue(), filetype="pdf") as doc:
                for pagina in doc:
                    texto += pagina.get_text()

            resultados[nome] = texto.strip()

        return jsonify({"mensagem": "✅ PDFs extraídos com sucesso", "conteudos": resultados})

    except Exception as e:
        return jsonify({"erro": str(e)}), 500
✅ ETAPA: Chamada JavaScript (ajuste no botão)
Na sua função JS que chama a rota:

javascript
Copiar
Editar
const empresa = document.querySelector('input[name="empresa"]').value;
const codrodada = document.querySelector('input[name="codrodada"]').value;
const emailLider = document.querySelector('input[name="emailLider"]').value;

fetch("https://api-microambiente.onrender.com/extrair-conteudo-pdfs", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ empresa, codrodada, emailLider }),
})
.then(response => response.json())
.then(data => {
  if (data.mensagem) {
    console.log(data.conteudos); // Aqui você pode usar os dados
    alert("✅ PDFs extraídos com sucesso!");
  } else {
    alert("Erro: " + data.erro);
  }
});
