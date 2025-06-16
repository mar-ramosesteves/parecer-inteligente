from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from fpdf import FPDF
from datetime import datetime
import io, os, textwrap, json
from googleapiclient.http import MediaIoBaseUpload
from openai import OpenAI

app = Flask(__name__)

# Ativa CORS para origem específica
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "https://gestor.thehrkey.tech"}})

# Middleware pós-resposta para garantir que OPTIONS passe
@app.after_request
def aplicar_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response

@app.route("/")
def index():
    return "API no ar! 🚀"

@app.route("/emitir-parecer-inteligente", methods=["POST", "OPTIONS"])
def emitir_parecer_inteligente():
    if request.method == "OPTIONS":
        # Preflight CORS OK
        response = make_response()
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response, 200

    try:
        dados = request.json
        empresa = dados["empresa"].lower()
        codrodada = dados["codrodada"].lower()
        emailLider = dados["emailLider"].lower()

        # Simulação apenas para teste (remova isso e insira o que já tinha depois)
        return jsonify({"mensagem": f"✅ Parecer para {emailLider} gerado com sucesso!"})

    except Exception as e:
        return jsonify({"erro": str(e)}), 500

if __name__ == "__main__":
    app.run()
