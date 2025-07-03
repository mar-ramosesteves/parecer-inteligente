from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
from fpdf import FPDF
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
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

        # Autenticação no Google Drive
        SCOPES = ['https://www.googleapis.com/auth/drive']
        json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        info = json.loads(json_str)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        service = build("drive", "v3", credentials=creds)

        # Acessar pastas
        id_empresa = buscar_id(service, PASTA_RAIZ, empresa)
        id_rodada = buscar_id(service, id_empresa, rodada)
        id_lider = buscar_id(service, id_rodada, email_lider)
        id_ia_json = buscar_id(service, id_lider, "IA_JSON")

        # Carregar JSONs
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

        # Extrair guia
        with open("guias_completos_unificados.txt", "r", encoding="utf-8") as f:
            texto = f.read()
        inicio = texto.find("##### INICIO ARQUETIPOS #####")
        fim = texto.find("##### FIM ARQUETIPOS #####")
        guia = texto[inicio + len("##### INICIO ARQUETIPOS #####"):fim].strip() if inicio != -1 and fim != -1 else "Guia de Arquétipos não encontrado."

        # Inserir marcador no guia
        marcador = "Abaixo, o resultado da análise de Arquétipos relativa ao modo como voce lidera em sua visão, comparado com a média da visão de sua equipe direta:"
        partes = guia.split(marcador)

        # Gerar gráfico 1
        caminho_grafico1 = None
        if json_auto_vs_equipe:
            labels = list(json_auto_vs_equipe["autoavaliacao"].keys())
            auto = list(json_auto_vs_equipe["autoavaliacao"].values())
            equipe = list(json_auto_vs_equipe["mediaEquipe"].values())
            x = range(len(labels))
            plt.figure(figsize=(10, 5))
            plt.bar(x, auto, width=0.4, label="Autoavaliação", align='center')
            plt.bar([i + 0.4 for i in x], equipe, width=0.4, label="Equipe", align='center')
            for i, (a, e) in enumerate(zip(auto, equipe)):
                plt.text(i, a + 1, f"{a:.0f}%", ha='center', fontsize=8)
                plt.text(i + 0.4, e + 1, f"{e:.0f}%", ha='center', fontsize=8)
            plt.xticks([i + 0.2 for i in x], labels, rotation=45)
            plt.axhline(50, color="gray", linestyle="--", linewidth=1)
            plt.text(len(labels) - 0.5, 51, "Suporte", color="gray", fontsize=8, ha='right')
            plt.axhline(60, color="gray", linestyle="--", linewidth=1)
            plt.text(len(labels) - 0.5, 61, "Dominante", color="gray", fontsize=8, ha='right')
            plt.title("ARQUÉTIPOS AUTO VS EQUIPE", fontsize=14, weight="bold")
            subtitulo = f"{empresa.upper()} / {rodada.upper()} / {email_lider} / {datetime.now().strftime('%B/%Y')}"
            plt.suptitle(subtitulo, fontsize=10, y=0.85)
            plt.ylim(0, 100)
            plt.legend()
            caminho_grafico1 = "/tmp/grafico1.png"
            plt.tight_layout()
            plt.savefig(caminho_grafico1)
            plt.close()

        # Criar PDF
        nome_pdf = f"parecer_arquetipos_{email_lider}_{rodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        caminho_local = f"/tmp/{nome_pdf}"
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 10, f"PARECER DE ARQUETIPOS DE GESTAO\nEmpresa: {empresa}\nRodada: {rodada}\nLider: {email_lider}\nData: {datetime.now().strftime('%d/%m/%Y')}\n\n")

        if len(partes) == 2 and caminho_grafico1:
            pdf.multi_cell(0, 10, partes[0].encode("latin-1", "ignore").decode("latin-1"))
            pdf.multi_cell(0, 10, marcador.encode("latin-1", "ignore").decode("latin-1"))
            pdf.image(caminho_grafico1, w=190)
            pdf.multi_cell(0, 10, partes[1].encode("latin-1", "ignore").decode("latin-1"))
        else:
            pdf.multi_cell(0, 10, guia.encode("latin-1", "ignore").decode("latin-1"))
            if caminho_grafico1:
                pdf.add_page()
                pdf.image(caminho_grafico1, w=190)

        from PyPDF2 import PdfMerger

        # 🔗 Baixar o PDF analítico existente
        resultado_arquivos = service.files().list(
            q=f"'{id_lider}' in parents and name contains 'RELATORIO_ANALITICO_ARQUETIPOS' and mimeType='application/pdf'",
            spaces='drive', fields='files(id, name)', orderBy='createdTime desc'
        ).execute()
        arquivos_pdf = resultado_arquivos.get("files", [])

        if arquivos_pdf:
            id_pdf_analitico = arquivos_pdf[0]["id"]
            nome_pdf_analitico = arquivos_pdf[0]["name"]
            caminho_pdf_analitico = f"/tmp/{nome_pdf_analitico}"
    
            request_analitico = service.files().get_media(fileId=id_pdf_analitico)
            with open(caminho_pdf_analitico, "wb") as f:
                downloader = MediaIoBaseDownload(f, request_analitico)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()

            # 🔗 Mesclar os dois PDFs
            caminho_final = f"/tmp/FINAL_{nome_pdf}"
            merger = PdfMerger()
            merger.append(caminho_local)           # Parecer
            merger.append(caminho_pdf_analitico)   # Analítico
            merger.write(caminho_final)
            merger.close()
    
            # Substitui o caminho final a ser salvo
            caminho_local = caminho_final

        
        
       
                # 🔵 Salvar o parecer PDF gerado
        pdf.output(caminho_local)

        # 🔗 Baixar o PDF analítico existente
        from PyPDF2 import PdfMerger
        resultado_arquivos = service.files().list(
            q=f"'{id_lider}' in parents and name contains 'RELATORIO_ANALITICO_ARQUETIPOS' and mimeType='application/pdf'",
            spaces='drive', fields='files(id, name)', orderBy='createdTime desc'
        ).execute()
        arquivos_pdf = resultado_arquivos.get("files", [])

        if arquivos_pdf:
            id_pdf_analitico = arquivos_pdf[0]["id"]
            nome_pdf_analitico = arquivos_pdf[0]["name"]
            caminho_pdf_analitico = f"/tmp/{nome_pdf_analitico}"

            request_analitico = service.files().get_media(fileId=id_pdf_analitico)
            with open(caminho_pdf_analitico, "wb") as f:
                downloader = MediaIoBaseDownload(f, request_analitico)
                done = False
                while not done:
                    status, done = downloader.next_chunk()

            # 🔗 Mesclar os dois PDFs
            caminho_final = f"/tmp/FINAL_{nome_pdf}"
            merger = PdfMerger()
            merger.append(caminho_local)           # Parecer
            merger.append(caminho_pdf_analitico)   # Analítico
            merger.write(caminho_final)
            merger.close()

            caminho_local = caminho_final

        # ⬆️ Upload para o Google Drive
        file_metadata = {"name": nome_pdf, "parents": [id_lider]}
        media = MediaIoBaseUpload(open(caminho_local, "rb"), mimetype="application/pdf")
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        print(f"✅ PDF salvo com sucesso no Drive: {nome_pdf}")
        return jsonify({"mensagem": f"✅ Parecer salvo no Drive: {nome_pdf}"})

    except Exception as e:
        return jsonify({"erro": str(e)}), 500

