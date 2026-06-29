import os
import logging
from flask import Flask, jsonify, request
from flask_cors import CORS

from rotas_api import api_bp
from rotas_strava import strava_bp
from public_site import register_public_routes
from admin_bp import admin_bp
from performance_bp import performance_bp

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AURA_APP")

app = Flask(__name__)

# Chave de sessão para o painel admin (usa JWT_SECRET como fallback seguro)
app.secret_key = (
    os.getenv("FLASK_SECRET_KEY")
    or os.getenv("JWT_SECRET")
    or "aura-dev-secret-change-me"
)

# ===================================================
# 🔐 CORS — CONFIGURAÇÃO ULTRA-ROBUSTA PARA IOS
# ===================================================
# Permitimos origins="*" temporariamente para garantir que o 
# handshake do Capacitor (OPTIONS) não retorne 404/403.

_CORS_HEADERS = [
    "Authorization",
    "Content-Type",
    "X-Requested-With",
    "X-Apple-IAP-Id",
    "X-RevenueCat-ETag"
]

CORS(app, resources={
    # Rotas de webhook abertas para servidores externos
    r"/api/webhook/*": {
        "origins": "*",
        "allow_headers": _CORS_HEADERS,
        "methods": ["POST", "OPTIONS"]
    },
    # Ajuste para garantir que o iPhone (capacitor://localhost) seja aceito
    r"/*": {
        "origins": "*",  # Em produção, o ideal é filtrar, mas para o Fix do Login usamos "*"
        "allow_headers": _CORS_HEADERS,
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "expose_headers": ["Content-Range", "X-Content-Range"],
        "supports_credentials": True
    }
})

# 2. Registro de Rotas (Blueprints)
# Registramos com o prefixo /api. 
# Se no rotas_api.py a rota for /auth/register, ela vira /api/auth/register
app.register_blueprint(api_bp, url_prefix='/api')
app.register_blueprint(strava_bp, url_prefix='/strava')
app.register_blueprint(admin_bp)
app.register_blueprint(performance_bp, url_prefix='/api/performance')

# Site publico (landing, suporte, legais) + health JSON em /health e /api/health
register_public_routes(app)

# [AURA DEBUG] Lista todas as rotas no log do Render ao iniciar (apos registro completo)
with app.app_context():
    logger.info("📍 Mapeamento de Rotas Ativo:")
    for rule in app.url_map.iter_rules():
        logger.info(f"Rota: {rule.rule} | Métodos: {rule.methods}")

# ──────────────────────────────────────────────────────────────
# Scheduler de tarefas agendadas
# Chamado aqui (nível de módulo) para que o Gunicorn inicie o
# scheduler em cada worker. O lock MongoDB em scheduler.py
# garante que apenas 1 worker execute cada job por vez.
# Em Flask dev mode com reloader, o guard WERKZEUG_RUN_MAIN
# evita iniciar duas instâncias no processo pai.
# ──────────────────────────────────────────────────────────────
import os as _os
if _os.getenv("WERKZEUG_RUN_MAIN") != "false":  # roda em prod e no child do reloader
    try:
        from scheduler import iniciar_scheduler
        iniciar_scheduler()
    except Exception as _e:
        logger.error(f"❌ Falha ao iniciar scheduler: {_e}")

# 4. Tratamento Global de Erros
@app.errorhandler(404)
def not_found(e):
    logger.warning(f"⚠️ Rota não encontrada: {request.path} [MÉTODO: {request.method}]")
    return jsonify({"erro": f"Rota {request.path} não encontrada no Aura OS"}), 404

@app.errorhandler(400)
def bad_request(e):
    return jsonify({"erro": "Requisição mal formatada ou parâmetros ausentes"}), 400

@app.errorhandler(500)
def server_error(e):
    logger.error(f"❌ Erro Crítico Interno: {e}")
    return jsonify({"erro": "Falha interna no servidor Aura. Verifique os logs no Render."}), 500

# Verificação de Variáveis de Ambiente
if not os.getenv("MONGODB_URI"):
    logger.warning("⚠️ MONGODB_URI não detectada!")

if not os.getenv("MELHOR_ENVIO_TOKEN"):
    logger.warning("⚠️ MELHOR_ENVIO_TOKEN ausente!")

# [AURA LOCAL LAUNCH]
if __name__ == '__main__':
    port = int(os.getenv("PORT", 5050)) 
    logger.info(f"🚀 Aura OS Híbrido iniciando localmente na porta {port}...")
    app.run(host='0.0.0.0', port=port, debug=True)