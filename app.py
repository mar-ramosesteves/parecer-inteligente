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


def carregar_prompt_leadertrack():
    """
    Carrega o prompt base do Assistente Inteligente Leadertrack.

    Este arquivo contém as regras que impedem a IA de sair do contexto
    do método Leadertrack.
    """
    try:
        with open("prompt_leadertrack_ia.txt", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return """
ERRO: O arquivo prompt_leadertrack_ia.txt não foi encontrado.
Verifique se ele está no mesmo nível do app.py.
"""
    except Exception as e:
        return f"""
ERRO: Não foi possível carregar o prompt Leadertrack.
Detalhe técnico: {str(e)}
"""



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
    if resp.status_code == 200:
        dados = resp.json()
        if dados:
            dados_json = dados[0].get("dados_json")
            if isinstance(dados_json, str):
                try:
                    dados_json = json.loads(dados_json)
                except Exception as e:
                    print("Erro ao converter dados_json:", e)
                    return None
            return dados_json
    return None

def buscar_json_microambiente(tipo_relatorio, empresa, rodada, email_lider):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    url = f"{SUPABASE_REST_URL}/relatorios_gerados"
    params = {
        "empresa": f"ilike.{empresa}",
        "codrodada": f"ilike.{rodada}",
        "emaillider": f"ilike.{email_lider}",
        "tipo_relatorio": f"eq.{tipo_relatorio}",
        "order": "data_criacao.desc",
        "limit": 1
    }
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code == 200:
        dados = resp.json()
        if dados:
            dados_json = dados[0].get("dados_json")
            if isinstance(dados_json, str):
                try:
                    dados_json = json.loads(dados_json)
                except Exception as e:
                    print("Erro ao converter dados_json:", e)
                    return None
            return dados_json
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
        if json_auto_vs_equipe and isinstance(json_auto_vs_equipe, str):
            try:
                json_auto_vs_equipe = json.loads(json_auto_vs_equipe)
            except:
                json_auto_vs_equipe = None

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
            ax.bar(x - 0.2, auto, width=0.4, label="Autoavaliação", color="orange")
            ax.bar(x + 0.2, equipe, width=0.4, label="Equipe", color="lightblue")
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

        dados_retorno = {
            "titulo": "PARECER INTELIGENTE - MICROAMBIENTE",
            "subtitulo": f"{empresa.upper()} / {rodada.upper()} / {email_lider}",
            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "conteudo_html": guia
        }

        salvar_relatorio_analitico_no_supabase(dados_retorno, empresa, rodada, email_lider, tipo_relatorio)

        response = jsonify(dados_retorno)
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 200

    except Exception as e:
        print("Erro no parecer IA microambiente:", e)
        response = jsonify({"erro": str(e)})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 500

@app.route("/buscar-json-supabase", methods=["POST", "OPTIONS"])
def buscar_json_supabase_rota():
    if request.method == "OPTIONS":
        response = jsonify({'status': 'CORS preflight OK'})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        return response

    try:
        dados = request.get_json()
        tipo_relatorio = dados["tipo_relatorio"]
        empresa = dados["empresa"].lower()
        codrodada = dados["codrodada"].lower()
        emailLider = dados["emailLider"].lower()

        print(f"🔍 Buscando dados: {tipo_relatorio}, {empresa}, {codrodada}, {emailLider}")

        dados_json = buscar_json_supabase(tipo_relatorio, empresa, codrodada, emailLider)

        if dados_json:
            response = jsonify(dados_json)
            response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
            return response, 200
        else:
            response = jsonify({"erro": "Dados não encontrados"})
            response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
            return response, 404

    except Exception as e:
        print("Erro ao buscar JSON:", e)
        response = jsonify({"erro": str(e)})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 500

@app.route("/buscar-json-microambiente", methods=["POST", "OPTIONS"])
def buscar_json_microambiente_rota():
    if request.method == "OPTIONS":
        response = jsonify({'status': 'CORS preflight OK'})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        return response

    try:
        dados = request.get_json()
        tipo_relatorio = dados["tipo_relatorio"]
        empresa = dados["empresa"].lower()
        codrodada = dados["codrodada"].lower()
        emailLider = dados["emailLider"].lower()

        print(f"🔍 Buscando dados microambiente: {tipo_relatorio}, {empresa}, {codrodada}, {emailLider}")

        dados_json = buscar_json_microambiente(tipo_relatorio, empresa, codrodada, emailLider)

        if dados_json:
            response = jsonify(dados_json)
            response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
            return response, 200
        else:
            response = jsonify({"erro": "Dados não encontrados"})
            response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
            return response, 404

    except Exception as e:
        print("Erro ao buscar JSON microambiente:", e)
        response = jsonify({"erro": str(e)})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 500

@app.route("/teste-prompt-leadertrack", methods=["GET"])
def teste_prompt_leadertrack():
    try:
        prompt = carregar_prompt_leadertrack()

        return jsonify({
            "status": "ok",
            "mensagem": "Prompt Leadertrack carregado com sucesso.",
            "tamanho_caracteres": len(prompt),
            "inicio_prompt": prompt[:300]
        }), 200

    except Exception as e:
        return jsonify({
            "status": "erro",
            "mensagem": str(e)
        }), 500

@app.route("/chat-leadertrack", methods=["POST", "OPTIONS"])
def chat_leadertrack():
    if request.method == "OPTIONS":
        response = jsonify({'status': 'CORS preflight OK'})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        return response

    try:
        dados = request.get_json()

        empresa = dados.get("empresa", "").lower()
        codrodada = dados.get("codrodada", "").lower()
        email_lider = dados.get("emailLider", "").lower()
        pergunta = dados.get("pergunta", "")

        if not empresa or not codrodada or not email_lider or not pergunta:
            response = jsonify({
                "erro": "Campos obrigatórios ausentes.",
                "campos_necessarios": [
                    "empresa",
                    "codrodada",
                    "emailLider",
                    "pergunta"
                ]
            })
            response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
            return response, 400

        prompt_base = carregar_prompt_leadertrack()

        # Busca os dados reais já gerados pelo Leadertrack no Supabase
        dados_arquetipos = buscar_json_supabase(
            "arquetipos_grafico_comparativo",
            empresa,
            codrodada,
            email_lider
        )
        
        dados_microambiente = buscar_json_microambiente(
            "microambiente_grafico_barras",
            empresa,
            codrodada,
            email_lider
        )
        
        dados_saude_emocional = buscar_json_supabase(
            "saude_emocional_grafico_barras",
            empresa,
            codrodada,
            email_lider
        )
        
        resposta_teste = f"""
        Assistente Leadertrack ativo.
        
        Recebi a sua pergunta:
        {pergunta}
        
        Contexto recebido:
        Empresa: {empresa}
        Rodada: {codrodada}
        Líder: {email_lider}
        
        Prompt Leadertrack:
        {len(prompt_base)} caracteres carregados.
        
        Dados encontrados no Supabase:
        
        Arquétipos:
        {"ENCONTRADO" if dados_arquetipos else "NÃO ENCONTRADO"}
        
        Microambiente:
        {"ENCONTRADO" if dados_microambiente else "NÃO ENCONTRADO"}
        
        Saúde Emocional:
        {"ENCONTRADO" if dados_saude_emocional else "NÃO ENCONTRADO"}
        
        Esta ainda é uma resposta de teste.
        No próximo passo, estes dados serão enviados para a IA de forma controlada.
        """
        response = jsonify({
            "status": "ok",
            "resposta": resposta_teste
        })
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 200

    except Exception as e:
        print("Erro no chat Leadertrack:", e)
        response = jsonify({"erro": str(e)})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 500


if __name__ == "__main__":
    app.run(debug=True)
