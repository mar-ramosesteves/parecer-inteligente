from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
from datetime import datetime
import matplotlib.pyplot as plt
import base64
import io
import numpy as np
import requests

app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "https://gestor.thehrkey.tech"}})

SUPABASE_REST_URL = os.getenv("SUPABASE_REST_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def salvar_relatorio_analitico_no_supabase(dados, empresa, codrodada, email_lider, tipo):
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

def buscar_json_supabase(tipo_relatorio, empresa, rodada, email_lider):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    filtro = f"?empresa=eq.{empresa}&codrodada=eq.{rodada}&emaillider=eq.{email_lider}&tipo_relatorio=eq.{tipo_relatorio}&order=data_criacao.desc&limit=1"
    url = f"{SUPABASE_REST_URL}/relatorios_gerados{filtro}"
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        dados = resp.json()
        if dados:
            return dados[0].get("dados_json")
    return None

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

        with open("guias_completos_unificados.txt", "r", encoding="utf-8") as f:
            texto = f.read()
        inicio = texto.find("##### INICIO ARQUETIPOS #####")
        fim = texto.find("##### FIM ARQUETIPOS #####")
        guia = texto[inicio + len("##### INICIO ARQUETIPOS #####"):fim].strip() if inicio != -1 and fim != -1 else "Guia de Arquétipos não encontrado."

        marcador = "Abaixo, o resultado da análise de Arquétipos relativa ao modo como voce lidera em sua visão, comparado com a média da visão de sua equipe direta:"
        partes = guia.split(marcador)

        imagem_base64 = ""
        if json_auto_vs_equipe:
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

        bloco_html = partes[0] + f"<br><br>{marcador}<br><br><img src='data:image/png;base64,{imagem_base64}' style='width:100%;max-width:800px;'><br><br>" + partes[1] if len(partes) == 2 else guia

        dados_retorno = {
            "titulo": "ARQUÉTIPOS DE GESTÃO",
            "subtitulo": f"{empresa.upper()} / {rodada.upper()} / {email_lider}",
            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "conteudo_html": bloco_html
        }

        salvar_relatorio_analitico_no_supabase(dados_retorno, empresa, rodada, email_lider, tipo_relatorio)

        response = jsonify(dados_retorno)
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 200

    except Exception as e:
        print("Erro no parecer IA arquetipos:", e)
        response = jsonify({"erro": str(e)})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 500




# ---------- ROTA PRINCIPAL ----------
@app.route("/emitir-parecer-microambiente", methods=["POST", "OPTIONS"])
def emitir_parecer_microambiente():
    if request.method == "OPTIONS":
        response = jsonify({'status': 'CORS preflight OK'})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        return response

    try:
        dados_requisicao = request.get_json()
        empresa = dados_requisicao["empresa"].lower()
        rodada = dados_requisicao["codrodada"].lower()
        email_lider = dados_requisicao["emailLider"].lower()

        # --- 1. Carregar o guia base do arquivo local ---
        try:
            with open("guias_completos_unificados.txt", "r", encoding="utf-8") as f:
                guia_texto_completo = f.read()
            
            marcador_inicio = "##### INICIO MICROAMBIENTE #####"
            marcador_fim = "##### FIM MICROAMBIENTE #####"
            inicio = guia_texto_completo.find(marcador_inicio)
            fim = guia_texto_completo.find(marcador_fim)
            
            conteudo_parecer = guia_texto_completo[inicio + len(marcador_inicio):fim].strip() if inicio != -1 and fim != -1 else "Guia de Microambiente não encontrado."

        except FileNotFoundError:
            conteudo_parecer = "Erro: Arquivo 'guias_completos_unificados.txt' não encontrado no servidor."
            print(f"ERRO: Arquivo 'guias_completos_unificados.txt' não encontrado.")
        except Exception as e:
            conteudo_parecer = f"Erro ao carregar o guia de microambiente: {str(e)}"
            print(f"ERRO: Ao carregar guia de microambiente: {str(e)}")
        
        # --- 2. Preparar o HTML do IFRAME para o gráfico de Dimensões (linhas) ---
        # Foco APENAS neste gráfico, como você solicitou.
        endpoint_pagina_grafico_dimensoes = "microambiente_grafico_mediaequipe_dimensao" 
        base_url_graficos = "https://microambiente-avaliacao.onrender.com/"
        
        # Constrói a URL completa para o iframe do gráfico de dimensões
        url_iframe_dimensoes = f"{base_url_graficos}{endpoint_pagina_grafico_dimensoes}?empresa={empresa}&codrodada={rodada}&emailLider={email_lider}"
        
        # Cria a tag <iframe> com estilos de DEBUG visual FORTE
        # Esses estilos devem ser removidos APÓS o gráfico aparecer.
        iframe_html_dimensoes = f'''
        <br>
        <iframe src="{url_iframe_dimensoes}" 
                style="width:100%;height:500px;border:5px solid red !important; display:block !important; background-color:yellow !important;"
                title="Gráfico de Dimensões da Equipe">
        </iframe>
        <br>
        '''

        # --- 3. Injetar o IFRAME no conteúdo do parecer no LOCAL EXATO ---
        # Este é o marcador no texto do guia onde o gráfico será inserido.
        marcador_no_texto = "Abaixo, os gráficos de dimensões e subdimensões de microambiente na percepção de sua equipe:"
        
        # Substitui o marcador no texto pelo marcador + o iframe.
        if marcador_no_texto in conteudo_parecer:
            conteudo_parecer_final = conteudo_parecer.replace(marcador_no_texto, f"{marcador_no_texto}{iframe_html_dimensoes}")
        else:
            # Se o marcador não for encontrado, adiciona o gráfico no final do parecer para depuração
            conteudo_parecer_final = conteudo_parecer + iframe_html_dimensoes
            print(f"AVISO: Marcador '{marcador_no_texto}' não encontrado no guia. Gráfico adicionado ao final do parecer.")


        # --- 4. Montar a resposta final para o frontend ---
        dados_retorno = {
            "titulo": "PARECER INTELIGENTE - MICROAMBIENTE",
            "subtitulo": f"{empresa.upper()} / {rodada.upper()} / {email_lider}",
            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "conteudo_html": conteudo_parecer_final # O texto do parecer COM o iframe injetado
        }

        # --- 5. Salvar o parecer (com a referência aos gráficos) no Supabase ---
        tipo_relatorio_parecer = "microambiente_parecer_ia"
        salvar_relatorio_analitico_no_supabase(dados_retorno, empresa, rodada, email_lider, tipo_relatorio_parecer)

        response = jsonify(dados_retorno)
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 200

    except requests.exceptions.RequestException as e:
        print(f"Erro de comunicação com o Supabase ao buscar ou salvar parecer: {str(e)}")
        detailed_traceback = traceback.format_exc()
        print(f"TRACEBACK COMPLETO:\n{detailed_traceback}")
        response = jsonify({"erro": f"Erro de comunicação com o Supabase: {str(e)}", "debug_info": "Verifique os logs."})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 500
    except Exception as e:
        print("Erro geral no parecer IA microambiente:", e)
        detailed_traceback = traceback.format_exc()
        print(f"TRACEBACK COMPLETO:\n{detailed_traceback}")
        response = jsonify({"erro": str(e), "debug_info": "Verifique os logs para detalhes."})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 500


