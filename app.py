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
from PyPDF2 import PdfMerger
import requests


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

        with open("guias_completos_unificados.txt", "r", encoding="utf-8") as f:
            texto = f.read()
        inicio = texto.find("##### INICIO ARQUETIPOS #####")
        fim = texto.find("##### FIM ARQUETIPOS #####")
        guia = texto[inicio + len("##### INICIO ARQUETIPOS #####"):fim].strip() if inicio != -1 and fim != -1 else "Guia de Arquétipos não encontrado."

        marcador = "Abaixo, o resultado da análise de Arquétipos relativa ao modo como voce lidera em sua visão, comparado com a média da visão de sua equipe direta:"
        partes = guia.split(marcador)

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

        nome_pdf = f"parecer_arquetipos_{email_lider}_{rodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        caminho_local = f"/tmp/{nome_pdf}"
        pdf = FPDF()

        # 🟡 CAPA SEM LOGO - COM TEXTO CENTRALIZADO
        pdf.add_page()
        pdf.set_text_color(30, 60, 120)  # Azul escuro

        # Título da marca
        pdf.set_y(40)
        pdf.set_font("Arial", "B", 22)
        pdf.cell(190, 15, "THE HR KEY", 0, 1, "C")
        pdf.set_text_color(0, 130, 60)  # verde


        # Slogan
        pdf.set_font("Arial", "", 12)
        pdf.cell(190, 10, "Empowering Performance through People", 0, 1, "C")
        pdf.set_text_color(30, 60, 120)  # Azul escuro

        # Título principal
        pdf.ln(20)
        pdf.set_font("Arial", "B", 18)
        pdf.cell(190, 15, "ARQUÉTIPOS DE GESTÃO", 0, 1, "C")
        pdf.set_text_color(30, 60, 120)  # Azul escuro

        # Subtítulo com informações do líder
        pdf.set_font("Arial", "", 12)
        pdf.ln(5)
        pdf.cell(190, 10, f"{empresa.upper()} / {email_lider} / {rodada.upper()}", 0, 1, "C")
        pdf.set_text_color(30, 60, 120)  # Azul escuro

        # Mês e ano
        mes_ano = datetime.now().strftime('%B/%Y').upper()
        pdf.cell(190, 10, mes_ano, 0, 1, "C")


        pdf.add_page()
        pdf.set_font("Arial", size=12)
        if len(partes) == 2 and caminho_grafico1:
                        renderizar_bloco_personalizado(pdf, partes[0])
                        pdf.ln(5)

                        pdf.set_font("Arial", "B", 12)
                        pdf.multi_cell(0, 10, "Abaixo, os gráficos de dimensões e subdimensões de microambiente na sua percepção:")
                        pdf.ln(3)

                        # === GRÁFICO 1: Dimensões ===
                        json_dim = carregar_json("grafico_microambiente_autoavaliacao")
                        if json_dim and "dados" in json_dim:
                            labels = [item["DIMENSAO"] for item in json_dim["dados"]]
                            como_e = [item["REAL_%"] for item in json_dim["dados"]]
                            como_deveria = [item["IDEAL_%"] for item in json_dim["dados"]]
                            x = range(len(labels))
                            plt.figure(figsize=(10, 5))
                            plt.bar(x, como_e, width=0.4, label="Como é", align='center')
                            plt.bar([i + 0.4 for i in x], como_deveria, width=0.4, label="Como deveria ser", align='center')
                            for i, (v1, v2) in enumerate(zip(como_e, como_deveria)):
                                plt.text(i, v1 + 1, f"{v1:.0f}%", ha='center', fontsize=8)
                                plt.text(i + 0.4, v2 + 1, f"{v2:.0f}%", ha='center', fontsize=8)
                            plt.xticks([i + 0.2 for i in x], labels, rotation=45)
                            plt.ylim(0, 100)
                            plt.axhline(60, color="gray", linestyle="--", linewidth=1)
                            plt.title("MICROAMBIENTE DE EQUIPES - DIMENSÕES", fontsize=14, weight="bold")
                            plt.tight_layout()
                            caminho_img1 = "/tmp/grafico_micro_dimensao.png"
                            plt.savefig(caminho_img1)
                            plt.close()
                            pdf.image(caminho_img1, x=10, w=190)
                            pdf.ln(5)
                    
                        # === GRÁFICO 2: Subdimensões ===
                        json_sub = carregar_json("grafico_microambiente_autoavaliacao_subdimensao")
                        if json_sub and "dados" in json_sub:
                            labels = [item["SUBDIMENSAO"] for item in json_sub["dados"]]
                            como_e = [item["REAL_%"] for item in json_sub["dados"]]
                            como_deveria = [item["IDEAL_%"] for item in json_sub["dados"]]
                            x = range(len(labels))
                            plt.figure(figsize=(10, 6))
                            plt.bar(x, como_e, width=0.4, label="Como é", align='center')
                            plt.bar([i + 0.4 for i in x], como_deveria, width=0.4, label="Como deveria ser", align='center')
                            for i, (v1, v2) in enumerate(zip(como_e, como_deveria)):
                                plt.text(i, v1 + 1, f"{v1:.0f}%", ha='center', fontsize=6)
                                plt.text(i + 0.4, v2 + 1, f"{v2:.0f}%", ha='center', fontsize=6)
                            plt.xticks([i + 0.2 for i in x], labels, rotation=90)
                            plt.ylim(0, 100)
                            plt.axhline(60, color="gray", linestyle="--", linewidth=1)
                            plt.title("MICROAMBIENTE DE EQUIPES - SUBDIMENSÕES", fontsize=14, weight="bold")
                            plt.tight_layout()
                            caminho_img2 = "/tmp/grafico_micro_subdimensao.png"
                            plt.savefig(caminho_img2)
                            plt.close()
                            pdf.image(caminho_img2, x=10, w=190)
                            pdf.ln(10)
                    
                        renderizar_bloco_personalizado(pdf, partes[1])

        else:
            renderizar_bloco_personalizado(pdf, guia)

            if caminho_grafico1:
                pdf.add_page()
                pdf.image(caminho_grafico1, w=190)

        pdf.output(caminho_local)

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

            caminho_final = f"/tmp/FINAL_{nome_pdf}"
            merger = PdfMerger()
            merger.append(caminho_local)
            merger.append(caminho_pdf_analitico)
            merger.write(caminho_final)
            merger.close()
            caminho_local = caminho_final

        file_metadata = {"name": nome_pdf, "parents": [id_lider]}
        media = MediaIoBaseUpload(open(caminho_local, "rb"), mimetype="application/pdf")
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        print(f"✅ PDF salvo com sucesso no Drive: {nome_pdf}")
        return jsonify({"mensagem": f"✅ Parecer salvo no Drive: {nome_pdf}"})

    except Exception as e:
        return jsonify({"erro": str(e)}), 500



def renderizar_bloco_personalizado(pdf, texto):
    import re
    cores = {
        "AZUL": (30, 60, 120),
        "CINZA": (100, 100, 100),
        "VERDE": (0, 130, 60),
        "VERMELHO": (180, 30, 30),
        "PRETO": (0, 0, 0),
        "PADRAO": (0, 0, 0)
    }

    pdf.set_font("Arial", size=12)
    pdf.set_text_color(0, 0, 0)

    linhas = texto.split("\n")
    for linha in linhas:
        linha = linha.strip()

        if linha.startswith("[COR:"):
            cor_tag = linha[5:-1].upper()
            cor_rgb = cores.get(cor_tag, (0, 0, 0))
            pdf.set_text_color(*cor_rgb)
            continue

        elif linha.startswith("[[CAIXA:") and linha.endswith("]]"):
            conteudo = linha[8:-2].strip()
            pdf.set_fill_color(240, 240, 240)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Arial", "B", 12)
            pdf.multi_cell(0, 10, conteudo.encode("latin-1", "ignore").decode("latin-1"), border=1, fill=True)
            pdf.ln(2)
            pdf.set_font("Arial", size=12)
            continue

        elif linha == "[[PAGEBREAK]]":
            pdf.add_page()
            continue

        elif linha.startswith("## "):
            pdf.set_font("Arial", "B", 16)
            pdf.set_text_color(*cores["AZUL"])
            titulo = linha[3:].strip().encode("latin-1", "ignore").decode("latin-1")
            pdf.multi_cell(0, 12, titulo)
            pdf.ln(1)
            pdf.set_font("Arial", size=12)
            pdf.set_text_color(*cores["PADRAO"])
            continue

        elif linha.startswith("### "):
            pdf.set_font("Arial", "B", 13)
            pdf.set_text_color(0, 130, 60)

            subtitulo = linha[4:].strip().encode("latin-1", "ignore").decode("latin-1")
            pdf.multi_cell(0, 10, subtitulo)
            pdf.ln(1)
            pdf.set_font("Arial", size=12)
            pdf.set_text_color(*cores["PADRAO"])
            continue

        # Negrito e itálico (dentro da linha)
        linha = re.sub(r"\*\*(.*?)\*\*", lambda m: f"\x01{m.group(1)}\x01", linha)
        linha = re.sub(r"_(.*?)_", lambda m: f"\x02{m.group(1)}\x02", linha)

        partes = re.split(r"(\x01.*?\x01|\x02.*?\x02)", linha)
        for parte in partes:
            if parte.startswith("\x01") and parte.endswith("\x01"):
                pdf.set_font("Arial", "B", 12)
                texto_limpo = parte[1:-1].encode("latin-1", "ignore").decode("latin-1")
                pdf.write(5, texto_limpo)
            elif parte.startswith("\x02") and parte.endswith("\x02"):
                pdf.set_font("Arial", "I", 12)
                texto_limpo = parte[1:-1].encode("latin-1", "ignore").decode("latin-1")
                pdf.write(5, texto_limpo)
            else:
                pdf.set_font("Arial", size=12)
                texto_limpo = parte.encode("latin-1", "ignore").decode("latin-1")
                pdf.write(5, texto_limpo)
        pdf.ln(7)



@app.route("/emitir-parecer-microambiente", methods=["POST"])
def emitir_parecer_microambiente():
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

        json_dimensao = carregar_json("AUTOAVALIACAO_DIMENSOES")
        caminho_grafico1 = None

        if json_dimensao:
            labels = list(json_dimensao["valores"].keys())
            valores = list(json_dimensao["valores"].values())
            x = range(len(labels))
            plt.figure(figsize=(10, 5))
            plt.bar(x, valores, color="#1f77b4")
            for i, v in enumerate(valores):
                plt.text(i, v + 1, f"{v:.0f}%", ha="center", fontsize=8)
            plt.xticks(x, labels, rotation=45)
            plt.axhline(60, color="gray", linestyle="--", linewidth=1)
            plt.ylim(0, 100)
            plt.title("AUTOAVALIAÇÃO - MICROAMBIENTE", fontsize=14, weight="bold")
            subtitulo = f"{empresa.upper()} / {rodada.upper()} / {email_lider} / {datetime.now().strftime('%B/%Y')}"
            plt.suptitle(subtitulo, fontsize=10, y=0.85)
            caminho_grafico1 = "/tmp/grafico_micro.png"
            plt.tight_layout()
            plt.savefig(caminho_grafico1)
            plt.close()

        with open("guias_completos_unificados.txt", "r", encoding="utf-8") as f:
            texto = f.read()
        inicio = texto.find("##### INICIO MICROAMBIENTE #####")
        fim = texto.find("##### FIM MICROAMBIENTE #####")
        guia = texto[inicio + len("##### INICIO MICROAMBIENTE #####"):fim].strip() if inicio != -1 and fim != -1 else "Guia de Microambiente não encontrado."

        marcador = "Abaixo, o resultado da análise de Microambiente de Equipes com base na sua autoavaliação, comparada com os parâmetros ideais:"
        partes = guia.split(marcador)

        nome_pdf = f"parecer_microambiente_{email_lider}_{rodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        caminho_local = f"/tmp/{nome_pdf}"
        pdf = FPDF()

        # 🟢 CAPA
        pdf.add_page()
        pdf.set_text_color(30, 60, 120)  # Azul escuro

        pdf.set_y(40)
        pdf.set_font("Arial", "B", 22)
        pdf.cell(190, 15, "THE HR KEY", 0, 1, "C")

        pdf.set_text_color(0, 130, 60)  # Verde
        pdf.set_font("Arial", "", 12)
        pdf.cell(190, 10, "Empowering Performance through People", 0, 1, "C")

        pdf.set_text_color(30, 60, 120)
        pdf.ln(20)
        pdf.set_font("Arial", "B", 18)
        pdf.cell(190, 15, "MICROAMBIENTE DE EQUIPES", 0, 1, "C")

        pdf.set_font("Arial", "", 12)
        pdf.ln(5)
        pdf.cell(190, 10, f"{empresa.upper()} / {email_lider} / {rodada.upper()}", 0, 1, "C")

        mes_ano = datetime.now().strftime('%B/%Y').upper()
        pdf.cell(190, 10, mes_ano, 0, 1, "C")

        # 🔵 CONTEÚDO
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        if len(partes) == 2 and caminho_grafico1:
            renderizar_bloco_personalizado(pdf, partes[0])
            pdf.ln(5)
            pdf.set_font("Arial", "B", 12)
            pdf.multi_cell(0, 10, marcador.encode("latin-1", "ignore").decode("latin-1"))
            pdf.ln(2)
            pdf.image(caminho_grafico1, w=190)
            renderizar_bloco_personalizado(pdf, partes[1])
        else:
            renderizar_bloco_personalizado(pdf, guia)
            if caminho_grafico1:
                pdf.add_page()
                pdf.image(caminho_grafico1, w=190)

        pdf.output(caminho_local)

        resultado_arquivos = service.files().list(
            q=f"'{id_lider}' in parents and name contains 'RELATORIO_ANALITICO_MICROAMBIENTE' and mimeType='application/pdf'",
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

            caminho_final = f"/tmp/FINAL_{nome_pdf}"
            merger = PdfMerger()
            merger.append(caminho_local)              # parecer gerado com FPDF
            merger.append(caminho_pdf_analitico)      # relatório analítico microambiente
            merger.write(caminho_final)
            merger.close()
            caminho_local = caminho_final

        file_metadata = {"name": nome_pdf, "parents": [id_lider]}
        media = MediaIoBaseUpload(open(caminho_local, "rb"), mimetype="application/pdf")
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        print(f"✅ PDF salvo com sucesso no Drive: {nome_pdf}")
        return jsonify({"mensagem": f"✅ Parecer salvo no Drive: {nome_pdf}"})

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


        

