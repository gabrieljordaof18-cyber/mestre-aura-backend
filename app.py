import os
import requests
from flask import Flask, render_template, request, jsonify, redirect
from flask_cors import CORS
from rotas_api import api_bp  # Importa o teu módulo de rotas existente
from data_manager import salvar_conexao_strava # Importação da integração Strava

# ===================================================
# ⚙️ CONFIGURAÇÃO DO SERVIDOR FLASK
# ===================================================
app = Flask(__name__, template_folder='templates', static_folder='static')

# LIBERA O ACESSO GERAL (CORS)
CORS(app)

# 1. REGISTRA AS ROTAS DE API:
# Todas as rotas de dados (comando, xp, missoes, equilibrio) continuam aqui.
app.register_blueprint(api_bp)

# ===================================================
# 🏃 ROTAS DE INTEGRAÇÃO: STRAVA (AUTENTICAÇÃO)
# ===================================================

@app.route('/auth/strava/login', methods=['GET'])
def strava_login():
    """
    Passo 1: Redireciona o usuário para a página de login do Strava.
    Lê as chaves do ambiente (Render) para montar a URL segura.
    """
    client_id = os.getenv('STRAVA_CLIENT_ID')
    redirect_uri = os.getenv('STRAVA_REDIRECT_URI')
    
    # Monta a URL oficial de autorização
    strava_auth_url = (
        f"https://www.strava.com/oauth/authorize?"
        f"client_id={client_id}&"
        f"response_type=code&"
        f"redirect_uri={redirect_uri}&"
        f"approval_prompt=auto&"
        f"scope=activity:read_all"  # Permissão para ler treinos
    )
    return redirect(strava_auth_url)

@app.route('/auth/strava/callback', methods=['GET'])
def strava_callback():
    """
    Passo 2: O Strava devolve o usuário para cá com um 'code'.
    Nós trocamos esse 'code' pelo Token de Acesso real e SALVAMOS no MongoDB.
    """
    code = request.args.get('code')
    
    if not code:
        return jsonify({"erro": "Nenhum código recebido do Strava"}), 400

    # Configuração para trocar o código pelo token
    token_url = "https://www.strava.com/oauth/token"
    payload = {
        'client_id': os.getenv('STRAVA_CLIENT_ID'),
        'client_secret': os.getenv('STRAVA_CLIENT_SECRET'),
        'code': code,
        'grant_type': 'authorization_code'
    }
    
    # Faz a requisição ao Strava (Back-to-Back)
    response = requests.post(token_url, data=payload)
    dados_recebidos = response.json()
    
    if response.status_code == 200:
        # SUCESSO NA TROCA DE CHAVES!
        
        # 1. Organizar os dados
        athlete_info = dados_recebidos.get('athlete', {})
        tokens = {
            "access_token": dados_recebidos.get('access_token'),
            "refresh_token": dados_recebidos.get('refresh_token'),
            "expires_at": dados_recebidos.get('expires_at')
        }
        
        # 2. Tentar Salvar no Banco de Dados
        sucesso_banco = salvar_conexao_strava(athlete_info, tokens)
        
        if sucesso_banco:
            # Retorna uma página HTML simples confirmando o sucesso
            return """
            <html>
                <body style="background-color: #000; color: #0f0; font-family: sans-serif; text-align: center; padding-top: 50px;">
                    <h1 style="font-size: 3rem;">✅ CONEXÃO ESTABELECIDA!</h1>
                    <p style="font-size: 1.5rem; color: #fff;">O Mestre da Aura agora está sincronizado com o seu Strava.</p>
                    <p style="color: #888;">Seus dados foram salvos com segurança no Banco de Dados.</p>
                    <br>
                    <p>Pode fechar esta janela e voltar ao App.</p>
                </body>
            </html>
            """
        else:
            return jsonify({"erro": "Falha ao salvar no Banco de Dados (MongoDB)"}), 500
            
    else:
        return jsonify({"erro": "Falha ao autenticar com Strava", "detalhes": dados_recebidos}), 400

# ===================================================
# 🔔 WEBHOOK STRAVA (O OUVIDO DO SISTEMA)
# ===================================================

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """
    Rota dupla:
    1. GET: O Strava usa para verificar se existimos (Handshake).
    2. POST: O Strava usa para enviar dados de treino (Notificação Real).
    """
    
    # --- FASE 1: VERIFICAÇÃO (HANDSHAKE) ---
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        VERIFY_TOKEN = "STRAVA_AURA_SECRET" 

        if mode and token:
            if mode == 'subscribe' and token == VERIFY_TOKEN:
                return jsonify({"hub.challenge": challenge}), 200
            else:
                return jsonify({"erro": "Token invalido"}), 403
        return "Webhook ativo", 200

    # --- FASE 2: RECEBER DADOS E PROCESSAR (POST) ---
    if request.method == 'POST':
        dados_evento = request.json
        
        # Aqui conectamos com o "Cérebro" (logic_strava.py)
        try:
            # Importamos aqui dentro para garantir que o arquivo existe
            from logic_strava import processar_evento_webhook
            
            # Chama a função que calcula XP e salva no banco
            processar_evento_webhook(dados_evento)
            
        except ImportError:
            print("❌ ERRO: O arquivo logic_strava.py não foi encontrado!")
        except Exception as e:
            print(f"❌ Erro crítico no webhook: {e}")

        # Sempre respondemos 200 OK rápido para o Strava
        return jsonify({"status": "EVENTO_RECEBIDO"}), 200

# ========================================
# 🌐 ROTAS DE PÁGINAS (FRONT-END ANTIGO)
# ========================================

@app.route('/')
def home():
    """Rota principal do site (Vitrine Pública)."""
    return render_template("index.html")

@app.route('/recurso/mestre')
def mestre_app():
    """Rota para a interface do Mestre da Aura (usado pelo Base44)."""
    return render_template("mestre_painel.html")

# ===================================================
# 🕵️ ROTA DE ESPIÃO (DEBUG)
# ===================================================
@app.route('/debug/usuarios', methods=['GET'])
def ver_usuarios_banco():
    """
    Rota temporária para ver o que está salvo no MongoDB
    sem precisar entrar no site do Atlas.
    """
    from data_manager import mongo_db
    
    if mongo_db is None:
        return jsonify({"erro": "MongoDB não conectado"}), 500

    try:
        # Busca todos os documentos na coleção 'usuarios'
        usuarios = list(mongo_db["usuarios"].find())
        
        # Converte o _id para string
        for user in usuarios:
            user['_id'] = str(user['_id'])
            
        return jsonify({
            "total_usuarios_encontrados": len(usuarios),
            "dados": usuarios
        })
    except Exception as e:
        return jsonify({"erro": f"Erro ao ler banco: {str(e)}"}), 500

# ===================================================
# 🚀 INICIALIZAÇÃO DO SERVIDOR LOCAL
# ===================================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050, debug=True)