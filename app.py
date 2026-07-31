from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
import re
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
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
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


def supabase_headers(prefer_return=True, use_service_role=False):
    key = SUPABASE_SERVICE_ROLE_KEY if use_service_role and SUPABASE_SERVICE_ROLE_KEY else SUPABASE_KEY
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer_return:
        headers["Prefer"] = "return=representation"
    return headers


def supabase_insert(table, payload):
    if not SUPABASE_REST_URL or not (SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY):
        raise RuntimeError("Supabase nao configurado no ambiente.")
    url = f"{SUPABASE_REST_URL}/{table}"
    response = requests.post(url, headers=supabase_headers(use_service_role=True), json=payload, timeout=60)
    if response.status_code >= 300:
        raise RuntimeError(f"Erro ao salvar em {table}: HTTP {response.status_code} - {response.text}")
    data = response.json()
    if isinstance(data, list) and data:
        return data[0]
    return data


def listar_lideres_relatorios(empresa, codrodada):
    if not SUPABASE_REST_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase nao configurado no ambiente.")

    url = f"{SUPABASE_REST_URL}/relatorios_gerados"
    params = {
        "select": "emaillider,tipo_relatorio,data_criacao,dados_json",
        "empresa": f"ilike.{empresa}",
        "codrodada": f"ilike.{codrodada}",
        "tipo_relatorio": "in.(microambiente_analitico,arquetipos_analitico)",
        "order": "emaillider.asc,data_criacao.desc",
        "limit": 1000,
    }
    response = requests.get(url, headers=supabase_headers(prefer_return=False), params=params, timeout=60)
    if response.status_code >= 300:
        raise RuntimeError(f"Erro ao listar lideres: HTTP {response.status_code} - {response.text}")

    leaders = {}
    for row in response.json() or []:
        email = str(row.get("emaillider") or "").strip().lower()
        if not email:
            continue
        current = leaders.setdefault(email, {
            "email": email,
            "nome": None,
            "rotulo": email,
            "relatorios_disponiveis": [],
            "ultima_atualizacao": None,
        })
        tipo = row.get("tipo_relatorio")
        if tipo and tipo not in current["relatorios_disponiveis"]:
            current["relatorios_disponiveis"].append(tipo)
        data_criacao = row.get("data_criacao")
        if data_criacao and (not current["ultima_atualizacao"] or data_criacao > current["ultima_atualizacao"]):
            current["ultima_atualizacao"] = data_criacao

    lista = []
    for leader in leaders.values():
        if leader["nome"]:
            leader["rotulo"] = f"{leader['nome']} - {leader['email']}"
        lista.append(leader)
    return sorted(lista, key=lambda item: item["rotulo"].lower())


def listar_empresas_relatorios(codrodada=None):
    if not SUPABASE_REST_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase nao configurado no ambiente.")

    url = f"{SUPABASE_REST_URL}/relatorios_gerados"
    params = {
        "select": "empresa,codrodada,data_criacao",
        "tipo_relatorio": "in.(microambiente_analitico,arquetipos_analitico)",
        "order": "empresa.asc,data_criacao.desc",
        "limit": 1000,
    }
    if codrodada:
        params["codrodada"] = f"ilike.{codrodada}"

    response = requests.get(url, headers=supabase_headers(prefer_return=False), params=params, timeout=60)
    if response.status_code >= 300:
        raise RuntimeError(f"Erro ao listar empresas: HTTP {response.status_code} - {response.text}")

    empresas = {}
    for row in response.json() or []:
        codigo = str(row.get("empresa") or "").strip()
        if not codigo:
            continue
        key = codigo.lower()
        current = empresas.setdefault(key, {
            "codigo": key,
            "empresa": key,
            "nome": codigo.upper(),
            "rotulo": codigo.upper(),
            "rodadas": set(),
            "ultima_atualizacao": None,
        })
        rodada = row.get("codrodada")
        if rodada:
            current["rodadas"].add(str(rodada))
        data_criacao = row.get("data_criacao")
        if data_criacao and (not current["ultima_atualizacao"] or data_criacao > current["ultima_atualizacao"]):
            current["ultima_atualizacao"] = data_criacao

    lista = []
    for empresa in empresas.values():
        empresa["rodadas"] = sorted(empresa["rodadas"])
        lista.append(empresa)
    return sorted(lista, key=lambda item: item["rotulo"].lower())


def leadertrack_cache_key(empresa, codrodada, email_lider, equipe_tipo, gap_id, etapa, semana_inicio=None, semana_fim=None):
    parts = [
        "leadertrack_pdi_v1",
        str(empresa or "").strip().lower(),
        str(codrodada or "").strip().lower(),
        str(email_lider or "").strip().lower(),
        str(equipe_tipo or "direta").strip().lower(),
        str(gap_id or "").strip().lower(),
        str(etapa or "").strip().lower(),
        str(semana_inicio or ""),
        str(semana_fim or ""),
    ]
    return "|".join(parts)


def buscar_cache_leadertrack(empresa, email_lider, cache_key):
    if not SUPABASE_REST_URL or not SUPABASE_KEY:
        return None

    url = f"{SUPABASE_REST_URL}/leadertrack_pdi_historico"
    params = {
        "select": "id,dados_depois,data_evento",
        "empresa": f"eq.{empresa}",
        "profissional_email": f"eq.{email_lider}",
        "origem": "eq.leadertrackbot_cache",
        "tipo_evento": "eq.ia_gerada",
        "order": "data_evento.desc",
        "limit": 80,
    }
    response = requests.get(url, headers=supabase_headers(prefer_return=False), params=params, timeout=60)
    if response.status_code >= 300:
        print("Cache LeaderTrack indisponivel:", response.status_code, response.text)
        return None

    for row in response.json() or []:
        dados = row.get("dados_depois") or {}
        if isinstance(dados, str):
            try:
                dados = json.loads(dados)
            except Exception:
                dados = {}
        if dados.get("cache_key") == cache_key:
            payload = dados.get("payload") or {}
            if isinstance(payload, dict):
                payload["persistencia"] = "cache_lido"
                payload["fonte"] = "cache"
                payload["cache"] = {
                    "status": "hit",
                    "cache_key": cache_key,
                    "historico_id": row.get("id"),
                    "data_evento": row.get("data_evento"),
                }
                return payload
    return None


def salvar_cache_leadertrack(empresa, contexto, contexto_ids, email_lider, nome_lider, cache_key, payload, gerado_por=None):
    evento = {
        "profissional_email": email_lider,
        "profissional_nome": nome_lider,
        "cliente_id": contexto_ids.get("cliente_id"),
        "holding_id": contexto_ids.get("holding_id"),
        "empresa_id": contexto_ids.get("empresa_id"),
        "filial_id": contexto_ids.get("filial_id"),
        "empresa": empresa,
        "contexto": contexto,
        "origem": "leadertrackbot_cache",
        "tipo_evento": "ia_gerada",
        "descricao_evento": "Geracao de IA LeaderTrack salva para reuso como cache tecnico.",
        "dados_antes": None,
        "dados_depois": {
            "cache_key": cache_key,
            "payload": payload,
        },
        "registrado_por": gerado_por,
    }
    try:
        saved = supabase_insert("leadertrack_pdi_historico", evento)
        return {
            "status": "salvo_no_historico_cache",
            "historico_id": saved.get("id") if isinstance(saved, dict) else None,
        }
    except Exception as exc:
        print("Erro ao salvar cache LeaderTrack:", exc)
        return {
            "status": "nao_salvo",
            "erro": str(exc),
        }


def _normalizar_chave_amostra(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def avaliar_amostra_leadertrack(*relatorios):
    textos = []
    campos = {}

    def walk(value, path=""):
        if isinstance(value, dict):
            for key, item in value.items():
                key_norm = _normalizar_chave_amostra(key)
                if isinstance(item, (int, float, str, bool)) and (
                    key_norm in (
                    "respondentes",
                    "respostasequipe",
                    "respostasdaequipe",
                    "elegiveismedia",
                    "elegiveisparamedia",
                    "menosde3meses",
                    "menos3meses",
                    "amostrainsuficiente",
                    )
                    or "respondente" in key_norm
                    or "respostaequipe" in key_norm
                    or "elegivel" in key_norm
                    or "elegivei" in key_norm
                    or "amostra" in key_norm
                    or "menosde3" in key_norm
                ):
                    campos[key_norm] = item
                walk(item, f"{path}.{key}" if path else str(key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
        elif isinstance(value, str):
            textos.append(value.lower())

    for relatorio in relatorios:
        walk(relatorio)

    texto_unificado = " ".join(textos)
    def numero(value):
        try:
            return float(str(value).replace(",", "."))
        except Exception:
            return None

    elegiveis = campos.get("elegiveismedia", campos.get("elegiveisparamedia"))
    respostas = campos.get("respostasequipe", campos.get("respostasdaequipe", campos.get("respondentes")))
    menos_3_meses = campos.get("menosde3meses", campos.get("menos3meses"))

    for key, value in campos.items():
        if "elegivel" in key or "elegivei" in key:
            elegiveis = value if elegiveis in (None, "") else elegiveis
        if "respondente" in key or "respostaequipe" in key:
            respostas = value if respostas in (None, "") else respostas
        if "menosde3" in key:
            menos_3_meses = value if menos_3_meses in (None, "") else menos_3_meses

    elegiveis_num = numero(elegiveis)
    respostas_num = numero(respostas)

    insuficiente = (
        "amostra insuficiente" in texto_unificado
        or "menos de 3 respostas" in texto_unificado
        or "menos de três respostas" in texto_unificado
        or bool(campos.get("amostrainsuficiente"))
        or (elegiveis_num is not None and elegiveis_num < 3)
        or (respostas_num is not None and respostas_num < 3)
    )

    return {
        "insuficiente": bool(insuficiente),
        "respostas_equipe": respostas,
        "elegiveis_media": elegiveis,
        "menos_de_3_meses": menos_3_meses,
        "criterio": "Amostra minima recomendada: pelo menos 3 respostas elegiveis para media da equipe.",
        "orientacao": (
            "Quando a amostra e insuficiente, os graficos podem existir, mas a devolutiva deve ser tratada "
            "como leitura limitada. Evite conclusoes fortes sobre percepcao coletiva da equipe."
            if insuficiente else
            "Amostra sem sinal automatico de insuficiencia nos metadados disponiveis."
        ),
    }


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
        equipe_tipo = str(dados.get("equipeTipo") or dados.get("tipoEquipe") or "direta").strip().lower()
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
        amostra = avaliar_amostra_leadertrack(
            dados_arquetipos_comparativo,
            dados_arquetipos_analitico,
            dados_microambiente_analitico,
            dados_microambiente_subdimensao,
            dados_microambiente_termometro_gaps,
            dados_microambiente_waterfall_gaps,
        )
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
        devolutiva["equipe_tipo"] = equipe_tipo
        devolutiva["amostra"] = amostra
        if amostra.get("insuficiente"):
            devolutiva["modo_devolutiva"] = {
                "modo": "amostra_insuficiente",
                "titulo": "Amostra insuficiente para leitura coletiva robusta",
                "leitura": amostra.get("orientacao"),
            }
            devolutiva["avisos"] = (devolutiva.get("avisos") or []) + [
                "Amostra insuficiente: tratar graficos e planos como leitura limitada, sem conclusoes fortes sobre a equipe.",
            ]
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


@app.route("/listar-empresas-leadertrack", methods=["POST", "OPTIONS"])
def listar_empresas_leadertrack():
    if request.method == "OPTIONS":
        response = jsonify({'status': 'CORS preflight OK'})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        response.headers["Access-Control-Allow-Methods"] = "POST,OPTIONS"
        return response

    try:
        dados = request.get_json() or {}
        codrodada = str(dados.get("codrodada") or "").strip().lower()
        contexto = dados.get("contexto", "")
        contexto_ids = {
            "cliente_id": dados.get("cliente_id") or dados.get("clienteId"),
            "holding_id": dados.get("holding_id") or dados.get("holdingId"),
            "empresa_id": dados.get("empresa_id") or dados.get("empresaId"),
            "filial_id": dados.get("filial_id") or dados.get("filialId"),
        }

        empresas = listar_empresas_relatorios(codrodada=codrodada or None)
        response = jsonify({
            "status": "ok",
            "codrodada": codrodada,
            "contexto": contexto,
            "contexto_ids": contexto_ids,
            "total": len(empresas),
            "empresas": empresas,
            "observacao": "Lista baseada em empresas tecnicas encontradas nos relatorios LeaderTrack ja apurados. Nome oficial deve ser vinculado ao cadastro central em uma proxima etapa.",
        })
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 200

    except Exception as e:
        print("Erro ao listar empresas LeaderTrack:", e)
        response = jsonify({"erro": str(e)})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 500


@app.route("/listar-lideres-leadertrack", methods=["POST", "OPTIONS"])
def listar_lideres_leadertrack():
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
        contexto = dados.get("contexto", "")
        contexto_ids = {
            "cliente_id": dados.get("cliente_id") or dados.get("clienteId"),
            "holding_id": dados.get("holding_id") or dados.get("holdingId"),
            "empresa_id": dados.get("empresa_id") or dados.get("empresaId"),
            "filial_id": dados.get("filial_id") or dados.get("filialId"),
        }

        if not empresa or not codrodada:
            response = jsonify({
                "erro": "Campos obrigatorios ausentes.",
                "campos_necessarios": ["empresa", "codrodada"]
            })
            response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
            return response, 400

        lideres = listar_lideres_relatorios(empresa, codrodada)
        response = jsonify({
            "status": "ok",
            "empresa": empresa,
            "codrodada": codrodada,
            "contexto": contexto,
            "contexto_ids": contexto_ids,
            "total": len(lideres),
            "lideres": lideres,
            "observacao": "Lista baseada em relatorios LeaderTrack ja apurados. Nome completo depende de vinculo futuro com cadastro central.",
        })
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 200

    except Exception as e:
        print("Erro ao listar lideres LeaderTrack:", e)
        response = jsonify({"erro": str(e)})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        return response, 500


@app.route("/teste-cache-leadertrack", methods=["POST", "OPTIONS"])
def teste_cache_leadertrack():
    if request.method == "OPTIONS":
        response = jsonify({'status': 'CORS preflight OK'})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        response.headers["Access-Control-Allow-Methods"] = "POST,OPTIONS"
        return response

    try:
        dados = request.get_json() or {}
        empresa = str(dados.get("empresa") or "fastco").strip().lower()
        codrodada = str(dados.get("codrodada") or "av1225").strip().lower()
        email_lider = str(dados.get("emailLider") or "teste-cache@leadertrack.local").strip().lower()
        nome_lider = str(dados.get("nomeLider") or "Teste Cache LeaderTrack").strip()
        contexto = str(dados.get("contexto") or "teste_cache").strip()
        contexto_ids = {
            "cliente_id": dados.get("cliente_id") or dados.get("clienteId"),
            "holding_id": dados.get("holding_id") or dados.get("holdingId"),
            "empresa_id": dados.get("empresa_id") or dados.get("empresaId"),
            "filial_id": dados.get("filial_id") or dados.get("filialId"),
        }
        cache_key = leadertrack_cache_key(
            empresa=empresa,
            codrodada=codrodada,
            email_lider=email_lider,
            equipe_tipo="diagnostico",
            gap_id="teste_cache",
            etapa="teste_cache",
        )
        payload_teste = {
            "status": "ok",
            "etapa": "teste_cache",
            "gap_id": "teste_cache",
            "fonte": "teste_sem_ia",
            "cache": {
                "status": "miss",
                "cache_key": cache_key,
            },
        }
        persistencia = salvar_cache_leadertrack(
            empresa=empresa,
            contexto=contexto,
            contexto_ids=contexto_ids,
            email_lider=email_lider,
            nome_lider=nome_lider,
            cache_key=cache_key,
            payload=payload_teste,
            gerado_por=dados.get("geradoPor"),
        )
        payload_teste["persistencia"] = persistencia
        response = jsonify(payload_teste)
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        status_code = 200 if persistencia.get("status") == "salvo_no_historico_cache" else 500
        return response, status_code

    except Exception as e:
        print("Erro no teste de cache LeaderTrack:", e)
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
        equipe_tipo = str(dados.get("equipeTipo") or dados.get("tipoEquipe") or "direta").strip().lower()
        etapa = str(dados.get("etapa") or "diagnostico").strip().lower()
        indicadores_disponiveis = dados.get("indicadoresOperacionaisDisponiveis", [])
        usar_cache = bool_param(dados.get("usarCache"), True)
        gravar_cache = bool_param(dados.get("gravarCache"), True)
        gerado_por = dados.get("geradoPor")

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

        gap_id_previo = str(dados.get("gapId") or dados.get("gap_id") or "").strip()
        if usar_cache and gap_id_previo:
            intervalo_previo = None
            if etapa != "diagnostico":
                intervalo_previo = intervalo_etapa_leadertrack(etapa, dados)
            if etapa == "diagnostico":
                cache_key_previa = leadertrack_cache_key(
                    empresa, codrodada, email_lider, equipe_tipo, gap_id_previo, etapa
                )
                cached_payload = buscar_cache_leadertrack(empresa, email_lider, cache_key_previa)
                if cached_payload:
                    response = jsonify(cached_payload)
                    response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
                    return response, 200
            elif intervalo_previo:
                inicio_previo, fim_previo = intervalo_previo
                cache_key_previa = leadertrack_cache_key(
                    empresa, codrodada, email_lider, equipe_tipo, gap_id_previo, etapa, inicio_previo, fim_previo
                )
                cached_payload = buscar_cache_leadertrack(empresa, email_lider, cache_key_previa)
                if cached_payload:
                    response = jsonify(cached_payload)
                    response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
                    return response, 200

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
            "equipe_tipo": equipe_tipo,
            "contexto_ids": contexto_ids,
        }
        prompt_base = carregar_prompt_leadertrack()
        gap_id = leadertrack_gap_id(gap)

        if etapa == "diagnostico":
            cache_key = leadertrack_cache_key(empresa, codrodada, email_lider, equipe_tipo, gap_id, etapa)
            if usar_cache:
                cached_payload = buscar_cache_leadertrack(empresa, email_lider, cache_key)
                if cached_payload:
                    response = jsonify(cached_payload)
                    response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
                    return response, 200

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
                "gap_id": gap_id,
                "gap": gap,
                "diagnostico": resultado,
                "persistencia": "nao_salvo",
                "fonte": "ia",
                "cache": {
                    "status": "miss",
                    "cache_key": cache_key,
                },
                "proxima_etapa_sugerida": "semanas_1_4",
            }
            if gravar_cache:
                persistencia_cache = salvar_cache_leadertrack(
                    empresa=empresa,
                    contexto=contexto,
                    contexto_ids=contexto_ids,
                    email_lider=email_lider,
                    nome_lider=nome_lider,
                    cache_key=cache_key,
                    payload=payload,
                    gerado_por=gerado_por,
                )
                payload["persistencia"] = persistencia_cache
                if persistencia_cache.get("status") == "salvo_no_historico_cache":
                    payload["cache"]["status"] = "saved"
                    payload["cache"]["historico_id"] = persistencia_cache.get("historico_id")
                else:
                    payload["cache"]["status"] = "save_failed"
                    payload["cache"]["erro"] = persistencia_cache.get("erro")
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
            cache_key = leadertrack_cache_key(empresa, codrodada, email_lider, equipe_tipo, gap_id, etapa, inicio, fim)
            if usar_cache:
                cached_payload = buscar_cache_leadertrack(empresa, email_lider, cache_key)
                if cached_payload:
                    response = jsonify(cached_payload)
                    response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
                    return response, 200

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
                "gap_id": gap_id,
                "gap": gap,
                "diagnostico_usado": diagnostico,
                "plano_parcial": resultado,
                "persistencia": "nao_salvo",
                "fonte": "ia",
                "cache": {
                    "status": "miss",
                    "cache_key": cache_key,
                },
                "proxima_etapa_sugerida": proxima_etapa,
            }
            if gravar_cache:
                persistencia_cache = salvar_cache_leadertrack(
                    empresa=empresa,
                    contexto=contexto,
                    contexto_ids=contexto_ids,
                    email_lider=email_lider,
                    nome_lider=nome_lider,
                    cache_key=cache_key,
                    payload=payload,
                    gerado_por=gerado_por,
                )
                payload["persistencia"] = persistencia_cache
                if persistencia_cache.get("status") == "salvo_no_historico_cache":
                    payload["cache"]["status"] = "saved"
                    payload["cache"]["historico_id"] = persistencia_cache.get("historico_id")
                else:
                    payload["cache"]["status"] = "save_failed"
                    payload["cache"]["erro"] = persistencia_cache.get("erro")

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
