import os
import logging
from flask import Flask, jsonify, request
from flask_cors import CORS

from rotas_api import api_bp
from rotas_strava import strava_bp

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AURA_APP")

app = Flask(__name__)

# ===================================================
# 🔐 CORS — URL do Render como origem principal
# ===================================================
# FRONTEND_URL deve ser configurada no painel do Render.
# Ex: https://meu-app.onrender.com
# Webhooks externos (Asaas, RevenueCat) precisam de origins="*" pois
# partem de servidores de terceiros — não de um browser.

_FRONTEND_URL = os.getenv("FRONTEND_URL", "")
_ALLOWED_ORIGINS = (
    [_FRONTEND_URL, "http://localhost:3000", "http://localhost:5050", "capacitor://localhost"]
    if _FRONTEND_URL
    else "*"
)

_CORS_HEADERS = [
    "Authorization",
    "Content-Type",
    "X-Requested-With",
    "X-Apple-IAP-Id",
    "X-RevenueCat-ETag"
]

CORS(app, resources={
    # Rotas de webhook abertas para servidores externos (Asaas / RevenueCat)
    r"/api/webhook/*": {
        "origins": "*",
        "allow_headers": _CORS_HEADERS,
        "methods": ["POST", "OPTIONS"]
    },
    # Todas as demais rotas — restritas à URL do Render (ou * em desenvolvimento)
    r"/*": {
        "origins": _ALLOWED_ORIGINS,
        "allow_headers": _CORS_HEADERS,
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "expose_headers": ["Content-Range", "X-Content-Range"]
    }
})

# 2. Registro de Rotas (Blueprints)
# [AURA FIX 404] Definimos o prefixo global aqui de forma definitiva. 
# As rotas de webhook (/api/webhook/revenuecat) e frete já estão contempladas no prefixo /api.
app.register_blueprint(api_bp, url_prefix='/api')
app.register_blueprint(strava_bp, url_prefix='/strava')

# 3. Rota Raiz (Health Check & Version Control)
@app.route('/')
def health_check():
    return jsonify({
        "status": "online",
        "system": "Aura Performance OS",
        "version": "3.3.0-NATIVE-IAP", # Versão atualizada para suporte a RevenueCat e Apple Sign-in
        "env": os.getenv("FLASK_ENV", "production"),
        "engine": "Aura-Core-Hybrid-Engine",
        "features": [
            "Marketplace", 
            "Melhor Envio Logistics", 
            "Asaas Gateway", 
            "RevenueCat Webhooks", 
            "Apple Auth Ready"
        ]
    })

# 4. Tratamento Global de Erros (Evita crash no App)
@app.errorhandler(404)
def not_found(e):
    # [AURA LOG] Ajuda a identificar qual URL exata está falhando nos logs do Render
    logger.warning(f"⚠️ Rota não encontrada: {request.path}")
    return jsonify({"erro": f"Rota {request.path} não encontrada no Aura OS"}), 404

@app.errorhandler(400)
def bad_request(e):
    return jsonify({"erro": "Requisição mal formatada ou parâmetros ausentes"}), 400

@app.errorhandler(500)
def server_error(e):
    logger.error(f"❌ Erro Crítico Interno: {e}")
    return jsonify({"erro": "Falha interna no servidor Aura. Verifique os logs no Render."}), 500

# Verificação de Variáveis de Ambiente Críticas para o Dia de Lançamento
if not os.getenv("MONGODB_URI"):
    logger.warning("⚠️ MONGODB_URI não detectada! O banco de dados ficará offline.")

if not os.getenv("MELHOR_ENVIO_TOKEN"):
    logger.warning("⚠️ MELHOR_ENVIO_TOKEN ausente! O cálculo de frete não funcionará.")

# [AURA LOCAL LAUNCH] Bloco para rodar no seu MacBook Pro
if __name__ == '__main__':
    port = int(os.getenv("PORT", 5050)) 
    logger.info(f"🚀 Aura OS Híbrido iniciando localmente na porta {port}...")
    app.run(host='0.0.0.0', port=port, debug=True)