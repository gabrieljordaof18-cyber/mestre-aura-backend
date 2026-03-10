import os
import logging
from flask import Flask, jsonify, request  # [AURA FIX] Importação do 'request' unificada
from flask_cors import CORS

# Importação dos Blueprints (Módulos de Rotas)
# Certifique-se que os arquivos rotas_api.py e rotas_strava.py existam na mesma pasta
from rotas_api import api_bp
from rotas_strava import strava_bp 

# Configuração de Logs (Nuvem/Render)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AURA_APP")

# [AURA STABLE SOLUTION] Instanciamos o app diretamente no escopo global.
# Isso garante que o Gunicorn (Render) carregue as rotas instantaneamente ao importar o arquivo.
app = Flask(__name__)

# 1. Segurança e CORS (Otimizado para Assinaturas Nativas e Webhooks)
# [AURA FIX] Ajustado para garantir que o RevenueCat (Webhooks) e o Base44 consigam enviar dados.
# Liberamos 'X-Apple-IAP-Id' e outros headers comuns em transações de aplicativos.
CORS(app, resources={r"/*": {
    "origins": "*",
    "allow_headers": [
        "Authorization", 
        "Content-Type", 
        "X-Requested-With", 
        "X-Apple-IAP-Id", 
        "X-RevenueCat-ETag"
    ],
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "expose_headers": ["Content-Range", "X-Content-Range"]
}})

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