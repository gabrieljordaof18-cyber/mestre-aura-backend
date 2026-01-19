import os
import logging
import requests
from flask import Blueprint, request, jsonify, redirect

# Importações de Lógica e Dados
# Nota: Esses arquivos serão refatorados a seguir, mas a importação já fica correta.
from data_manager import salvar_conexao_strava
from logic_strava import processar_evento_webhook

# Configuração de Logs
logger = logging.getLogger("AURA_STRAVA")

# Criação do Blueprint (Módulo de Rotas)
strava_bp = Blueprint('strava_bp', __name__)

# ===================================================
# 🏃 ROTAS DE AUTENTICAÇÃO (LOGIN NO STRAVA)
# ===================================================

@strava_bp.route('/auth/strava/login', methods=['GET'])
def strava_login():
    """
    Inicia o fluxo OAuth2. Redireciona o usuário para o site do Strava.
    """
    client_id = os.getenv('STRAVA_CLIENT_ID')
    # Ajuste: No Render, a REDIRECT_URI deve ser a URL de produção. 
    # Em local, pode ser http://localhost:5000/auth/strava/callback
    redirect_uri = os.getenv('STRAVA_REDIRECT_URI', 'http://localhost:5000/auth/strava/callback')
    
    if not client_id:
        return jsonify({"erro": "Configuração STRAVA_CLIENT_ID ausente"}), 500

    strava_auth_url = (
        f"https://www.strava.com/oauth/authorize?"
        f"client_id={client_id}&"
        f"response_type=code&"
        f"redirect_uri={redirect_uri}&"
        f"approval_prompt=auto&"
        f"scope=activity:read_all,profile:read_all"
    )
    logger.info("🔄 Iniciando redirecionamento para login Strava...")
    return redirect(strava_auth_url)

@strava_bp.route('/auth/strava/callback', methods=['GET'])
def strava_callback():
    """
    O Strava devolve o usuário para cá com um 'code'.
    Trocamos esse code por um Token de Acesso permanente.
    """
    code = request.args.get('code')
    erro = request.args.get('error')

    if erro:
        logger.error(f"❌ Erro retornado pelo Strava: {erro}")
        return jsonify({"erro": "Acesso negado pelo usuário no Strava"}), 400
    
    if not code:
        return jsonify({"erro": "Nenhum código recebido"}), 400

    # Troca Code por Token
    token_url = "https://www.strava.com/oauth/token"
    payload = {
        'client_id': os.getenv('STRAVA_CLIENT_ID'),
        'client_secret': os.getenv('STRAVA_CLIENT_SECRET'),
        'code': code,
        'grant_type': 'authorization_code'
    }
    
    try:
        response = requests.post(token_url, data=payload)
        dados = response.json()
        
        if response.status_code == 200:
            # Dados do Atleta e Tokens
            athlete_info = dados.get('athlete', {})
            tokens = {
                "access_token": dados.get('access_token'),
                "refresh_token": dados.get('refresh_token'),
                "expires_at": dados.get('expires_at')
            }
            
            # Salva no MongoDB (via Data Manager)
            sucesso = salvar_conexao_strava(athlete_info, tokens)
            
            if sucesso:
                logger.info(f"✅ Usuário {athlete_info.get('firstname')} conectado com sucesso!")
                # Página de Sucesso (Estilo Matrix/Dark)
                return """
                <html>
                    <body style="background-color: #0f172a; color: #4ade80; font-family: 'Courier New', sans-serif; text-align: center; display: flex; flex-direction: column; justify-content: center; height: 100vh; margin: 0;">
                        <div style="border: 2px solid #4ade80; padding: 40px; border-radius: 10px; max-width: 500px; margin: 0 auto; box-shadow: 0 0 20px rgba(74, 222, 128, 0.2);">
                            <h1 style="font-size: 2.5rem; margin-bottom: 10px;">CONEXÃO ESTABELECIDA</h1>
                            <p style="font-size: 1.2rem; color: #e2e8f0;">O Mestre da Aura agora está sincronizado com seus dados.</p>
                            <div style="margin-top: 30px; font-size: 3rem;">🛰️ ✅</div>
                            <p style="color: #64748b; margin-top: 30px;">Pode fechar esta janela e retornar ao App.</p>
                        </div>
                    </body>
                </html>
                """
            else:
                return jsonify({"erro": "Falha crítica ao salvar no banco de dados."}), 500
        else:
            logger.error(f"❌ Falha na troca de token Strava: {dados}")
            return jsonify({"erro": "Falha na autenticação com Strava API"}), 400

    except Exception as e:
        logger.error(f"❌ Erro de conexão Strava: {e}")
        return jsonify({"erro": "Erro interno no servidor"}), 500

# ===================================================
# 🔔 WEBHOOK (O OUVIDO DO SISTEMA)
# ===================================================

@strava_bp.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """
    Endpoint que o Strava chama quando você termina um treino.
    """
    # FASE 1: Verificação (Handshake) - O Strava chama isso ao configurar
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        # Token de segurança definido por nós (pode ir para o .env futuramente)
        VERIFY_TOKEN = "STRAVA_AURA_SECRET" 

        if mode and token:
            if mode == 'subscribe' and token == VERIFY_TOKEN:
                logger.info("✅ Webhook Strava verificado com sucesso.")
                return jsonify({"hub.challenge": challenge}), 200
            else:
                return jsonify({"erro": "Token de verificação inválido"}), 403
        return "Webhook Aura Ativo", 200

    # FASE 2: Recebimento de Eventos (POST) - Quando alguém treina
    if request.method == 'POST':
        dados_evento = request.json
        logger.info(f"🔔 Evento Webhook Recebido: {dados_evento.get('object_type')}")
        
        try:
            # Processamento Assíncrono (Idealmente)
            # Por enquanto, chamamos a lógica direta
            processar_evento_webhook(dados_evento)
            return jsonify({"status": "EVENTO_PROCESSADO"}), 200
            
        except Exception as e:
            logger.error(f"❌ Erro ao processar webhook: {e}")
            # Retornamos 200 mesmo com erro para o Strava não ficar tentando reenviar infinitamente
            return jsonify({"status": "ERRO_PROCESSAMENTO"}), 200