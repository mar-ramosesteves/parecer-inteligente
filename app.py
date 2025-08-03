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
import traceback

app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "https://gestor.thehrkey.tech"}})

SUPABASE_REST_URL = os.getenv("SUPABASE_REST_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


from flask import render_template

@app.route("/microambiente_grafico_autoavaliacao_dimensao")
def microambiente_grafico_autoavaliacao_dimensao():
    return render_template("microambiente_grafico_autoavaliacao_dimensao.html")

@app.route("/microambiente_grafico_mediaequipe_dimensao")
def microambiente_grafico_mediaequipe_dimensao():
    return render_template("microambiente_grafico_mediaequipe_dimensao.html")

@app.route("/microambiente_grafico_comparativo")
def microambiente_grafico_comparativo():
    return render_template("microambiente_grafico_comparativo.html")


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

def salvar_json_no_supabase(dados, empresa, codrodada, email_lider, tipo):
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

def buscar_dados_microambiente_supabase(empresa, rodada, email_lider):
    """Busca dados de microambiente do Supabase"""
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    
    # Buscar dados da equipe
    url_equipe = f"{SUPABASE_REST_URL}/microambiente_equipe"
    params_equipe = {
        "empresa": f"eq.{empresa}",
        "codrodada": f"eq.{rodada}",
        "emaillider": f"eq.{email_lider}"
    }
    
    try:
        resp_equipe = requests.get(url_equipe, headers=headers, params=params_equipe)
        dados_equipe = resp_equipe.json() if resp_equipe.status_code == 200 else []
        
        # Buscar dados da autoavaliação
        url_auto = f"{SUPABASE_REST_URL}/microambiente_autoavaliacao"
        params_auto = {
            "empresa": f"eq.{empresa}",
            "codrodada": f"eq.{rodada}",
            "emaillider": f"eq.{email_lider}"
        }
        
        resp_auto = requests.get(url_auto, headers=headers, params=params_auto)
        dados_auto = resp_auto.json() if resp_auto.status_code == 200 else []
        
        return {
            "equipe": dados_equipe,
            "autoavaliacao": dados_auto
        }
    except Exception as e:
        print(f"Erro ao buscar dados de microambiente: {e}")
        return {"equipe": [], "autoavaliacao": []}

def gerar_grafico_microambiente_base64(dados_equipe, dados_auto, tipo_grafico="comparativo"):
    """Gera gráfico de microambiente em base64"""
    dimensoes = ['Adaptabilidade', 'Responsabilidade', 'Performance', 'Reconhecimento', 'Clareza', 'Equipe']
    
    # Calcular médias da equipe
    medias_equipe = []
    for dimensao in dimensoes:
        valores = [item.get(dimensao.lower(), 0) for item in dados_equipe if item.get(dimensao.lower())]
        media = sum(valores) / len(valores) if valores else 0
        medias_equipe.append(media)
    
    # Calcular médias da autoavaliação
    medias_auto = []
    for dimensao in dimensoes:
        valores = [item.get(dimensao.lower(), 0) for item in dados_auto if item.get(dimensao.lower())]
        media = sum(valores) / len(valores) if valores else 0
        medias_auto.append(media)
    
    # Criar gráfico
    fig, ax = plt.subplots(figsize=(12, 8))
    x = np.arange(len(dimensoes))
    width = 0.35
    
    if tipo_grafico == "comparativo":
        ax.bar(x - width/2, medias_equipe, width, label='Equipe', color='#36A2EB', alpha=0.7)
        ax.bar(x + width/2, medias_auto, width, label='Autoavaliação', color='#FF6384', alpha=0.7)
        ax.set_ylabel('Pontuação (%)')
        ax.set_title('Comparativo: Equipe vs Autoavaliação')
        ax.legend()
    elif tipo_grafico == "equipe":
        ax.bar(x, medias_equipe, color='#36A2EB', alpha=0.7)
        ax.set_ylabel('Pontuação (%)')
        ax.set_title('Percepção da Equipe')
    elif tipo_grafico == "auto":
        ax.bar(x, medias_auto, color='#FF6384', alpha=0.7)
        ax.set_ylabel('Pontuação (%)')
        ax.set_title('Sua Autoavaliação')
    
    ax.set_xticks(x)
    ax.set_xticklabels(dimensoes, rotation=45, ha='right')
    ax.set_ylim(0, 100)
    
    # Adicionar valores nas barras
    for i, v in enumerate(medias_equipe if tipo_grafico in ["equipe", "comparativo"] else medias_auto):
        ax.text(i, v + 1, f'{v:.1f}%', ha='center', va='bottom', fontsize=10)
    
    if tipo_grafico == "comparativo":
        for i, v in enumerate(medias_auto):
            ax.text(i + width/2, v + 1, f'{v:.1f}%', ha='center', va='bottom', fontsize=10)
    
    plt.tight_layout()
    
    # Converter para base64
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
    plt.close()
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
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
        
        # --- 2. Buscar dados reais e gerar gráficos dinâmicos ---
        dados_microambiente = buscar_dados_microambiente_supabase(empresa, rodada, email_lider)
        
        # Gerar gráficos base64
        grafico_equipe_base64 = gerar_grafico_microambiente_base64(
            dados_microambiente["equipe"], 
            dados_microambiente["autoavaliacao"], 
            "equipe"
        )
        
        grafico_auto_base64 = gerar_grafico_microambiente_base64(
            dados_microambiente["equipe"], 
            dados_microambiente["autoavaliacao"], 
            "auto"
        )
        
        grafico_comparativo_base64 = gerar_grafico_microambiente_base64(
            dados_microambiente["equipe"], 
            dados_microambiente["autoavaliacao"], 
            "comparativo"
        )
        
        # Criar HTML dos gráficos
        iframe_html_dimensoes = f'''
        <div style="margin: 20px 0; text-align: center;">
            <h3 style="color: #333; margin-bottom: 10px;">Gráfico de Dimensões - Percepção da Equipe</h3>
            <img src="data:image/png;base64,{grafico_equipe_base64}" 
                 style="width:100%;max-width:800px;border:2px solid #ddd; border-radius:8px;">
        </div>
        '''
        
        iframe_html_autoavaliacao = f'''
        <div style="margin: 20px 0; text-align: center;">
            <h3 style="color: #333; margin-bottom: 10px;">Gráfico de Dimensões - Sua Autoavaliação</h3>
            <img src="data:image/png;base64,{grafico_auto_base64}" 
                 style="width:100%;max-width:800px;border:2px solid #ddd; border-radius:8px;">
        </div>
        '''
        
        iframe_html_comparativo = f'''
        <div style="margin: 20px 0; text-align: center;">
            <h3 style="color: #333; margin-bottom: 10px;">Comparativo: Equipe vs Sua Percepção</h3>
            <img src="data:image/png;base64,{grafico_comparativo_base64}" 
                 style="width:100%;max-width:800px;border:2px solid #ddd; border-radius:8px;">
        </div>
        '''

        # --- 3. Inserir gráficos nos pontos estratégicos do texto ---
        marcadores_graficos = {
            "Abaixo, os gráficos de dimensões e subdimensões de microambiente na percepção de sua equipe:": iframe_html_dimensoes,
            "O inventário de Microambiente de Equipe é baseado nos conceitos de inteligência emocional.": iframe_html_comparativo,
            "E abaixo, os gráficos de dimensões e subdimensões de microambiente na sua percepção:": iframe_html_autoavaliacao
        }
        
        conteudo_parecer_final = conteudo_parecer
        for marcador, iframe_html in marcadores_graficos.items():
            if marcador in conteudo_parecer_final:
                conteudo_parecer_final = conteudo_parecer_final.replace(marcador, f"{marcador}\n{iframe_html}")
            else:
                print(f"AVISO: Marcador '{marcador}' não encontrado no guia.")
        
        # Se nenhum marcador foi encontrado, adiciona os gráficos no final
        if conteudo_parecer_final == conteudo_parecer:
            conteudo_parecer_final += f"\n\n{iframe_html_dimensoes}\n{iframe_html_autoavaliacao}\n{iframe_html_comparativo}"
            print("AVISO: Nenhum marcador encontrado. Gráficos adicionados ao final do parecer.")


        # --- 4. Montar a resposta final para o frontend ---
        dados_retorno = {
            "titulo": "PARECER INTELIGENTE - MICROAMBIENTE",
            "subtitulo": f"{empresa.upper()} / {rodada.upper()} / {email_lider}",
            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "conteudo_html": conteudo_parecer_final # O texto do parecer COM o iframe injetado
        }

        # --- 5. Salvar o parecer (com a referência aos gráficos) no Supabase ---
        tipo_relatorio_parecer = "microambiente_parecer_ia"
        salvar_json_no_supabase(dados_retorno, empresa, rodada, email_lider, tipo_relatorio_parecer)

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


