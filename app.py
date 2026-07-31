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
from openai import OpenAI
from leadertrack_devolutivas import (
    archetype_summary,
    build_diagnostic_prompt,
    build_empty_devolutiva,
    build_history_event,
    build_performance_goal_suggestion,
    build_weekly_prompt,
    filter_gaps,
    low_reference_affirmations,
    microenvironment_affirmations,
    parse_json_response,
    slug,
)

app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "https://gestor.thehrkey.tech"}})

SUPABASE_REST_URL = os.getenv("SUPABASE_REST_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)


def bool_param(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in ("1", "true", "sim", "yes", "y")


def leadertrack_gap_id(gap):
    return f"{gap.get('questao')}_{slug(gap.get('dimensao'))}_{slug(gap.get('subdimensao'))}"


def selecionar_gap_leadertrack(todas_afirmacoes, dados):
    gap_enviado = dados.get("gap")
    if isinstance(gap_enviado, dict) and gap_enviado.get("questao"):
        return gap_enviado

    gap_id = str(dados.get("gapId") or dados.get("gap_id") or "").strip()
    questao = str(dados.get("questao") or "").strip().lower()
    dimensao = str(dados.get("dimensao") or "").strip().lower()
    subdimensao = str(dados.get("subdimensao") or "").strip().lower()

    for gap in todas_afirmacoes:
        if gap_id and leadertrack_gap_id(gap) == gap_id:
            return gap
        if questao and str(gap.get("questao") or "").strip().lower() == questao:
            if dimensao and str(gap.get("dimensao") or "").strip().lower() != dimensao:
                continue
            if subdimensao and str(gap.get("subdimensao") or "").strip().lower() != subdimensao:
                continue
            return gap
    return None


def intervalo_etapa_leadertrack(etapa, dados):
    etapa = str(etapa or "diagnostico").strip().lower()
    mapa = {
        "semanas_1_4": (1, 4),
        "1_4": (1, 4),
        "semanas_5_8": (5, 8),
        "5_8": (5, 8),
        "semanas_9_12": (9, 12),
        "9_12": (9, 12),
    }
    if etapa in mapa:
        return mapa[etapa]
    if dados.get("semanaInicio") and dados.get("semanaFim"):
        return int(dados["semanaInicio"]), int(dados["semanaFim"])
    return None


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

def gerar_resposta_ia_leadertrack(
    pergunta,
    prompt_base,
    empresa,
    codrodada,
    email_lider,
    pagina_atual,
    url_atual,    
    dados_arquetipos_comparativo,
    dados_arquetipos_analitico,
    guia_arquetipos,
    dados_microambiente_analitico,
    dados_microambiente_subdimensao,
    dados_microambiente_termometro_gaps,
    dados_microambiente_waterfall_gaps,
    guia_microambiente
):
    """
    Gera uma resposta do Assistente Leadertrack com base apenas nos dados fornecidos.
    """

    contexto_leadertrack = {
        "empresa": empresa,
        "codrodada": codrodada,
        "email_lider": email_lider,
        "pagina_atual": pagina_atual,
        "url_atual": url_atual,
        "pergunta_usuario": pergunta,        
        "dados_disponiveis": {
            "arquetipos_grafico_comparativo": dados_arquetipos_comparativo,
            "arquetipos_analitico": dados_arquetipos_analitico,
            "arquetipos_parecer_ia_guia": guia_arquetipos,
            "microambiente_analitico": dados_microambiente_analitico,
            "microambiente_grafico_mediaequipe_subdimensao": dados_microambiente_subdimensao,
            "microambiente_termometro_gaps": dados_microambiente_termometro_gaps,
            "microambiente_waterfall_gaps": dados_microambiente_waterfall_gaps,
            "microambiente_parecer_ia_guia": guia_microambiente
        }
    }

    resposta = openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": prompt_base
            },
            {
                "role": "user",
                "content": (
                    "Responda à pergunta do usuário usando exclusivamente o contexto JSON abaixo. "
                    "Não invente dados. Não use teorias externas. "
                    "Se algum dado não estiver disponível, informe a limitação.\n\n"
                    f"CONTEXTO LEADERTRACK:\n{json.dumps(contexto_leadertrack, ensure_ascii=False)}"
                )
            }
        ]
    )

    return resposta.choices[0].message.content



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


def supabase_headers(prefer_return=True):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer_return:
        headers["Prefer"] = "return=representation"
    return headers


def supabase_insert(table, payload):
    if not SUPABASE_REST_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase nao configurado no ambiente.")
    url = f"{SUPABASE_REST_URL}/{table}"
    response = requests.post(url, headers=supabase_headers(), json=payload, timeout=60)
    if response.status_code >= 300:
        raise RuntimeError(f"Erro ao salvar em {table}: HTTP {response.status_code} - {response.text}")
    data = response.json()
    if isinstance(data, list) and data:
        return data[0]
    return data


def persistir_devolutiva_leadertrack(devolutiva, gerado_por=None):
    contexto_ids = devolutiva.get("contexto_ids") or {}
    parent_payload = {
        "empresa": devolutiva.get("empresa"),
        "contexto": devolutiva.get("contexto"),
        "cliente_id": contexto_ids.get("cliente_id"),
        "holding_id": contexto_ids.get("holding_id"),
        "empresa_id": contexto_ids.get("empresa_id"),
        "filial_id": contexto_ids.get("filial_id"),
        "codrodada": devolutiva.get("codrodada"),
        "email_lider": devolutiva.get("email_lider"),
        "nome_lider": devolutiva.get("nome_lider"),
        "status": "rascunho_gerado",
        "limite_gaps": len(devolutiva.get("gaps_priorizados") or []),
        "maximo_gaps_por_ciclo": (devolutiva.get("faseamento_anual_sugerido") or {}).get("maximo_recomendado_por_ciclo", 4),
        "gap_minimo_percentual": (devolutiva.get("criterios_de_leitura") or {}).get("gap_minimo_percentual"),
        "baixa_referencia_threshold_percentual": (devolutiva.get("criterios_de_leitura") or {}).get("baixa_referencia_threshold_percentual"),
        "dados_entrada_resumo": {
            "arquetipos": devolutiva.get("arquetipos"),
            "resumo_severidade": devolutiva.get("resumo_severidade"),
            "criterios_de_leitura": devolutiva.get("criterios_de_leitura"),
        },
        "todas_afirmacoes_microambiente": devolutiva.get("todas_afirmacoes_microambiente") or [],
        "baixa_referencia": devolutiva.get("baixa_referencia") or [],
        "faseamento_anual_sugerido": devolutiva.get("faseamento_anual_sugerido") or {},
        "resposta_leadertrackbot_json": devolutiva,
        "pdi_enviado_para_modulo_pdi": False,
        "meta_desempenho_sugerida": any((pdi.get("meta_desempenho_sugerida") for pdi in devolutiva.get("pdis") or [])),
        "gerado_por": gerado_por,
    }
    saved_parent = supabase_insert("leadertrack_devolutivas", parent_payload)
    devolutiva_id = saved_parent.get("id")

    for pdi in devolutiva.get("pdis") or []:
        gap = pdi.get("gap") or {}
        gap_id = pdi.get("gap_id")
        for semana in pdi.get("plano_12_semanas") or []:
            supabase_insert("leadertrack_pdi_acompanhamento", {
            "devolutiva_id": devolutiva_id,
            "cliente_id": contexto_ids.get("cliente_id"),
            "holding_id": contexto_ids.get("holding_id"),
            "empresa_id": contexto_ids.get("empresa_id"),
            "filial_id": contexto_ids.get("filial_id"),
            "gap_id": gap_id,
                "questao": gap.get("questao"),
                "dimensao": gap.get("dimensao"),
                "subdimensao": gap.get("subdimensao"),
                "afirmacao": gap.get("afirmacao"),
                "semana": semana.get("semana"),
                "foco_da_semana": semana.get("foco_da_semana"),
                "objetivo": semana.get("objetivo"),
                "prazo": semana.get("prazo"),
                "status": semana.get("status") or "nao_iniciado",
                "acoes_praticas": semana.get("acoes_praticas") or [],
                "formato_sugerido": semana.get("formato_sugerido"),
                "tarefa_do_lider": semana.get("tarefa_do_lider") or [],
                "tarefa_da_equipe": semana.get("tarefa_da_equipe") or [],
                "perguntas_para_equipe": semana.get("perguntas_para_equipe") or [],
                "o_que_mostrar_para_equipe": semana.get("o_que_mostrar_para_equipe") or [],
                "o_que_nao_mostrar_para_equipe": semana.get("o_que_nao_mostrar_para_equipe") or [],
                "indicador": semana.get("indicador"),
                "evidencia_esperada": semana.get("evidencia_esperada"),
                "resultado_esperado": semana.get("resultado_esperado"),
                "indicadores_operacionais_relacionados": semana.get("indicadores_operacionais_relacionados") or [],
                "metrica_operacional_base": semana.get("metrica_operacional_base"),
                "evolucao_operacional_observada": semana.get("evolucao_operacional_observada"),
                "resultado_obtido": semana.get("resultado_obtido"),
                "observacoes_de_evolucao": semana.get("observacoes_de_evolucao"),
            })

        historico = dict(pdi.get("historico_evento_inicial") or {})
        if historico:
            historico["devolutiva_id"] = devolutiva_id
            historico["cliente_id"] = contexto_ids.get("cliente_id")
            historico["holding_id"] = contexto_ids.get("holding_id")
            historico["empresa_id"] = contexto_ids.get("empresa_id")
            historico["filial_id"] = contexto_ids.get("filial_id")
            supabase_insert("leadertrack_pdi_historico", historico)

        meta = dict(pdi.get("meta_desempenho_sugerida") or {})
        if meta:
            meta["devolutiva_id"] = devolutiva_id
            meta["cliente_id"] = contexto_ids.get("cliente_id")
            meta["holding_id"] = contexto_ids.get("holding_id")
            meta["empresa_id"] = contexto_ids.get("empresa_id")
            meta["filial_id"] = contexto_ids.get("filial_id")
            supabase_insert("leadertrack_pdi_meta_desempenho", meta)

        indicadores = (
            (pdi.get("diagnostico") or {})
            .get("indicadores_de_efetividade", {})
            .get("indicadores_operacionais_sugeridos", [])
        )
        for indicador in indicadores:
            supabase_insert("leadertrack_pdi_indicadores_operacionais", {
                "devolutiva_id": devolutiva_id,
                "cliente_id": contexto_ids.get("cliente_id"),
                "holding_id": contexto_ids.get("holding_id"),
                "empresa_id": contexto_ids.get("empresa_id"),
                "filial_id": contexto_ids.get("filial_id"),
                "gap_id": gap_id,
                "nome_indicador": indicador,
                "fonte": "sugerido_leadertrackbot",
            })

    return {
        "devolutiva_id": devolutiva_id,
        "status_persistencia": "salvo_no_supabase",
    }

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
        pagina_atual = dados.get("paginaAtual", "")
        url_atual = dados.get("urlAtual", "")

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

        # Busca os dados reais de Arquétipos já gerados pelo Leadertrack no Supabase
        dados_arquetipos_comparativo = buscar_json_supabase(
            "arquetipos_grafico_comparativo",
            empresa,
            codrodada,
            email_lider
        )
        
        dados_arquetipos_analitico = buscar_json_supabase(
            "arquetipos_analitico",
            empresa,
            codrodada,
            email_lider
        )
        
        guia_arquetipos = buscar_json_supabase(
            "arquetipos_parecer_ia",
            empresa,
            codrodada,
            email_lider
        )
        
        # Busca os dados reais de Microambiente já gerados pelo Leadertrack no Supabase
        dados_microambiente_analitico = buscar_json_microambiente(
            "microambiente_analitico",
            empresa,
            codrodada,
            email_lider
        )
        
        dados_microambiente_subdimensao = buscar_json_microambiente(
            "microambiente_grafico_mediaequipe_subdimensao",
            empresa,
            codrodada,
            email_lider
        )
        
        dados_microambiente_termometro_gaps = buscar_json_microambiente(
            "microambiente_termometro_gaps",
            empresa,
            codrodada,
            email_lider
        )
        
        dados_microambiente_waterfall_gaps = buscar_json_microambiente(
            "microambiente_waterfall_gaps",
            empresa,
            codrodada,
            email_lider
        )
        
        guia_microambiente = buscar_json_microambiente(
            "microambiente_parecer_ia",
            empresa,
            codrodada,
            email_lider
        )
        
        resposta_ia = gerar_resposta_ia_leadertrack(
            pergunta=pergunta,
            prompt_base=prompt_base,
            empresa=empresa,
            codrodada=codrodada,
            email_lider=email_lider,
            pagina_atual=pagina_atual,
            url_atual=url_atual,            
            dados_arquetipos_comparativo=dados_arquetipos_comparativo,
            dados_arquetipos_analitico=dados_arquetipos_analitico,
            guia_arquetipos=guia_arquetipos,
            dados_microambiente_analitico=dados_microambiente_analitico,
            dados_microambiente_subdimensao=dados_microambiente_subdimensao,
            dados_microambiente_termometro_gaps=dados_microambiente_termometro_gaps,
            dados_microambiente_waterfall_gaps=dados_microambiente_waterfall_gaps,
            guia_microambiente=guia_microambiente
        )

        
        response = jsonify({
            "status": "ok",
            "resposta": resposta_ia
        })

        
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 200

    except Exception as e:
        print("Erro no chat Leadertrack:", e)
        response = jsonify({"erro": str(e)})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 500


@app.route("/gerar-devolutiva-leadertrack", methods=["POST", "OPTIONS"])
def gerar_devolutiva_leadertrack():
    if request.method == "OPTIONS":
        response = jsonify({'status': 'CORS preflight OK'})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        response.headers["Access-Control-Allow-Methods"] = "POST,OPTIONS"
        return response

    try:
        dados = request.get_json() or {}
        empresa = dados.get("empresa", "").lower()
        codrodada = dados.get("codrodada", "").lower()
        email_lider = dados.get("emailLider", "").lower()
        contexto = dados.get("contexto", "")
        contexto_ids = {
            "cliente_id": dados.get("cliente_id") or dados.get("clienteId"),
            "holding_id": dados.get("holding_id") or dados.get("holdingId"),
            "empresa_id": dados.get("empresa_id") or dados.get("empresaId"),
            "filial_id": dados.get("filial_id") or dados.get("filialId"),
        }
        nome_lider = dados.get("nomeLider", "")
        gap_minimo = float(dados.get("gapMinimo", 20) or 20)
        baixa_referencia_threshold = float(dados.get("baixaReferenciaThreshold", 70) or 70)
        limite_gaps = dados.get("limiteGaps")
        limite_gaps = int(limite_gaps) if limite_gaps not in (None, "", 0, "0") else None
        maximo_gaps_por_ciclo = int(dados.get("maximoGapsPorCiclo", 4) or 4)
        gerar_apenas_primeiro_ciclo = bool_param(dados.get("gerarApenasPrimeiroCiclo"), True)
        gerar_planos_com_ia = bool_param(dados.get("gerarPlanosComIA"), False)
        persistir = bool_param(dados.get("persistir"), False)
        gerado_por = dados.get("geradoPor")
        indicadores_disponiveis = dados.get("indicadoresOperacionaisDisponiveis", [])

        if not empresa or not codrodada or not email_lider:
            response = jsonify({
                "erro": "Campos obrigatorios ausentes.",
                "campos_necessarios": ["empresa", "codrodada", "emailLider"]
            })
            response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
            return response, 400

        if persistir and not gerar_planos_com_ia:
            response = jsonify({
                "erro": "Persistencia bloqueada para devolutiva sem planos gerados pela IA.",
                "orientacao": "Envie gerarPlanosComIA=true apenas quando for gerar e salvar um PDI validado."
            })
            response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
            return response, 400

        prompt_base = carregar_prompt_leadertrack() if gerar_planos_com_ia else ""

        dados_arquetipos_comparativo = buscar_json_supabase(
            "arquetipos_grafico_comparativo", empresa, codrodada, email_lider
        )
        dados_arquetipos_analitico = buscar_json_supabase(
            "arquetipos_analitico", empresa, codrodada, email_lider
        )
        guia_arquetipos = buscar_json_supabase(
            "arquetipos_parecer_ia", empresa, codrodada, email_lider
        )
        dados_microambiente_analitico = buscar_json_microambiente(
            "microambiente_analitico", empresa, codrodada, email_lider
        )
        dados_microambiente_subdimensao = buscar_json_microambiente(
            "microambiente_grafico_mediaequipe_subdimensao", empresa, codrodada, email_lider
        )
        dados_microambiente_termometro_gaps = buscar_json_microambiente(
            "microambiente_termometro_gaps", empresa, codrodada, email_lider
        )
        dados_microambiente_waterfall_gaps = buscar_json_microambiente(
            "microambiente_waterfall_gaps", empresa, codrodada, email_lider
        )
        guia_microambiente = buscar_json_microambiente(
            "microambiente_parecer_ia", empresa, codrodada, email_lider
        )

        if not dados_arquetipos_comparativo or not dados_microambiente_analitico:
            response = jsonify({
                "erro": "Dados LeaderTrack insuficientes para gerar devolutiva.",
                "dados_encontrados": {
                    "arquetipos_grafico_comparativo": bool(dados_arquetipos_comparativo),
                    "microambiente_analitico": bool(dados_microambiente_analitico),
                }
            })
            response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
            return response, 404

        arquetipos = archetype_summary(dados_arquetipos_comparativo)
        todas_afirmacoes = microenvironment_affirmations(dados_microambiente_analitico)
        gaps = filter_gaps(todas_afirmacoes, gap_minimo)
        if limite_gaps:
            gaps = gaps[:limite_gaps]
        baixa_referencia = low_reference_affirmations(todas_afirmacoes, baixa_referencia_threshold)
        gaps_para_gerar = gaps[:maximo_gaps_por_ciclo] if gerar_apenas_primeiro_ciclo else gaps
        leader = {
            "nome": nome_lider,
            "email": email_lider,
            "rodada": codrodada,
            "contexto": contexto,
            "contexto_ids": contexto_ids,
        }
        devolutiva = build_empty_devolutiva(
            empresa=empresa,
            contexto=contexto,
            codrodada=codrodada,
            email_lider=email_lider,
            nome_lider=nome_lider,
            gaps=gaps,
            arquetipos=arquetipos,
            maximo_gaps_por_ciclo=maximo_gaps_por_ciclo,
            todas_afirmacoes=todas_afirmacoes,
            baixa_referencia=baixa_referencia,
            gap_minimo=gap_minimo,
            baixa_referencia_threshold=baixa_referencia_threshold,
            contexto_ids=contexto_ids,
        )
        devolutiva["status"] = "gerada_sem_persistencia"
        devolutiva["modo_geracao_planos"] = "com_ia" if gerar_planos_com_ia else "estrutura_sem_ia"
        devolutiva["proximo_passo_sugerido"] = (
            "Gerar PDI detalhado por afirmacao, em chamada especifica com IA, para evitar timeout."
            if not gerar_planos_com_ia else
            "Validar plano gerado antes de enviar para PDI/Treinamentos ou Desempenho."
        )

        for gap in gaps_para_gerar:
            gap_id = f"{gap['questao']}_{slug(gap['dimensao'])}_{slug(gap['subdimensao'])}"
            if gerar_planos_com_ia:
                prompt_diagnostico = build_diagnostic_prompt(
                    leader=leader,
                    arquetipos=arquetipos,
                    gap=gap,
                    indicadores_disponiveis=indicadores_disponiveis,
                )
                resposta_diagnostico = gerar_resposta_ia_leadertrack(
                    pergunta=prompt_diagnostico,
                    prompt_base=prompt_base,
                    empresa=empresa,
                    codrodada=codrodada,
                    email_lider=email_lider,
                    pagina_atual="/gerar-devolutiva-leadertrack",
                    url_atual="https://gestor.thehrkey.tech",
                    dados_arquetipos_comparativo=dados_arquetipos_comparativo,
                    dados_arquetipos_analitico=dados_arquetipos_analitico,
                    guia_arquetipos=guia_arquetipos,
                    dados_microambiente_analitico=dados_microambiente_analitico,
                    dados_microambiente_subdimensao=dados_microambiente_subdimensao,
                    dados_microambiente_termometro_gaps=dados_microambiente_termometro_gaps,
                    dados_microambiente_waterfall_gaps=dados_microambiente_waterfall_gaps,
                    guia_microambiente=guia_microambiente,
                )
                diagnostico = parse_json_response(resposta_diagnostico)

                semanas = []
                revisoes = []
                for inicio, fim in [(1, 4), (5, 8), (9, 12)]:
                    prompt_semanal = build_weekly_prompt(
                        leader=leader,
                        arquetipos=arquetipos,
                        gap=gap,
                        diagnostic=diagnostico,
                        start_week=inicio,
                        end_week=fim,
                        indicadores_disponiveis=indicadores_disponiveis,
                    )
                    resposta_semanal = gerar_resposta_ia_leadertrack(
                        pergunta=prompt_semanal,
                        prompt_base=prompt_base,
                        empresa=empresa,
                        codrodada=codrodada,
                        email_lider=email_lider,
                        pagina_atual="/gerar-devolutiva-leadertrack",
                        url_atual="https://gestor.thehrkey.tech",
                        dados_arquetipos_comparativo=dados_arquetipos_comparativo,
                        dados_arquetipos_analitico=dados_arquetipos_analitico,
                        guia_arquetipos=guia_arquetipos,
                        dados_microambiente_analitico=dados_microambiente_analitico,
                        dados_microambiente_subdimensao=dados_microambiente_subdimensao,
                        dados_microambiente_termometro_gaps=dados_microambiente_termometro_gaps,
                        dados_microambiente_waterfall_gaps=dados_microambiente_waterfall_gaps,
                        guia_microambiente=guia_microambiente,
                    )
                    plano = parse_json_response(resposta_semanal)
                    semanas.extend(plano.get("plano_12_semanas", []))
                    if plano.get("revisao_parcial_informal"):
                        revisoes.append(plano["revisao_parcial_informal"])

                plano_12_semanas = sorted(semanas, key=lambda item: int(item.get("semana", 0) or 0))
            else:
                diagnostico = {
                    "status": "pendente_geracao_ia",
                    "mensagem": "Diagnostico tecnico e plano semanal devem ser gerados por etapa para evitar timeout.",
                    "gap": gap,
                    "arquetipos_disponiveis_para_cruzamento": arquetipos,
                    "indicadores_operacionais_disponiveis": indicadores_disponiveis,
                }
                plano_12_semanas = []
                revisoes = []

            pdi_payload = {
                "gap_id": gap_id,
                "gap": gap,
                "diagnostico": diagnostico,
                "plano_12_semanas": plano_12_semanas,
                "revisoes_parciais_informais": revisoes,
                "geracao_ia": {
                    "status": "concluida" if gerar_planos_com_ia else "pendente",
                    "motivo": None if gerar_planos_com_ia else "A tela deve solicitar a geracao profunda deste gap em chamada propria.",
                },
                "origem_para_pdi_treinamentos": {
                    "pode_enviar_para_modulo_pdi": bool(gerar_planos_com_ia),
                    "status_inicial": "sugerido_pela_devolutiva",
                    "requer_validacao_consultiva": True,
                },
            }
            historico_snapshot = dict(pdi_payload)
            pdi_payload["historico_evento_inicial"] = build_history_event(
                empresa=empresa,
                contexto=contexto,
                email_lider=email_lider,
                nome_lider=nome_lider,
                codrodada=codrodada,
                gap_id=gap_id,
                event_type="pdi_sugerido_pela_devolutiva",
                description="PDI sugerido a partir de devolutiva LeaderTrack, pendente de validacao consultiva.",
                payload=historico_snapshot,
            )
            pdi_payload["meta_desempenho_sugerida"] = build_performance_goal_suggestion(
                email_lider=email_lider,
                empresa=empresa,
                contexto=contexto,
                codrodada=codrodada,
                gap_id=gap_id,
                gap=gap,
            )
            devolutiva["pdis"].append(pdi_payload)

        if persistir:
            persistencia = persistir_devolutiva_leadertrack(devolutiva, gerado_por=gerado_por)
            devolutiva["persistencia"] = persistencia
            devolutiva["status"] = "gerada_e_salva_como_rascunho"

        response = jsonify(devolutiva)
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 200

    except Exception as e:
        print("Erro ao gerar devolutiva LeaderTrack:", e)
        response = jsonify({"erro": str(e)})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 500


@app.route("/gerar-pdi-leadertrack-afirmacao", methods=["POST", "OPTIONS"])
def gerar_pdi_leadertrack_afirmacao():
    if request.method == "OPTIONS":
        response = jsonify({'status': 'CORS preflight OK'})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        response.headers["Access-Control-Allow-Methods"] = "POST,OPTIONS"
        return response

    try:
        dados = request.get_json() or {}
        empresa = dados.get("empresa", "").lower()
        codrodada = dados.get("codrodada", "").lower()
        email_lider = dados.get("emailLider", "").lower()
        nome_lider = dados.get("nomeLider", "")
        contexto = dados.get("contexto", "")
        etapa = str(dados.get("etapa") or "diagnostico").strip().lower()
        indicadores_disponiveis = dados.get("indicadoresOperacionaisDisponiveis", [])

        contexto_ids = {
            "cliente_id": dados.get("cliente_id") or dados.get("clienteId"),
            "holding_id": dados.get("holding_id") or dados.get("holdingId"),
            "empresa_id": dados.get("empresa_id") or dados.get("empresaId"),
            "filial_id": dados.get("filial_id") or dados.get("filialId"),
        }

        if not empresa or not codrodada or not email_lider:
            response = jsonify({
                "erro": "Campos obrigatorios ausentes.",
                "campos_necessarios": ["empresa", "codrodada", "emailLider"]
            })
            response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
            return response, 400

        dados_arquetipos_comparativo = buscar_json_supabase(
            "arquetipos_grafico_comparativo", empresa, codrodada, email_lider
        )
        dados_arquetipos_analitico = buscar_json_supabase(
            "arquetipos_analitico", empresa, codrodada, email_lider
        )
        guia_arquetipos = buscar_json_supabase(
            "arquetipos_parecer_ia", empresa, codrodada, email_lider
        )
        dados_microambiente_analitico = buscar_json_microambiente(
            "microambiente_analitico", empresa, codrodada, email_lider
        )
        dados_microambiente_subdimensao = buscar_json_microambiente(
            "microambiente_grafico_mediaequipe_subdimensao", empresa, codrodada, email_lider
        )
        dados_microambiente_termometro_gaps = buscar_json_microambiente(
            "microambiente_termometro_gaps", empresa, codrodada, email_lider
        )
        dados_microambiente_waterfall_gaps = buscar_json_microambiente(
            "microambiente_waterfall_gaps", empresa, codrodada, email_lider
        )
        guia_microambiente = buscar_json_microambiente(
            "microambiente_parecer_ia", empresa, codrodada, email_lider
        )

        if not dados_arquetipos_comparativo or not dados_microambiente_analitico:
            response = jsonify({
                "erro": "Dados LeaderTrack insuficientes para gerar PDI da afirmacao.",
                "dados_encontrados": {
                    "arquetipos_grafico_comparativo": bool(dados_arquetipos_comparativo),
                    "microambiente_analitico": bool(dados_microambiente_analitico),
                }
            })
            response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
            return response, 404

        arquetipos = archetype_summary(dados_arquetipos_comparativo)
        todas_afirmacoes = microenvironment_affirmations(dados_microambiente_analitico)
        gap = selecionar_gap_leadertrack(todas_afirmacoes, dados)
        if not gap:
            response = jsonify({
                "erro": "Afirmacao/gap nao encontrado.",
                "orientacao": "Informe gapId, questao ou envie o objeto gap retornado pela devolutiva estruturada."
            })
            response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
            return response, 404

        leader = {
            "nome": nome_lider,
            "email": email_lider,
            "rodada": codrodada,
            "contexto": contexto,
            "contexto_ids": contexto_ids,
        }
        prompt_base = carregar_prompt_leadertrack()

        if etapa == "diagnostico":
            prompt = build_diagnostic_prompt(
                leader=leader,
                arquetipos=arquetipos,
                gap=gap,
                indicadores_disponiveis=indicadores_disponiveis,
            )
            resposta_ia = gerar_resposta_ia_leadertrack(
                pergunta=prompt,
                prompt_base=prompt_base,
                empresa=empresa,
                codrodada=codrodada,
                email_lider=email_lider,
                pagina_atual="/gerar-pdi-leadertrack-afirmacao",
                url_atual="https://gestor.thehrkey.tech",
                dados_arquetipos_comparativo=dados_arquetipos_comparativo,
                dados_arquetipos_analitico=dados_arquetipos_analitico,
                guia_arquetipos=guia_arquetipos,
                dados_microambiente_analitico=dados_microambiente_analitico,
                dados_microambiente_subdimensao=dados_microambiente_subdimensao,
                dados_microambiente_termometro_gaps=dados_microambiente_termometro_gaps,
                dados_microambiente_waterfall_gaps=dados_microambiente_waterfall_gaps,
                guia_microambiente=guia_microambiente,
            )
            resultado = parse_json_response(resposta_ia)
            payload = {
                "status": "ok",
                "etapa": etapa,
                "gap_id": leadertrack_gap_id(gap),
                "gap": gap,
                "diagnostico": resultado,
                "persistencia": "nao_salvo",
                "proxima_etapa_sugerida": "semanas_1_4",
            }
        else:
            intervalo = intervalo_etapa_leadertrack(etapa, dados)
            if not intervalo:
                response = jsonify({
                    "erro": "Etapa invalida.",
                    "etapas_validas": ["diagnostico", "semanas_1_4", "semanas_5_8", "semanas_9_12"]
                })
                response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
                return response, 400

            diagnostico = dados.get("diagnostico") or {
                "status": "diagnostico_nao_enviado",
                "orientacao": "Use preferencialmente o diagnostico gerado na etapa diagnostico como entrada desta chamada.",
            }
            inicio, fim = intervalo
            prompt = build_weekly_prompt(
                leader=leader,
                arquetipos=arquetipos,
                gap=gap,
                diagnostic=diagnostico,
                start_week=inicio,
                end_week=fim,
                indicadores_disponiveis=indicadores_disponiveis,
            )
            resposta_ia = gerar_resposta_ia_leadertrack(
                pergunta=prompt,
                prompt_base=prompt_base,
                empresa=empresa,
                codrodada=codrodada,
                email_lider=email_lider,
                pagina_atual="/gerar-pdi-leadertrack-afirmacao",
                url_atual="https://gestor.thehrkey.tech",
                dados_arquetipos_comparativo=dados_arquetipos_comparativo,
                dados_arquetipos_analitico=dados_arquetipos_analitico,
                guia_arquetipos=guia_arquetipos,
                dados_microambiente_analitico=dados_microambiente_analitico,
                dados_microambiente_subdimensao=dados_microambiente_subdimensao,
                dados_microambiente_termometro_gaps=dados_microambiente_termometro_gaps,
                dados_microambiente_waterfall_gaps=dados_microambiente_waterfall_gaps,
                guia_microambiente=guia_microambiente,
            )
            resultado = parse_json_response(resposta_ia)
            proxima_etapa = None
            if fim == 4:
                proxima_etapa = "semanas_5_8"
            elif fim == 8:
                proxima_etapa = "semanas_9_12"
            payload = {
                "status": "ok",
                "etapa": etapa,
                "gap_id": leadertrack_gap_id(gap),
                "gap": gap,
                "diagnostico_usado": diagnostico,
                "plano_parcial": resultado,
                "persistencia": "nao_salvo",
                "proxima_etapa_sugerida": proxima_etapa,
            }

        response = jsonify(payload)
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 200

    except Exception as e:
        print("Erro ao gerar PDI LeaderTrack por afirmacao:", e)
        response = jsonify({"erro": str(e)})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 500


@app.route("/teste-chat-leadertrack", methods=["GET"])
def teste_chat_leadertrack_get():
    try:
        empresa = request.args.get("empresa", "").lower()
        codrodada = request.args.get("codrodada", "").lower()
        email_lider = request.args.get("emailLider", "").lower()
        pergunta = request.args.get(
            "pergunta",
            "Como posso melhorar o microambiente da minha equipe com base nos meus arquétipos?"
        )

        if not empresa or not codrodada or not email_lider:
            return jsonify({
                "status": "erro",
                "mensagem": "Informe empresa, codrodada e emailLider na URL.",
                "exemplo": "/teste-chat-leadertrack?empresa=empresa_teste&codrodada=rodada1&emailLider=lider@teste.com"
            }), 400

        prompt_base = carregar_prompt_leadertrack()

        dados_arquetipos_comparativo = buscar_json_supabase(
            "arquetipos_grafico_comparativo",
            empresa,
            codrodada,
            email_lider
        )

        dados_arquetipos_analitico = buscar_json_supabase(
            "arquetipos_analitico",
            empresa,
            codrodada,
            email_lider
        )

        guia_arquetipos = buscar_json_supabase(
            "arquetipos_parecer_ia",
            empresa,
            codrodada,
            email_lider
        )

        dados_microambiente_analitico = buscar_json_microambiente(
            "microambiente_analitico",
            empresa,
            codrodada,
            email_lider
        )

        dados_microambiente_subdimensao = buscar_json_microambiente(
            "microambiente_grafico_mediaequipe_subdimensao",
            empresa,
            codrodada,
            email_lider
        )

        dados_microambiente_termometro_gaps = buscar_json_microambiente(
            "microambiente_termometro_gaps",
            empresa,
            codrodada,
            email_lider
        )

        dados_microambiente_waterfall_gaps = buscar_json_microambiente(
            "microambiente_waterfall_gaps",
            empresa,
            codrodada,
            email_lider
        )

        guia_microambiente = buscar_json_microambiente(
            "microambiente_parecer_ia",
            empresa,
            codrodada,
            email_lider
        )

        

        return jsonify({
            "status": "ok",
            "pergunta": pergunta,
            "prompt_carregado": True,
            "tamanho_prompt": len(prompt_base),
            "dados_encontrados": {
                "arquetipos_grafico_comparativo": "ENCONTRADO" if dados_arquetipos_comparativo else "NÃO ENCONTRADO",
                "arquetipos_analitico": "ENCONTRADO" if dados_arquetipos_analitico else "NÃO ENCONTRADO",
                "arquetipos_parecer_ia_guia": "ENCONTRADO" if guia_arquetipos else "NÃO ENCONTRADO",

                "microambiente_analitico": "ENCONTRADO" if dados_microambiente_analitico else "NÃO ENCONTRADO",
                "microambiente_grafico_mediaequipe_subdimensao": "ENCONTRADO" if dados_microambiente_subdimensao else "NÃO ENCONTRADO",
                "microambiente_termometro_gaps": "ENCONTRADO" if dados_microambiente_termometro_gaps else "NÃO ENCONTRADO",
                "microambiente_waterfall_gaps": "ENCONTRADO" if dados_microambiente_waterfall_gaps else "NÃO ENCONTRADO",
                "microambiente_parecer_ia_guia": "ENCONTRADO" if guia_microambiente else "NÃO ENCONTRADO",

                
            }
        }), 200

    except Exception as e:
        print("Erro no teste chat Leadertrack GET:", e)
        return jsonify({
            "status": "erro",
            "mensagem": str(e)
        }), 500



@app.route("/teste-ia-leadertrack", methods=["GET"])
def teste_ia_leadertrack_get():
    try:
        empresa = request.args.get("empresa", "").lower()
        codrodada = request.args.get("codrodada", "").lower()
        email_lider = request.args.get("emailLider", "").lower()
        pergunta = request.args.get(
            "pergunta",
            "Como posso melhorar o microambiente da minha equipe com base nos meus arquétipos?"
        )

        if not empresa or not codrodada or not email_lider:
            return jsonify({
                "status": "erro",
                "mensagem": "Informe empresa, codrodada e emailLider na URL.",
                "exemplo": "/teste-ia-leadertrack?empresa=fastco&codrodada=av1225&emailLider=felipe@astro34.com.br"
            }), 400

        prompt_base = carregar_prompt_leadertrack()

        dados_arquetipos_comparativo = buscar_json_supabase(
            "arquetipos_grafico_comparativo",
            empresa,
            codrodada,
            email_lider
        )

        dados_arquetipos_analitico = buscar_json_supabase(
            "arquetipos_analitico",
            empresa,
            codrodada,
            email_lider
        )

        guia_arquetipos = buscar_json_supabase(
            "arquetipos_parecer_ia",
            empresa,
            codrodada,
            email_lider
        )

        dados_microambiente_analitico = buscar_json_microambiente(
            "microambiente_analitico",
            empresa,
            codrodada,
            email_lider
        )

        dados_microambiente_subdimensao = buscar_json_microambiente(
            "microambiente_grafico_mediaequipe_subdimensao",
            empresa,
            codrodada,
            email_lider
        )

        dados_microambiente_termometro_gaps = buscar_json_microambiente(
            "microambiente_termometro_gaps",
            empresa,
            codrodada,
            email_lider
        )

        dados_microambiente_waterfall_gaps = buscar_json_microambiente(
            "microambiente_waterfall_gaps",
            empresa,
            codrodada,
            email_lider
        )

        guia_microambiente = buscar_json_microambiente(
            "microambiente_parecer_ia",
            empresa,
            codrodada,
            email_lider
        )

        resposta_ia = gerar_resposta_ia_leadertrack(
            pergunta=pergunta,
            prompt_base=prompt_base,
            empresa=empresa,
            codrodada=codrodada,
            email_lider=email_lider,
            pagina_atual="/teste-ia-leadertrack",
            url_atual=request.url, 
            dados_arquetipos_comparativo=dados_arquetipos_comparativo,
            dados_arquetipos_analitico=dados_arquetipos_analitico,
            guia_arquetipos=guia_arquetipos,
            dados_microambiente_analitico=dados_microambiente_analitico,
            dados_microambiente_subdimensao=dados_microambiente_subdimensao,
            dados_microambiente_termometro_gaps=dados_microambiente_termometro_gaps,
            dados_microambiente_waterfall_gaps=dados_microambiente_waterfall_gaps,
            guia_microambiente=guia_microambiente
        )

        return jsonify({
            "status": "ok",
            "pergunta": pergunta,
            "resposta": resposta_ia
        }), 200

    except Exception as e:
        print("Erro no teste IA Leadertrack GET:", e)
        return jsonify({
            "status": "erro",
            "mensagem": str(e)
        }), 500




if __name__ == "__main__":
    app.run(debug=True)
