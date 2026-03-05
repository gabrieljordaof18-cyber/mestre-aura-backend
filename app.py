import os
import logging
from flask import Flask, jsonify
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

def create_app():
    """
    Fábrica da Aplicação: Configura segurança, rotas e tratamento de erros.
    """
    app = Flask(__name__)
    
    # 1. Segurança e CORS
    # [AURA FIX] Ajustado para garantir que o Base44 consiga enviar Authorization Headers sem bloqueio.
    CORS(app, resources={r"/*": {
        "origins": "*",
        "allow_headers": ["Authorization", "Content-Type"],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    }})

    # 2. Registro de Rotas (Blueprints)
    # Organizamos com prefixos para evitar conflitos de URL
    app.register_blueprint(api_bp)                        # Prefixo definido no arquivo: /api
    app.register_blueprint(strava_bp, url_prefix='/strava') # Forçamos o prefixo /strava

    # 3. Rota Raiz (Health Check)
    @app.route('/')
    def health_check():
        return jsonify({
            "status": "online",
            "system": "Aura Performance OS",
            "version": "2.0.1",
            "env": os.getenv("FLASK_ENV", "production")
        })

    # 4. Tratamento Global de Erros (Evita crash no App)
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"erro": "Rota não encontrada"}), 404

    @app.errorhandler(500)
    def server_error(e):
        logger.error(f"Erro interno: {e}")
        return jsonify({"erro": "Falha interna no servidor Aura"}), 500

    return app

# Instância para o Gunicorn (Render usa esta variável 'app')
app = create_app()

if __name__ == '__main__':
    # Configuração para rodar localmente no seu MacBook
    port = int(os.getenv("PORT", 5050)) # Prioriza a porta 5050 do seu .env
    logger.info(f"🚀 Aura OS iniciando na porta {port}...")
    
    # No seu Mac, usamos debug=True para ver as mudanças em tempo real
    # O Render ignora o __main__, então o debug=True não afetará a produção.
    app.run(host='0.0.0.0', port=port, debug=True)