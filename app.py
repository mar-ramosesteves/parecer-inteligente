from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
from datetime import datetime
import requests
import base64
import io
import matplotlib.pyplot as plt
import numpy as np

app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "https://gestor.thehrkey.tech"}})

SUPABASE_REST_URL = os.getenv("SUPABASE_REST_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


from flask import render_template

@app.route("/microambiente_grafico_autoavaliacao_dimensao")
def microambiente_grafico_autoavaliacao_dimensao():
    return render_template("microambiente_grafico_autoavaliacao_dimensao.html")


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
    url = f"{SUPABASE_REST_URL}/relatorios_gerados"
    params = {
        "empresa": f"eq.{empresa}",
        "codrodada": f"eq.{rodada}",
        "emaillider": f"eq.{email_lider}",
        "tipo_relatorio": f"eq.{tipo_relatorio}",
        "order": "data_criacao.desc",
        "limit": 1
    }
    resp = requests.get(url, headers=headers, params=params)
    print("📦 JSON buscado:", resp.status_code, resp.text)
    

    if resp.status_code == 200:
        dados = resp.json()
        if dados:
            return dados[0].get("dados_json")
    return None

def gerar_grafico_base64(dados):
    arquetipos = dados.get("arquetipos", [])
    auto = [dados["autoavaliacao"].get(a, 0) for a in arquetipos]
    equipe = [dados["mediaEquipe"].get(a, 0) for a in arquetipos]
    x = np.arange(len(arquetipos))

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - 0.2, auto, width=0.4, label="Autoavaliação", color='#00b0f0')
    ax.bar(x + 0.2, equipe, width=0.4, label="Média da Equipe", color='#f7931e')

    for i, (a, e) in enumerate(zip(auto, equipe)):
        ax.text(i - 0.2, a + 1, f"{a:.0f}%", ha='center', fontsize=8)
        ax.text(i + 0.2, e + 1, f"{e:.0f}%", ha='center', fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(arquetipos, rotation=45)
    ax.set_ylim(0, 100)
    ax.axhline(50, color='gray', linestyle=':', linewidth=1)
    ax.text(len(x)-0.5, 52, "Suporte", color='gray', fontsize=8, ha='right')
    ax.axhline(60, color='gray', linestyle='--', linewidth=1)
    ax.text(len(x)-0.5, 62, "Dominante", color='gray', fontsize=8, ha='right')
    ax.set_title(dados.get("titulo", ""), fontsize=12, weight='bold')
    ax.legend()
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close()
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    print("🧪 Tamanho do gráfico gerado (base64):", len(img_base64))
    return img_base64

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

        with open("guias_completos_unificados.txt", "r", encoding="utf-8") as f:
            texto = f.read()
        inicio = texto.find("##### INICIO ARQUETIPOS #####")
        fim = texto.find("##### FIM ARQUETIPOS #####")
        guia = texto[inicio + len("##### INICIO ARQUETIPOS #####"):fim].strip() if inicio != -1 and fim != -1 else "Guia de Arquétipos não encontrado."

        conteudo_html = guia
        print("GUIA CARREGADO:", conteudo_html[:500])


        marcador = "Abaixo, o resultado da análise de Arquétipos relativa ao modo como voce lidera em sua visão, comparado com a média da visão de sua equipe direta:"
        partes = guia.split(marcador)


        imagem_base64 = ""
        grafico = buscar_json_supabase("arquetipos_grafico_comparativo", empresa, rodada, email_lider)
        print("JSON DO GRÁFICO:", grafico)

        if grafico:
            imagem_base64 = gerar_grafico_base64(grafico)

        if len(partes) == 2:
            conteudo_html = partes[0] + f"{marcador}\n<br><br><img src=\"data:image/png;base64,{imagem_base64}\" style=\"width:100%;max-width:800px;\"><br><br>" + partes[1]


        dados_retorno = {
            "titulo": "ARQUÉTIPOS DE GESTÃO",
            "subtitulo": f"{empresa.upper()} / {rodada.upper()} / {email_lider}",
            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "conteudo_html": conteudo_html
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
        dados = request.get_json()
        empresa = dados["empresa"].lower()
        rodada = dados["codrodada"].lower()
        email_lider = dados["emailLider"].lower()
        tipo_relatorio = "microambiente_parecer_ia"

        with open("guias_completos_unificados.txt", "r", encoding="utf-8") as f:
            texto = f.read()
        inicio = texto.find("##### INICIO MICROAMBIENTE #####")
        fim = texto.find("##### FIM MICROAMBIENTE #####")
        guia = texto[inicio + len("##### INICIO MICROAMBIENTE #####"):fim].strip() if inicio != -1 and fim != -1 else "Guia de Microambiente não encontrado."

        conteudo_html = guia

        # Frases que serão substituídas por iframes com as rotas reais
        frases_graficos = {
    "Abaixo, os gráficos de dimensões e subdimensões de microambiente na percepção de sua equipe:":
        [
            "microambiente_grafico_mediaequipe_dimensao",
            "microambiente_grafico_mediaequipe_subdimensao"
        ],
    "E abaixo, os gráficos de dimensões e subdimensões de microambiente na sua percepção:":
        [
            "microambiente_grafico_autoavaliacao_dimensao",
            "microambiente_grafico_autoavaliacao_subdimensao"
        ],
    "Abaixo, o seu resultado dimensão e subdimensão, com o objetivo de evidenciar os GAP's que devemn ser priorizados, na visão de sua equipe:":
        ["microambiente_waterfall_gaps"],
    "Abaixo, o termômetro de GAP's, que serve para determinar o tipo de microambiente que você proporciona à sua equipe.":
        ["microambiente_termometro_gaps"],
    "A seguir, o relatório analítico por afirmação, comparando o que a sua equipe julga ser ideal e como eles gostariam que fosse, divididos por dimensões e subdimensões de microambiente. Boa leitura!":
        ["microambiente_analitico"]
}

        for frase, rotas in frases_graficos.items():
            blocos_iframe = ""
            for rota in rotas:
                blocos_iframe += f'<br><div class="grafico" data-tipo="{rota}" data-empresa="{empresa}" data-rodada="{rodada}" data-email="{email_lider}"></div><br>'

            conteudo_html = conteudo_html.replace(frase, f"{frase}\n{blocos_iframe}")

        dados_retorno = {
            "titulo": "PARECER MICROAMBIENTE",
            "subtitulo": f"{empresa.upper()} / {rodada.upper()} / {email_lider}",
            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "conteudo_html": conteudo_html
        }

        salvar_relatorio_analitico_no_supabase(dados_retorno, empresa, rodada, email_lider, tipo_relatorio)

        response = jsonify(dados_retorno)
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 200

    except Exception as e:
        print("❌ Erro no parecer IA microambiente:", e)
        response = jsonify({"erro": str(e)})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 500



