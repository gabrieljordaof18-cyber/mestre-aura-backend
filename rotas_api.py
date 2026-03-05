import logging
import os
import requests
import jwt
from functools import wraps
from datetime import datetime
from typing import Dict, Any
from flask import request, jsonify, Blueprint

# --- IMPORTAÇÕES DA NOVA ARQUITETURA ---
from data_user import carregar_memoria, salvar_memoria
from data_manager import obter_ranking_global, ler_plano, mongo_db
from logic_gamificacao import gerar_missoes_diarias, aplicar_xp
from logic_equilibrio import calcular_e_atualizar_equilibrio
from logic import processar_comando 
from logic_feedback import gerar_feedback_emocional
from logic_asaas import criar_cobranca

# Configuração de Logs
logger = logging.getLogger("AURA_API_ROTAS")

api_bp = Blueprint('api_bp', __name__, url_prefix='/api')

# ===================================================
# 🔐 MIDDLEWARE DE AUTENTICAÇÃO (SEGURANÇA 2.0)
# ===================================================

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                # O Base44 costuma enviar "Bearer ID_DO_USUARIO"
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({"erro": "Token mal formatado"}), 401
        
        if not token:
            return jsonify({"erro": "Token ausente"}), 401

        try:
            # [AURA FIX] Limpeza rigorosa para garantir que o ID chegue limpo ao MongoDB
            current_user_id = str(token).strip().replace('"', '').replace("'", "")
        except Exception as e:
            logger.error(f"Erro de auth: {e}")
            return jsonify({"erro": "Sessão inválida"}), 401

        return f(current_user_id, *args, **kwargs)
    return decorated

# ===================================================
# 👤 STATUS E PROGRESSÃO (MULTIJOGADOR)
# ===================================================

@api_bp.route('/usuario/status', methods=['GET'])
@token_required
def get_status_jogador(current_user_id):
    try:
        dados = carregar_memoria(current_user_id)
        if not dados: 
            return jsonify({"erro": "Perfil não encontrado no Atlas"}), 404
            
        # [AURA FIX] Sincronização direta com a RAIZ do seu MongoDB
        xp_atual = int(dados.get("xp_total", 0))
        nivel_atual = int(dados.get("nivel", 1))
        nome_atleta = dados.get("nome", "Atleta Aura")
        # [AURA FIX] Mapeado para 'moedas' conforme seu JSON manual do Atlas
        coins = dados.get("moedas", 0)
        
        # Lógica de Barra de Progresso (Calculada no Backend para evitar bugs na UI)
        XP_BASE = 1000
        xp_prox = XP_BASE * nivel_atual
        xp_anterior = XP_BASE * (nivel_atual - 1)
        range_nivel = xp_prox - xp_anterior
        xp_no_nivel = xp_atual - xp_anterior
        
        # Garantir que o progresso seja um inteiro entre 0 e 100
        progresso = int((xp_no_nivel / range_nivel) * 100) if range_nivel > 0 else 0
        
        # [AURA FIX] Payload formatado exatamente como o Base44 espera
        return jsonify({
            "id": current_user_id,
            "nome": nome_atleta,
            "foto": dados.get("foto_perfil", ""),
            "xp_total": xp_atual,
            "moedas": coins,
            "saldo_cristais": dados.get("saldo_cristais", 0),
            "nivel": nivel_atual,
            "barra_progresso": max(0, min(100, progresso)),
            "xp_falta": max(0, range_nivel - xp_no_nivel),
            "objetivo": dados.get("objetivo", "Performance")
        })
    except Exception as e:
        logger.error(f"Erro status para o user {current_user_id}: {e}")
        return jsonify({"erro": "Falha ao sincronizar perfil"}), 500

# ===================================================
# ⚔️ CLÃS E RANKING (SOCIAL)
# ===================================================

@api_bp.route('/cla/ranking', methods=['GET'])
def get_ranking_cla():
    try:
        ranking = obter_ranking_global(limite=50) 
        return jsonify({"ranking": ranking})
    except Exception as e:
        logger.error(f"Erro ao buscar ranking: {e}")
        return jsonify({"ranking": []})

@api_bp.route('/cla/chat', methods=['GET', 'POST'])
@token_required
def chat_cla(current_user_id):
    """Gerencia as mensagens do chat global do clã."""
    # [AURA FIX] Comparação explícita com None para evitar erro de truth value
    if mongo_db is None:
        return jsonify({"erro": "Chat temporariamente offline"}), 503

    if request.method == 'GET':
        try:
            cursor = mongo_db["chat_messages"].find().sort("timestamp", -1).limit(50)
            msgs = [{"user": d.get("nome"), "msg": d.get("content"), "time": d.get("timestamp")} for d in cursor]
            return jsonify(msgs[::-1])
        except Exception as e:
            return jsonify([])

    if request.method == 'POST':
        try:
            dados = request.get_json(force=True)
            mongo_db["chat_messages"].insert_one({
                "user_id": current_user_id,
                "nome": dados.get("nome", "Atleta"),
                "content": dados.get("mensagem"),
                "timestamp": datetime.now().isoformat()
            })
            return jsonify({"sucesso": True})
        except Exception as e:
            return jsonify({"erro": "Falha ao enviar mensagem"}), 500

# ===================================================
# 🧠 COMANDO DO MESTRE (IA)
# ===================================================

@api_bp.route('/comando', methods=['POST'])
@token_required
def comando(current_user_id):
    try:
        dados = request.get_json(force=True) 
        msg = dados.get('comando', '').strip()
        if not msg: return jsonify({"resposta": "O Mestre aguarda suas palavras..."})
        
        # [AURA FIX] A lógica processar_comando agora lê os campos da raiz corretamente
        resposta = processar_comando(current_user_id, msg)
        return jsonify({"resposta": resposta})
    except Exception as e:
        logger.error(f"Erro no comando IA para {current_user_id}: {e}")
        return jsonify({"resposta": "⚠️ O Mestre está meditando em silêncio. Tente novamente."})

# ===================================================
# 🎮 MISSÕES E GAMIFICAÇÃO
# ===================================================

@api_bp.route('/missoes', methods=['GET'])
@token_required
def listar_missoes(current_user_id):
    # [AURA FIX] Retorna o array de missões diárias renovado ou cacheado do dia
    return jsonify({"missoes": gerar_missoes_diarias(current_user_id)})

@api_bp.route('/concluir_missao', methods=['POST'])
@token_required
def concluir_missao(current_user_id):
    try:
        dados = request.get_json(force=True)
        missao_id = dados.get("id")
        
        memoria = carregar_memoria(current_user_id)
        gamificacao = memoria.get("gamificacao", {})
        missoes = gamificacao.get("missoes_ativas", [])
        
        for m in missoes:
            if m["id"] == missao_id and not m.get("concluida"):
                m["concluida"] = True
                salvar_memoria(current_user_id, memoria)
                
                # Aplica XP e verifica Level Up na raiz do documento
                resultado = aplicar_xp(current_user_id, m.get("xp", 0))
                return jsonify({
                    "sucesso": True, 
                    "novo_nivel": resultado["novo_nivel"],
                    "novo_xp": resultado["novo_xp"]
                })
                
        return jsonify({"erro": "Missão inválida ou já concluída"}), 400
    except Exception as e:
        return jsonify({"erro": "Falha ao concluir missão"}), 500

# ===================================================
# ⚕️ BIOHACKING E SINCRONIZAÇÃO
# ===================================================

@api_bp.route('/sincronizar_dinamico', methods=['POST'])
@token_required
def sincronizar_dinamico(current_user_id):
    # Lazy import para evitar dependência circular
    from data_sensores import obter_dados_fisiologicos
    
    # Busca dados no Strava/Sensores e atualiza 'status_atual'
    novos_dados = obter_dados_fisiologicos(current_user_id)
    # Recalcula a Homeostase (Prontidão)
    calcular_e_atualizar_equilibrio(current_user_id)
    
    return jsonify({"status": "Sincronizado", "dados": novos_dados})

@api_bp.route('/feedback', methods=['GET'])
@token_required
def feedback(current_user_id):
    # Retorna o texto curto para a Home do Base44
    return jsonify({"texto": gerar_feedback_emocional(current_user_id)})

# ===================================================
# 💳 PAGAMENTOS (ASAAS)
# ===================================================

@api_bp.route('/pagamento/criar', methods=['POST'])
@token_required
def criar_pagamento(current_user_id):
    dados = request.get_json(force=True)
    dados['user_id'] = current_user_id
    # A lógica logic_asaas agora sincroniza corretamente com a coleção 'pedidos'
    return jsonify(criar_cobranca(dados))