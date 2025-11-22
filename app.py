import os
import requests
from flask import Flask, render_template, request, jsonify, redirect
from flask_cors import CORS
from rotas_api import api_bp  # Importa o teu módulo de rotas existente

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
# 🏃 ROTAS DE INTEGRAÇÃO: STRAVA (NOVO)
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
    Nós trocamos esse 'code' pelo Token de Acesso real.
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
    dados_token = response.json()
    
    if response.status_code == 200:
        # SUCESSO!
        # Aqui temos o access_token e refresh_token.
        # Por enquanto, mostramos na tela para confirmar que funcionou.
        athlete_info = dados_token.get('athlete', {})
        access_token = dados_token.get('access_token')
        
        return jsonify({
            "status": "CONEXAO_SUCESSO",
            "mensagem": f"Olá, {athlete_info.get('firstname')}! Conectado ao AURA.",
            "id_atleta": athlete_info.get('id'),
            "token_teste": access_token  # Mostramos só para debug
        })
    else:
        return jsonify({"erro": "Falha ao autenticar com Strava", "detalhes": dados_token}), 400

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
# 🚀 INICIALIZAÇÃO DO SERVIDOR LOCAL
# ===================================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050, debug=True)