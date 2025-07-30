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
import base64
import io




app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "https://gestor.thehrkey.tech"}})

PASTA_RAIZ = "1ekQKwPchEN_fO4AK0eyDd_JID5YO3hAF"

from flask import request, jsonify
from datetime import datetime






SUPABASE_REST_URL = os.getenv("SUPABASE_REST_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")




from flask import Flask, request, jsonify
import json, os
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import base64
import io

app = Flask(__name__)

SUPABASE_REST_URL = os.getenv("SUPABASE_REST_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def salvar_relatorio_analitico_no_supabase(dados, empresa, codrodada, email_lider, tipo):
    import requests
    url = f"{SUPABASE_REST_URL}/relatorios_gerados"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "empresa": empresa,
        "codrodada": codrodada,
        "emaillider": email_lider,
        "tipo_relatorio": tipo,
        "dados_json": dados,
        "data_criacao": datetime.utcnow().isoformat()
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

@app.route("/emitir-parecer-arquetipos", methods=["POST", "OPTIONS"])
def emitir_parecer_arquetipos():
    if request.method == "OPTIONS":
        response = jsonify({'status': 'CORS preflight OK'})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        return response

    try:
        dados = request.get_json()
        empresa = dados["empresa"].lower()
        rodada = dados["codrodada"].lower()
        email_lider = dados["emailLider"].lower()

        tipo_relatorio = "arquetipos_parecer_ia"

        # Buscar JSONs no Supabase
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }

        def buscar_json(tipo):
            url = f"{SUPABASE_REST_URL}/relatorios_gerados"
            params = {
                "empresa": f"eq.{empresa}",
                "codrodada": f"eq.{rodada}",
                "emaillider": f"eq.{email_lider}",
                "tipo_relatorio": f"eq.{tipo}",
                "order": "data_criacao.desc",
                "limit": 1
            }
            resp = requests.get(url, headers=headers, params=params)
            if resp.status_code == 200 and resp.json():
                return resp.json()[0]["dados_json"]
            return None

        json_auto_vs_equipe = buscar_json("arquetipos_grafico_comparativo")

        # Carregar o guia base
        with open("guias_completos_unificados.txt", "r", encoding="utf-8") as f:
            texto = f.read()
        inicio = texto.find("##### INICIO ARQUETIPOS #####")
        fim = texto.find("##### FIM ARQUETIPOS #####")
        guia = texto[inicio + len("##### INICIO ARQUETIPOS #####"):fim].strip() if inicio != -1 and fim != -1 else "Guia de Arquétipos não encontrado."

        marcador = "Abaixo, o resultado da análise de Arquétipos relativa ao modo como voce lidera em sua visão, comparado com a média da visão de sua equipe direta:"
        partes = guia.split(marcador)

        imagem_base64 = ""
        if json_auto_vs_equipe:
            import matplotlib.pyplot as plt
            import io, base64
            import numpy as np

            labels = list(json_auto_vs_equipe["autoavaliacao"].keys())
            auto = list(json_auto_vs_equipe["autoavaliacao"].values())
            equipe = list(json_auto_vs_equipe["mediaEquipe"].values())
            x = np.arange(len(labels))
            fig, ax = plt.subplots(figsize=(10, 5))
            ax.bar(x - 0.2, auto, width=0.4, label="Autoavaliação", color="royalblue")
            ax.bar(x + 0.2, equipe, width=0.4, label="Equipe", color="darkorange")
            for i in range(len(labels)):
                ax.text(x[i] - 0.2, auto[i] + 1, f"{auto[i]:.0f}%", ha='center', fontsize=8)
                ax.text(x[i] + 0.2, equipe[i] + 1, f"{equipe[i]:.0f}%", ha='center', fontsize=8)
            ax.set_xticks(x)
            ax.set_xticklabels(labels, rotation=45)
            ax.axhline(50, color="gray", linestyle="--")
            ax.axhline(60, color="gray", linestyle=":")
            ax.set_ylim(0, 100)
            ax.set_title("ARQUÉTIPOS AUTO VS EQUIPE", fontsize=14, weight="bold")
            plt.tight_layout()

            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            imagem_base64 = base64.b64encode(buf.read()).decode("utf-8")
            plt.close()

        bloco_html = partes[0] + f'<br><br><img src="data:image/png;base64,{imagem_base64}" style="width:100%;max-width:800px;"><br><br>' + partes[1] if len(partes) == 2 else guia

        dados_retorno = {
            "titulo": "ARQUÉTIPOS DE GESTÃO",
            "subtitulo": f"{empresa.upper()} / {rodada.upper()} / {email_lider}",
            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "conteudo_html": bloco_html
        }

        # Salvar no Supabase
        payload = {
            "empresa": empresa,
            "codrodada": rodada,
            "emaillider": email_lider,
            "tipo_relatorio": tipo_relatorio,
            "dados_json": dados_retorno,
            "data_criacao": datetime.now().isoformat()
        }
        requests.post(f"{SUPABASE_REST_URL}/relatorios_gerados", headers=headers, json=payload)

        return jsonify(dados_retorno), 200

    except Exception as e:
        print("Erro no parecer IA arquetipos:", e)
        return jsonify({"erro": str(e)}), 500



@app.route("/emitir-parecer-microambiente", methods=["POST"])
def emitir_parecer_microambiente():
    try:
        from matplotlib import pyplot as plt
        import os
        import json
        from datetime import datetime
        from fpdf import FPDF
        from PyPDF2 import PdfMerger
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
        from google.oauth2 import service_account

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

        def gerar_grafico_linha(json_dados, titulo, nome_arquivo):
            try:
                if not json_dados or "dados" not in json_dados:
                    print(f"→ Sem dados para gráfico {titulo}")
                    return None
        
                dados = json_dados["dados"]
                labels = []
                valores_real = []
                valores_ideal = []
                for item in dados:
                    # Tenta DIMENSAO, se não existir tenta SUBDIMENSAO
                    label = item.get("DIMENSAO") or item.get("SUBDIMENSAO")
                    if label is None:
                        print("❗ Ignorando item sem DIMENSAO/SUBDIMENSAO:", item)
                        continue
                    labels.append(label)
                    valores_real.append(item.get("REAL_%", 0))
                    valores_ideal.append(item.get("IDEAL_%", 0))
        
                if not labels:
                    print("→ Nenhuma label válida encontrada em:", dados)
                    return None
        
                plt.figure(figsize=(10, 5))
                plt.plot(labels, valores_ideal, marker='o', linestyle='--',
                         color='gray', linewidth=2, label="Como deveria ser")
                for i, v in enumerate(valores_ideal):
                    plt.text(i, v + 1.5, f"{v:.1f}%", ha='center', va='bottom', fontsize=8, color='gray')
        
                plt.plot(labels, valores_real, marker='o', color="#1f77b4",
                         linewidth=2, label="Como é")
                for i, v in enumerate(valores_real):
                    plt.text(i, v - 3, f"{v:.1f}%", ha='center', va='top', fontsize=8, color='#1f77b4')
        
                plt.xticks(rotation=45, ha='right')
                plt.ylim(0, 100)
                plt.axhline(60, color="gray", linestyle="--", linewidth=1)
                plt.grid(True, linestyle='--', alpha=0.6)
        
                subtitulo = f"{empresa.upper()} / {email_lider} / {rodada.upper()} / {datetime.now():%B/%Y}".upper()
                plt.suptitle(titulo, fontsize=14, weight="bold", y=0.98)
                plt.title(subtitulo, fontsize=10)
                plt.legend()
                plt.tight_layout()
        
                caminho = f"/tmp/{nome_arquivo}"
                plt.savefig(caminho)
                plt.close()
                print("✅ Gráfico salvo em:", caminho)
                return caminho
        
            except Exception as e:
                print(f"❌ Erro ao gerar gráfico '{titulo}':", e)
                return None



        json_dimensao = carregar_json("grafico_microambiente_autoavaliacao")
        json_subdimensao = carregar_json("AUTOAVALIACAO_SUBDIMENSAO")
        json_eq_dimensao = carregar_json("grafico_microambiente_mediaequipe_dimensao")
        json_eq_subdimensao = carregar_json("grafico_microambiente_mediaequipe_subdimensao")  
        # === Inserção do JSON do termômetro e waterfall ===
        json_termometro = carregar_json("STATUS - TERMÔMETRO")
        json_waterfall = carregar_json("GAP MÉDIO POR DIMENSÃO E SUBDIMENSÃO")

          
        caminho_grafico1 = gerar_grafico_linha(json_dimensao, "Autoavaliação por Dimensões", "grafico_dimensao.png")
        caminho_grafico2 = gerar_grafico_linha(json_subdimensao, "Autoavaliação por Subdimensões", "grafico_subdimensao.png")
        caminho_grafico3 = gerar_grafico_linha(json_eq_dimensao, "Média da Equipe por Dimensões", "grafico_eq_dimensao.png")
        caminho_grafico4 = gerar_grafico_linha(json_eq_subdimensao, "Média da Equipe por Subdimensões", "grafico_eq_subdimensao.png")


        with open("guias_completos_unificados.txt", "r", encoding="utf-8") as f:
            texto = f.read()
        inicio = texto.find("##### INICIO MICROAMBIENTE #####")
        fim = texto.find("##### FIM MICROAMBIENTE #####")
        guia = texto[inicio + len("##### INICIO MICROAMBIENTE #####"):fim].strip() if inicio != -1 and fim != -1 else "Guia de Microambiente não encontrado."

        marcador = "Abaixo, os gráficos de dimensões e subdimensões de microambiente na sua percepção:"
        partes = guia.split(marcador)

        nome_pdf = f"parecer_microambiente_{email_lider}_{rodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        caminho_local = f"/tmp/{nome_pdf}"
        pdf = FPDF()

        # CAPA
        pdf.add_page()
        pdf.set_text_color(30, 60, 120)
        pdf.set_y(40)
        pdf.set_font("Arial", "B", 22)
        pdf.cell(190, 15, "THE HR KEY", 0, 1, "C")

        pdf.set_text_color(0, 130, 60)
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

        # CONTEÚDO
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        if len(partes) == 2:
            renderizar_bloco_personalizado(pdf, partes[0])
            pdf.set_font("Arial", "B", 12)
            pdf.multi_cell(0, 8, marcador)
            # Gráfico de DIMENSÕES (duas linhas: Ideal e Real)
            # Gráfico de DIMENSÕES (duas linhas: Ideal e Real)
        if json_dimensao and "dados" in json_dimensao:
            try:
                dados = json_dimensao["dados"]
                labels = [item["DIMENSAO"] for item in dados]
                ideal = [item["IDEAL_%"] for item in dados]
                real = [item["REAL_%"] for item in dados]
        
                plt.figure(figsize=(10, 5))
                plt.plot(labels, ideal, marker='o', label='Como Deveria Ser (Ideal)', linewidth=2)
                plt.plot(labels, real, marker='o', label='Como É (Real)', linewidth=2)
                plt.xticks(rotation=45, ha='right')
                plt.ylim(0, 100)
                plt.ylabel("Percentual (%)")
                plt.axhline(60, color="gray", linestyle="--", linewidth=1)
                plt.title(
                    "Autoavaliação por Dimensões\n" +
                    f"{empresa.upper()} / {email_lider} / {rodada.upper()} / {datetime.now().strftime('%B/%Y').upper()}",
                    fontsize=11, weight="bold", loc='center'
                )
                plt.tight_layout()
                plt.grid(True, linestyle="--", alpha=0.5)
                plt.legend()
                caminho_grafico_dimensao = "/tmp/grafico_micro_dimensao.png"
                plt.savefig(caminho_grafico_dimensao)
                plt.close()
        
                pdf.image(caminho_grafico_dimensao, w=180)
                pdf.ln(2)
            except Exception as e:
                print("Erro ao gerar gráfico de dimensões:", e)
            
            # Gráfico de SUBDIMENSÕES (linha única, já existente)
            if caminho_grafico2:
                pdf.image(caminho_grafico2, w=180)
                pdf.ln(2)
                # Frase de transição para gráficos da equipe
                pdf.set_font("Arial", "B", 12)
                pdf.multi_cell(0, 8, "e a seguir, o gráfico de dimensões e subdimensões de microambiente na visão da sua equipe direta:")
            
                pdf.ln(6)
            
                # Gráfico de DIMENSÕES - EQUIPE
                json_dimensao_eq = carregar_json("microambiente_mediaequipe_dimensao")
                if json_dimensao_eq and "dados" in json_dimensao_eq:
                    try:
                        dados_eq = json_dimensao_eq["dados"]
                        labels_eq = [item["DIMENSAO"] for item in dados_eq]
                        ideal_eq = [item["IDEAL_%"] for item in dados_eq]
                        real_eq = [item["REAL_%"] for item in dados_eq]
            
                        plt.figure(figsize=(10, 5))
                        plt.plot(labels_eq, ideal_eq, marker='o', label='Como Deveria Ser (Ideal)', linewidth=2)
                        plt.plot(labels_eq, real_eq, marker='o', label='Como É (Real)', linewidth=2)
                        plt.xticks(rotation=45, ha='right')
                        plt.ylim(0, 100)
                        plt.ylabel("Percentual (%)")
                        plt.axhline(60, color="gray", linestyle="--", linewidth=1)
                        plt.title("Média da Equipe por Dimensões", fontsize=11, weight="bold", loc='center')
                        plt.tight_layout()
                        plt.grid(True, linestyle="--", alpha=0.5)
                        plt.legend()
                        caminho_grafico_eq_dimensao = "/tmp/grafico_eq_dimensao.png"
                        plt.savefig(caminho_grafico_eq_dimensao)
                        plt.close()
            
                        pdf.image(caminho_grafico_eq_dimensao, w=180)
                        pdf.ln(2)
                    except Exception as e:
                        print("Erro ao gerar gráfico de dimensões da equipe:", e)

                # Gráfico de SUBDIMENSÕES - EQUIPE
                json_sub_eq = carregar_json("microambiente_media_equipe_subdimensao")
                if json_sub_eq and "dados" in json_sub_eq:
                    try:
                        dados_sub = json_sub_eq["dados"]
                        labels_sub = [item["SUBDIMENSAO"] for item in dados_sub]
                        ideal_sub = [item["IDEAL_%"] for item in dados_sub]
                        real_sub = [item["REAL_%"] for item in dados_sub]
                        
                        plt.figure(figsize=(10, 5))
                        plt.plot(labels_sub, ideal_sub, marker='o', linestyle='--', color='gray', linewidth=2, label="Como deveria ser")
                        for i, v in enumerate(ideal_sub):
                            plt.text(i, v + 1.5, f"{v:.1f}%", ha='center', va='bottom', fontsize=8, color='gray')
                        
                        plt.plot(labels_sub, real_sub, marker='o', color="#1f77b4", linewidth=2, label="Como é")
                        for i, v in enumerate(real_sub):
                            plt.text(i, v - 3, f"{v:.1f}%", ha='center', va='top', fontsize=8, color='#1f77b4')
                        
                        plt.xticks(rotation=45, ha='right')
                        plt.ylim(0, 100)
                        plt.grid(True, linestyle='--', alpha=0.6)
                        plt.axhline(60, color="gray", linestyle="--", linewidth=1)
                        plt.title("Média da Equipe por Subdimensões", fontsize=11, weight="bold", loc='center')
                        plt.tight_layout()
                        plt.legend()

                        plt.xticks(rotation=45, ha='right')
                        plt.ylim(0, 100)
                        plt.grid(True, linestyle='--', alpha=0.6)
                        plt.axhline(60, color="gray", linestyle="--", linewidth=1)
                        plt.title("Média da Equipe por Subdimensões", fontsize=11, weight="bold", loc='center')
                        plt.tight_layout()
                        caminho_grafico_eq_sub = "/tmp/grafico_eq_subdimensao.png"
                        plt.savefig(caminho_grafico_eq_sub)
                        plt.close()

                        pdf.image(caminho_grafico_eq_sub, w=180)
                        pdf.ln(2)
                    except Exception as e:
                        print("Erro ao gerar gráfico de subdimensões da equipe:", e)


            renderizar_bloco_personalizado(pdf, partes[1])
        else:
            renderizar_bloco_personalizado(pdf, guia)

        pdf.output(caminho_local)

        # JUNTAR COM RELATÓRIO ANALÍTICO
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
            merger.append(caminho_local)
            merger.append(caminho_pdf_analitico)
            merger.write(caminho_final)
            merger.close()
            caminho_local = caminho_final

        file_metadata = {"name": nome_pdf, "parents": [id_lider]}
        media = MediaIoBaseUpload(open(caminho_local, "rb"), mimetype="application/pdf")
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        return jsonify({"mensagem": f"✅ Parecer salvo no Drive: {nome_pdf}"})

    except Exception as e:
        return jsonify({"erro": str(e)}), 500
