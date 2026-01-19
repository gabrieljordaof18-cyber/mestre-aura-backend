import logging
import os
import requests # <--- A CORREÇÃO ESTÁ AQUI (Faltava essa linha)
import jwt
from functools import wraps
from datetime import datetime
from typing import Dict, Any
from flask import request, jsonify, Blueprint

# --- IMPORTAÇÕES DA NOVA ARQUITETURA ---
from data_user import carregar_memoria, salvar_memoria, obter_status_fisiologico
from data_manager import obter_ranking_global, ler_plano 
from logic_gamificacao import gerar_missoes_diarias, aplicar_xp
from logic_equilibrio import calcular_e_atualizar_equilibrio
from logic import processar_comando 
from logic_feedback import gerar_feedback_emocional
from logic_asaas import criar_cobranca # Agora com persistência

# Configuração de Logs
logger = logging.getLogger("AURA_API_ROTAS")

api_bp = Blueprint('api_bp', __name__, url_prefix='/api')

# ===================================================
# 🔐 MIDDLEWARE DE AUTENTICAÇÃO (TOKEN/ID)
# ===================================================

def token_required(f):
    """
    Decorador que protege as rotas.
    Espera um Header 'Authorization: Bearer <USER_ID_OU_TOKEN>'
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # 1. Tenta pegar do Header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1] # Remove "Bearer "
            except IndexError:
                return jsonify({"erro": "Token mal formatado"}), 401
        
        if not token:
            return jsonify({"erro": "Token de autenticação ausente"}), 401

        try:
            # PARA O MVP: Aceitamos o próprio User ID como token temporário
            # Futuro: Decodificar JWT aqui (jwt.decode(token, SECRET...))
            current_user_id = token 
            
            # Se fosse JWT real:
            # data = jwt.decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
            # current_user_id = data['user_id']
            
        except Exception as e:
            logger.error(f"Erro de auth: {e}")
            return jsonify({"erro": "Token inválido ou expirado"}), 401

        # Injeta o user_id na função da rota
        return f(current_user_id, *args, **kwargs)

    return decorated

# ===================================================
# 💳 PAGAMENTOS (ASAAS)
# ===================================================

@api_bp.route('/pagamento/criar', methods=['POST'])
@token_required
def criar_pagamento_asaas(current_user_id):
    """
    Cria cobrança e vincula ao usuário logado.
    """
    try:
        dados = request.get_json(force=True)
        if not dados:
            return jsonify({"erro": "Payload vazio"}), 400
            
        # Injeta o ID do usuário para persistência
        dados['user_id'] = current_user_id
        
        # Chama a lógica (agora segura e persistente)
        resultado = criar_cobranca(dados)
        
        if "erro" in resultado:
            return jsonify(resultado), 400
            
        return jsonify(resultado)

    except Exception as e:
        logger.error(f"Erro na rota de pagamento: {e}")
        return jsonify({"erro": "Falha ao processar pagamento."}), 500

@api_bp.route('/pagamento/pix/qrcode/<id_pagamento>', methods=['GET'])
# Esta rota pode ser pública ou protegida, dependendo da UX. Deixaremos pública por enquanto.
def recuperar_qrcode_pix(id_pagamento):
    try:
        from logic_asaas import ASAAS_URL, get_headers
        headers = get_headers()
        
        url = f"{ASAAS_URL}/payments/{id_pagamento}/pixQrCode"
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            return jsonify({
                "sucesso": True,
                "payload_pix": data.get('payload'),
                "imagem_qr": data.get('encodedImage')
            })
        else:
            return jsonify({"erro": "QR Code não disponível ou expirado."}), 400
    except Exception as e:
        logger.error(f"Erro recuperação Pix: {e}")
        return jsonify({"erro": "Erro interno"}), 500

# ===================================================
# 👤 USUÁRIO E STATUS
# ===================================================

@api_bp.route('/usuario/status', methods=['GET'])
@token_required
def get_status_jogador(current_user_id):
    try:
        dados = carregar_memoria(current_user_id)
        
        if not dados:
            return jsonify({"erro": "Perfil não encontrado"}), 404
            
        jogador = dados.get("jogador", {})
        integracoes = dados.get("integracoes", {})
        
        xp_atual = jogador.get("experiencia", 0)
        nivel_atual = jogador.get("nivel", 1)
        
        # Lógica visual de barra de progresso (Presentation Logic)
        XP_BASE = 1000
        xp_prox = XP_BASE * nivel_atual
        xp_anterior = XP_BASE * (nivel_atual - 1)
        
        # Evita divisão por zero no nível 1
        range_nivel = xp_prox - xp_anterior
        xp_no_nivel = xp_atual - xp_anterior
        
        progresso = int((xp_no_nivel / range_nivel) * 100) if range_nivel > 0 else 0
        
        # Simplificando retorno para o Frontend
        return jsonify({
            "nome": jogador.get("nome", "Atleta"),
            "foto": dados.get("profile_picture_url", ""),
            "xp_total": xp_atual,
            "aura_coins": jogador.get("saldo_coins", 0),
            "saldo_cristais": jogador.get("saldo_cristais", 0),
            "nivel": nivel_atual,
            "xp_necessario_proximo": range_nivel - xp_no_nivel,
            "barra_progresso": progresso,
            "strava_conectado": integracoes.get("strava", {}).get("conectado", False)
        })
    except Exception as e:
        logger.error(f"Erro status usuário: {e}")
        return jsonify({"erro": "Falha ao carregar perfil"}), 500

@api_bp.route('/cla/ranking', methods=['GET'])
def get_ranking_cla():
    # Rota pública (pode ser vista sem login para atrair novos usuários)
    try:
        ranking = obter_ranking_global(limite=20) 
        return jsonify({"ranking": ranking})
    except Exception as e:
        logger.error(f"Erro no ranking: {e}")
        return jsonify({"ranking": []})

@api_bp.route('/antifraude/validar', methods=['POST'])
@token_required
def validar_atividade(current_user_id):
    """
    Verifica se existe atividade no Strava na data informada.
    """
    try:
        dados_input = request.get_json(force=True)
        data_declarada = dados_input.get('data') 
        
        # Agora buscamos na coleção de atividades reais
        from data_manager import mongo_db
        if mongo_db is None: return jsonify({"erro": "Banco offline"}), 500

        # Busca simples por data string (YYYY-MM-DD)
        # Nota: Idealmente faríamos range de data, mas string match serve para MVP
        existe = mongo_db["activities"].find_one({
            "user_id": current_user_id,
            "start_date_local": {"$regex": f"^{data_declarada}"}
        })
        
        if existe: 
            return jsonify({"aprovado": True, "msg": "Atividade Strava localizada!"})
        else: 
            return jsonify({"aprovado": False, "motivo": "Nenhum registro no Strava nesta data."})
            
    except Exception as e:
        logger.error(f"Erro antifraude: {e}")
        return jsonify({"aprovado": False, "motivo": "Erro técnico."}), 500

# ===================================================
# 🧠 CÉREBRO E GAMIFICAÇÃO
# ===================================================

@api_bp.route('/comando', methods=['POST'])
@token_required
def comando(current_user_id):
    try:
        dados = request.get_json(force=True) 
        mensagem = dados.get('comando', '').strip()
        
        if not mensagem: return jsonify({"resposta": "..."})
        
        resposta = processar_comando(current_user_id, mensagem)
        return jsonify({"resposta": resposta})
    except Exception as e:
        logger.error(f"Erro no chat: {e}")
        return jsonify({"resposta": "⚠️ Erro de comunicação com o Mestre."})

@api_bp.route('/missoes', methods=['GET'])
@token_required
def listar_missoes(current_user_id):
    # Gera ou recupera missões do usuário específico
    missoes = gerar_missoes_diarias(current_user_id)
    return jsonify({"missoes": missoes})

@api_bp.route('/missoes/gerar', methods=['POST'])
@token_required
def rota_gerar_missoes(current_user_id):
    # Força regeneração (se a lógica permitir)
    missoes = gerar_missoes_diarias(current_user_id)
    return jsonify({"mensagem": "Missões sincronizadas.", "missoes": missoes})

@api_bp.route('/concluir_missao', methods=['POST'])
@token_required
def concluir_missao(current_user_id):
    try:
        dados = request.get_json(force=True)
        missao_id = dados.get("id")
        
        memoria = carregar_memoria(current_user_id)
        missoes = memoria.get("gamificacao", {}).get("missoes_ativas", [])
        
        missao_alvo = None
        for m in missoes:
            if m["id"] == missao_id:
                if m.get("concluida"): return jsonify({"erro": "Já concluída!"}), 400
                m["concluida"] = True
                missao_alvo = m
                break
        
        if missao_alvo:
            xp = missao_alvo.get("xp", 0)
            
            # Aplica XP e salva
            salvar_memoria(current_user_id, memoria)
            resultado = aplicar_xp(current_user_id, xp)
            
            return jsonify({
                "sucesso": True, 
                "msg": f"Concluída! +{xp} XP", 
                "novo_nivel": resultado["novo_nivel"],
                "subiu_nivel": resultado["subiu"]
            })
            
        return jsonify({"erro": "Missão não encontrada"}), 404
    except Exception as e:
        logger.error(f"Erro concluir missão: {e}")
        return jsonify({"erro": "Falha interna"}), 500

# ===================================================
# ⚕️ SAÚDE E BIOHACKING
# ===================================================

@api_bp.route('/equilibrio', methods=['GET'])
@token_required
def obter_equilibrio(current_user_id):
    # Calcula na hora ou recupera o último
    memoria = carregar_memoria(current_user_id)
    homeostase = memoria.get("homeostase", {"score": 0, "estado": "Calculando..."})
    return jsonify(homeostase)

@api_bp.route('/status_fisiologico', methods=['GET'])
@token_required
def status_fisiologico(current_user_id):
    # Aqui poderíamos chamar obter_dados_fisiologicos(current_user_id) para forçar sync
    # Mas para leitura rápida, pegamos do banco direto
    memoria = carregar_memoria(current_user_id)
    return jsonify(memoria.get("dados_fisiologicos", {}))

@api_bp.route('/feedback', methods=['GET'])
@token_required
def feedback(current_user_id):
    texto = gerar_feedback_emocional(current_user_id)
    return jsonify({"texto": texto})

@api_bp.route('/sincronizar_dinamico', methods=['POST'])
@token_required
def sincronizar_dinamico(current_user_id):
    """
    Rota chamada pelo botão 'Sincronizar' do app.
    Força a ida ao Strava/Sensores.
    """
    from data_sensores import obter_dados_fisiologicos
    
    # 1. Busca dados novos nos sensores
    novos_dados = obter_dados_fisiologicos(current_user_id)
    
    # 2. Recalcula equilíbrio com esses dados
    calcular_e_atualizar_equilibrio(current_user_id)
    
    return jsonify({"dados": novos_dados})

@api_bp.route('/usuario/planos', methods=['GET'])
@token_required
def get_plano_usuario(current_user_id):
    try:
        tipo = request.args.get('tipo') 
        if tipo not in ['dieta', 'treino']: 
            return jsonify({"erro": "Tipo inválido."}), 400
        
        dados_plano = ler_plano(current_user_id, tipo)
        return jsonify({"tipo": tipo, "dados": dados_plano})
    except Exception as e:
        logger.error(f"Erro ao buscar plano: {e}")
        return jsonify({"erro": "Falha ao carregar plano."}), 500