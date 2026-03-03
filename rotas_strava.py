import os
import logging
import requests
from flask import Blueprint, request, jsonify, redirect

# Importações de Lógica e Dados
from data_manager import salvar_conexao_strava
from logic_strava import processar_evento_webhook

# Configuração de Logs
logger = logging.getLogger("AURA_STRAVA")

# Criação do Blueprint
strava_bp = Blueprint('strava_bp', __name__)

# ===================================================
# 🏃 AUTENTICAÇÃO OAUTH2 (VÍNCULO DE CONTA)
# ===================================================

@strava_bp.route('/auth/strava/login', methods=['GET'])
def strava_login():
    """Redireciona o atleta para a autorização do Strava."""
    client_id = os.getenv('STRAVA_CLIENT_ID')
    # No Render, define a STRAVA_REDIRECT_URI nas variáveis de ambiente
    redirect_uri = os.getenv('STRAVA_REDIRECT_URI', 'http://localhost:5050/api/auth/strava/callback')
    
    if not client_id:
        return jsonify({"erro": "STRAVA_CLIENT_ID não configurado"}), 500

    # Scopes necessários para leitura detalhada de treinos e perfil
    scope = "read,activity:read_all,profile:read_all"
    
    strava_auth_url = (
        f"https://www.strava.com/oauth/authorize?"
        f"client_id={client_id}&"
        f"response_type=code&"
        f"redirect_uri={redirect_uri}&"
        f"approval_prompt=auto&"
        f"scope={scope}"
    )
    
    logger.info("🔄 Redirecionando atleta para o Strava...")
    return redirect(strava_auth_url)

@strava_bp.route('/auth/strava/callback', methods=['GET'])
def strava_callback():
    """Recebe o código do Strava e troca por tokens permanentes."""
    code = request.args.get('code')
    error = request.args.get('error')

    if error or not code:
        logger.error(f"❌ Erro no Callback Strava: {error}")
        return jsonify({"erro": "Autorização cancelada ou falhou"}), 400

    # Troca Code por Access & Refresh Tokens
    try:
        token_url = "https://www.strava.com/oauth/token"
        payload = {
            'client_id': os.getenv('STRAVA_CLIENT_ID'),
            'client_secret': os.getenv('STRAVA_CLIENT_SECRET'),
            'code': code,
            'grant_type': 'authorization_code'
        }
        
        response = requests.post(token_url, data=payload, timeout=10)
        dados = response.json()
        
        if response.status_code == 200:
            atleta = dados.get('athlete', {})
            tokens = {
                "access_token": dados.get('access_token'),
                "refresh_token": dados.get('refresh_token'),
                "expires_at": dados.get('expires_at')
            }
            
            # Persistência no MongoDB (Schema 2.0)
            # Nota: O salvar_conexao_strava deve associar estes dados ao utilizador logado
            if salvar_conexao_strava(atleta, tokens):
                logger.info(f"✅ Atleta {atleta.get('firstname')} conectado com sucesso!")
                
                # Interface de Confirmação Dark Mode
                return """
                <html>
                    <body style="background: #09090b; color: #10b981; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0;">
                        <div style="text-align: center; border: 1px solid #10b981; padding: 3rem; border-radius: 1rem; background: #18181b; box-shadow: 0 0 30px rgba(16, 185, 129, 0.1);">
                            <h1 style="margin: 0 0 1rem 0;">AURA SYNC</h1>
                            <p style="color: #a1a1aa;">Conexão neural estabelecida com o Strava.</p>
                            <div style="font-size: 3rem; margin: 1.5rem 0;">⚡</div>
                            <p style="font-size: 0.8rem; color: #71717a;">Pode fechar esta aba e voltar ao app.</p>
                        </div>
                    </body>
                </html>
                """
        return jsonify({"erro": "Falha na troca de tokens"}), 400

    except Exception as e:
        logger.error(f"❌ Erro crítico no Callback: {e}")
        return jsonify({"erro": "Erro interno no servidor"}), 500

# ===================================================
# 🔔 WEBHOOK (SINCRONIZAÇÃO AUTOMÁTICA)
# ===================================================

@strava_bp.route('/webhook', methods=['GET', 'POST'])
def webhook_strava():
    """Ouvinte de novos treinos em tempo real."""
    
    # 1. Validação (Handshake) exigida pelo Strava
    if request.method == 'GET':
        challenge = request.args.get('hub.challenge')
        verify_token = request.args.get('hub.verify_token')
        
        # Este token deve ser o mesmo que configuraste no painel do Strava API
        STRAVA_VERIFY_TOKEN = os.getenv('STRAVA_WEBHOOK_TOKEN', 'AURA_SECRET_2024')

        if verify_token == STRAVA_VERIFY_TOKEN:
            return jsonify({"hub.challenge": challenge}), 200
        return "Token inválido", 403

    # 2. Recebimento de Atividades (POST)
    if request.method == 'POST':
        evento = request.get_json()
        logger.info(f"🔔 Webhook Strava: Novo evento de {evento.get('object_type')}")
        
        # Processa em background (ou diretamente para o MVP)
        try:
            processar_evento_webhook(evento)
            return jsonify({"status": "recebido"}), 200
        except Exception as e:
            logger.error(f"❌ Erro ao processar atividade via Webhook: {e}")
            return jsonify({"status": "erro"}), 200 # Retornamos 200 para o Strava não re-tentar erro