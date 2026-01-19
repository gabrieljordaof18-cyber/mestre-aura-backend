import os
import logging
from flask import Flask, jsonify
from flask_cors import CORS

# Importação dos Blueprints (Módulos de Rotas)
from rotas_api import api_bp
# OBS: O arquivo rotas_strava.py será criado no próximo passo.
# Se der erro de importação agora, é normal. Ele sumirá assim que criarmos o arquivo.
from rotas_strava import strava_bp 

# Configuração de Logs (Nuvem)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AURA_APP")

def create_app():
    """
    Fábrica da Aplicação (Padrão robusto para Gunicorn/Render)
    """
    app = Flask(__name__)
    
    # 1. Segurança e CORS
    # Permite requisições do seu Frontend (Base44) e locais
    CORS(app, resources={r"/*": {"origins": "*"}})

    # 2. Registro de Rotas (Blueprints)
    app.register_blueprint(api_bp)       # Rotas da API Principal (Usuário, Missões, Pagamento)
    app.register_blueprint(strava_bp)    # Rotas de Integração Strava (Auth, Webhook)

    # 3. Rota Raiz (Health Check)
    # Substitui a antiga página HTML por um JSON de status simples
    @app.route('/')
    def health_check():
        return jsonify({
            "status": "online",
            "system": "Aura Performance API",
            "version": "2.0.1",
            "env": os.environ.get("FLASK_ENV", "production")
        })

    return app

# Instância da aplicação para o servidor WSGI
app = create_app()

if __name__ == '__main__':
    # Inicialização Local (Dev)
    # Pega a porta do .env ou usa 5000 como padrão
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Aura API iniciando na porta {port}...")
    app.run(host='0.0.0.0', port=port, debug=True)