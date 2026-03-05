import os
import logging
import requests
from flask import Blueprint, request, jsonify, redirect

# Importações de Lógica e Dados
# [AURA FIX] Garantindo que as rotas utilizem o Data Manager sincronizado com o Atlas
from data_manager import salvar_conexao_strava
from logic_strava import processar_evento_webhook
from data_sensores import obter_dados_fisiologicos # Para sync imediato pós-login

# Configuração de Logs
logger = logging.getLogger("AURA_STRAVA")

# Criação do Blueprint
# [AURA INFO] O prefixo '/strava' é definido no create_app() do app.py
strava_bp = Blueprint('strava_bp', __name__)

# ===================================================
# 🏃 AUTENTICAÇÃO OAUTH2 (VÍNCULO DE CONTA)
# ===================================================

@strava_bp.route('/auth/strava/login', methods=['GET'])
def strava_login():
    """Redireciona o atleta para a autorização do Strava."""
    client_id = os.getenv('STRAVA_CLIENT_ID')
    
    # [AURA FIX] Sincronização de URI: Detecta se está no Render ou Localhost
    # No Dashboard do Strava, a Redirect URI deve ser a do Render em produção.
    redirect_uri = os.getenv('STRAVA_REDIRECT_URI')
    
    if not client_id:
        logger.error("❌ STRAVA_CLIENT_ID ausente nas variáveis de ambiente.")
        return jsonify({"erro": "Configuração do servidor incompleta (Client ID)"}), 500

    # Scopes robustos para leitura detalhada de treinos e perfil (Necessário para IA Híbrida)
    # 'activity:read_all' é fundamental para a IA entender o histórico do atleta
    scope = "read,activity:read_all,profile:read_all"
    
    strava_auth_url = (
        f"https://www.strava.com/oauth/authorize?"
        f"client_id={client_id}&"
        f"response_type=code&"
        f"redirect_uri={redirect_uri}&"
        f"approval_prompt=auto&"
        f"scope={scope}"
    )
    
    logger.info(f"🔄 Iniciando fluxo OAuth Strava para URI: {redirect_uri}")
    return redirect(strava_auth_url)

@strava_bp.route('/auth/strava/callback', methods=['GET'])
def strava_callback():
    """Recebe o código do Strava e troca por tokens permanentes."""
    code = request.args.get('code')
    error = request.args.get('error')

    if error or not code:
        logger.error(f"❌ Erro no Callback Strava ou autorização negada: {error}")
        return jsonify({"erro": "Autorização do Strava foi cancelada ou falhou"}), 400

    # Troca Code por Access & Refresh Tokens
    try:
        token_url = "https://www.strava.com/oauth/token"
        payload = {
            'client_id': os.getenv('STRAVA_CLIENT_ID'),
            'client_secret': os.getenv('STRAVA_CLIENT_SECRET'),
            'code': code,
            'grant_type': 'authorization_code'
        }
        
        # [AURA INFO] Timeout de 10s para evitar que o Render trave se a API do Strava oscilar
        response = requests.post(token_url, data=payload, timeout=10)
        dados = response.json()
        
        if response.status_code == 200:
            atleta = dados.get('athlete', {})
            tokens = {
                "access_token": dados.get('access_token'),
                "refresh_token": dados.get('refresh_token'),
                "expires_at": dados.get('expires_at')
            }
            
            # Persistência no MongoDB Atlas (Coleção 'usuarios')
            # Extraímos o ID do atleta para facilitar o sync posterior
            strava_atleta_id = str(atleta.get('id'))
            
            if salvar_conexao_strava(atleta, tokens):
                logger.info(f"✅ Sincronização Completa: Atleta {atleta.get('firstname')} vinculado.")
                
                # [AURA ROBUST] Tentamos forçar uma primeira coleta de dados para alimentar a IA
                # Isso permite que o Mestre Aura já conheça o histórico do atleta no primeiro chat
                try:
                    # Buscamos o ID interno do usuário que acabamos de vincular
                    from data_manager import mongo_db
                    user_doc = mongo_db["usuarios"].find_one({"integracoes.strava.atleta_id": strava_atleta_id})
                    if user_doc:
                        obter_dados_fisiologicos(str(user_doc["_id"]))
                except:
                    pass

                # Interface de Confirmação Estilizada
                return """
                <html>
                    <head><title>AURA SYNC</title><meta charset="UTF-8"></head>
                    <body style="background: #09090b; color: #10b981; font-family: 'Inter', sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0;">
                        <div style="text-align: center; border: 1px solid #10b981; padding: 3rem; border-radius: 1.5rem; background: #18181b; box-shadow: 0 10px 40px rgba(16, 185, 129, 0.15); max-width: 400px;">
                            <div style="font-size: 4rem; margin-bottom: 1.5rem;">⚡</div>
                            <h1 style="margin: 0 0 0.5rem 0; letter-spacing: -1px;">SINCRO ESTABELECIDA</h1>
                            <p style="color: #a1a1aa; line-height: 1.5;">O Mestre da Aura agora tem acesso ao seu histórico esportivo para gerar treinos híbridos.</p>
                            <hr style="border: 0; border-top: 1px solid #27272a; margin: 2rem 0;">
                            <p style="font-size: 0.85rem; color: #71717a; font-weight: bold;">FECHE ESTA ABA E VOLTE AO APP.</p>
                        </div>
                    </body>
                </html>
                """
            else:
                logger.error("❌ Falha ao persistir dados do Strava no MongoDB.")
                return jsonify({"erro": "Erro ao salvar vínculo no banco de dados"}), 500
                
        logger.error(f"❌ Strava Token Exchange falhou: {response.text}")
        return jsonify({"erro": "Falha na troca de tokens com o servidor do Strava"}), 400

    except Exception as e:
        logger.error(f"❌ Erro crítico no Callback Strava: {e}")
        return jsonify({"erro": "Erro interno no servidor Aura"}), 500

# ===================================================
# 🔔 WEBHOOK (SINCRONIZAÇÃO AUTOMÁTICA EM TEMPO REAL)
# ===================================================

@strava_bp.route('/webhook', methods=['GET', 'POST'])
def webhook_strava():
    """
    Ouvinte passivo para atualizações do Strava (Webhooks).
    Sincroniza novos treinos automaticamente com o Render e Atlas.
    """
    
    # 1. Validação de Handshake (Segurança exigida pelo Strava)
    if request.method == 'GET':
        challenge = request.args.get('hub.challenge')
        verify_token = request.args.get('hub.verify_token')
        
        # [AURA FIX] Verificação do Token configurado no Painel do Desenvolvedor Strava
        STRAVA_VERIFY_TOKEN = os.getenv('STRAVA_WEBHOOK_TOKEN', 'AURA_SECRET_2026')

        if verify_token == STRAVA_VERIFY_TOKEN:
            logger.info("✅ Handshake do Webhook Strava validado com sucesso.")
            return jsonify({"hub.challenge": challenge}), 200
        
        logger.warning(f"⚠️ Tentativa de validação de Webhook com token inválido.")
        return "Token de verificação inválido", 403

    # 2. Recebimento de Atividades (Processamento Assíncrono)
    if request.method == 'POST':
        evento = request.get_json()
        
        # Logamos o recebimento para depuração no Render
        logger.info(f"🔔 Novo evento Strava: {evento.get('aspect_type')} de {evento.get('object_type')}")
        
        try:
            # Processamento do evento para atualizar XP e contexto biofísico
            processar_evento_webhook(evento)
            return jsonify({"status": "recebido"}), 200
        except Exception as e:
            logger.error(f"❌ Falha no processamento do Webhook: {e}")
            return jsonify({"status": "erro_interno_processado"}), 200