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

                # 🔵 Minigráficos analíticos de arquétipos (por bloco)
        if json_analitico and "analise" in json_analitico:
            blocos = {}
            for item in json_analitico["analise"]:
                bloco = item.get("bloco", "OUTROS")
                if bloco not in blocos:
                    blocos[bloco] = []
                blocos[bloco].append(item)

            for nome_bloco, perguntas in blocos.items():
                pdf.add_page()
                pdf.set_font("Arial", "B", 12)
                pdf.multi_cell(0, 10, f"ANÁLISE POR BLOCO: {nome_bloco.upper()}")
                y_offset = 40
                for i, item in enumerate(perguntas):
                    try:
                        afirmacao = item.get("afirmacao", f"Afirmação {i+1}")
                        valor_auto = item.get("pontuacao_auto", 0)
                        valor_equipe = item.get("pontuacao_equipe", 0)

                        # Criar gráfico tipo velocímetro horizontal
                        plt.figure(figsize=(6.5, 0.4))
                        plt.barh([0], [valor_auto], color="blue", label="Auto", height=0.3)
                        plt.barh([0.4], [valor_equipe], color="green", label="Equipe", height=0.3)
                        plt.xlim(0, 100)
                        plt.xticks([0, 20, 40, 60, 80, 100])
                        plt.yticks([])
                        plt.axvline(50, color="gray", linestyle="--", linewidth=0.8)
                        plt.axvline(60, color="gray", linestyle="--", linewidth=0.8)
                        plt.text(valor_auto + 1, 0, f"{valor_auto:.0f}%", va='center', fontsize=6)
                        plt.text(valor_equipe + 1, 0.4, f"{valor_equipe:.0f}%", va='center', fontsize=6)
                        plt.tight_layout()

                        # Salvar e inserir
                        caminho_barra = f"/tmp/barra_{nome_bloco}_{i}.png"
                        plt.savefig(caminho_barra)
                        plt.close()
                        pdf.image(caminho_barra, x=10, y=y_offset, w=180)
                        y_offset += 12
                        if y_offset > 260:
                            pdf.add_page()
                            y_offset = 40
                    except Exception as erro:
                        print(f"Erro ao gerar minigráfico {i} do bloco {nome_bloco}: {erro}")

        
        
        # Salvar no Drive
        pdf.output(caminho_local)
        file_metadata = {"name": nome_pdf, "parents": [id_lider]}
        media = MediaIoBaseUpload(open(caminho_local, "rb"), mimetype="application/pdf")
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        print(f"✅ PDF salvo com sucesso no Drive: {nome_pdf}")
        return jsonify({"mensagem": f"✅ Parecer salvo no Drive: {nome_pdf}"})
    
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
