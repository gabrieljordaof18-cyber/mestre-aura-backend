import logging
import os
import requests
import jwt
from functools import wraps
from datetime import datetime
from typing import Dict, Any
from flask import request, jsonify, Blueprint
from bson.objectid import ObjectId # [AURA FIX] Importação necessária para busca por _id

# --- IMPORTAÇÕES DA NOVA ARQUITETURA ---
from data_user import carregar_memoria, salvar_memoria
from data_manager import obter_ranking_global, ler_plano, mongo_db
from logic_gamificacao import gerar_missoes_diarias, aplicar_xp
from logic_equilibrio import calcular_e_atualizar_equilibrio
from logic import processar_comando 
from logic_feedback import gerar_feedback_emocional
from logic_asaas import criar_cobranca

# [AURA LOGISTICS] Importação do novo serviço de frete
from logic_frete import calcular_cotacao_frete

# Configuração de Logs
logger = logging.getLogger("AURA_API_ROTAS")

# [AURA FIX] Definimos o prefixo oficial aqui. No app.py você registrará apenas app.register_blueprint(api_bp)
# Isso resolve o erro 404 de rotas não encontradas no Render.
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
            
        # [AURA FIX] Inicialização correta das variáveis conforme o schema 3.0
        xp_total = int(dados.get("xp_total", 0))
        nivel_atual = int(dados.get("nivel", 1))
        nome_atleta = dados.get("nome", "Atleta Aura")
        cristais = int(dados.get("saldo_cristais", 0))
        
        # Lógica de Barra de Progresso
        XP_BASE = 1000
        xp_prox = XP_BASE * nivel_atual
        xp_anterior = XP_BASE * (nivel_atual - 1)
        range_nivel = xp_prox - xp_anterior
        xp_no_nivel = xp_total - xp_anterior
        
        progresso = int((xp_no_nivel / range_nivel) * 100) if range_nivel > 0 else 0
        
        return jsonify({
            "id": current_user_id,
            "nome": nome_atleta,
            "foto": dados.get("foto_perfil", ""),
            "xp_total": xp_total,
            "saldo_cristais": cristais,
            "nivel": nivel_atual,
            "barra_progresso": max(0, min(100, progresso)),
            "xp_falta": max(0, range_nivel - xp_no_nivel),
            "objetivo": dados.get("objetivo", "Performance")
        })
    except Exception as e:
        logger.error(f"Erro status para o user {current_user_id}: {e}")
        return jsonify({"erro": "Falha ao sincronizar perfil"}), 500

# ===================================================
# 🍎 CONSULTA DE PLANOS (ROBUSTEZ HÍBRIDA)
# ===================================================

@api_bp.route('/usuario/plano/treino', methods=['GET'])
@token_required
def get_plano_treino(current_user_id):
    """Retorna o último treino híbrido gerado pela IA."""
    try:
        plano = ler_plano(current_user_id, "treino")
        if not plano:
            return jsonify({"mensagem": "Nenhum treino ativo. Peça ao Mestre para montar um!"}), 200
        return jsonify(plano)
    except Exception as e:
        logger.error(f"Erro ao ler treino: {e}")
        return jsonify({"erro": "Erro ao carregar treino"}), 500

@api_bp.route('/usuario/plano/dieta', methods=['GET'])
@token_required
def get_plano_dieta(current_user_id):
    """Retorna a última dieta estruturada gerada pela IA."""
    try:
        plano = ler_plano(current_user_id, "dieta")
        if not plano:
            return jsonify({"mensagem": "Nenhuma dieta ativa. Peça ao Mestre para montar uma!"}), 200
        return jsonify(plano)
    except Exception as e:
        logger.error(f"Erro ao ler dieta: {e}")
        return jsonify({"erro": "Erro ao carregar dieta"}), 500

@api_bp.route('/usuario/atualizar_biometria', methods=['POST'])
@token_required
def atualizar_biometria(current_user_id):
    """Atualiza dados físicos para que a IA gere treinos com volume correto."""
    try:
        dados = request.get_json(force=True)
        sucesso = salvar_memoria(current_user_id, {
            "peso_kg": float(dados.get("peso", 70)),
            "altura_cm": float(dados.get("altura", 170)),
            "idade": int(dados.get("idade", 25)),
            "objetivo": dados.get("objetivo", "Performance")
        })
        return jsonify({"sucesso": sucesso})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

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

# ===================================================
# 🧠 COMANDO DO MESTRE (IA HÍBRIDA)
# ===================================================

@api_bp.route('/comando', methods=['POST'])
@token_required
def comando(current_user_id):
    try:
        dados = request.get_json(force=True) 
        msg = dados.get('comando', '').strip()
        if not msg: return jsonify({"resposta": "O Mestre aguarda suas palavras..."})
        
        # O processar_comando no logic.py agora lida com os 10 exercícios e híbridos
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
                
                resultado = aplicar_xp(current_user_id, m.get("xp", 0))
                return jsonify({
                    "sucesso": True, 
                    "novo_nivel": resultado["novo_nivel"],
                    "novo_xp": resultado["novo_xp"],
                    "cristais_ganhos": resultado.get("cristais_ganhos", 0)
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
    from data_sensores import obter_dados_fisiologicos
    novos_dados = obter_dados_fisiologicos(current_user_id)
    calcular_e_atualizar_equilibrio(current_user_id)
    return jsonify({"status": "Sincronizado", "dados": novos_dados})

@api_bp.route('/feedback', methods=['GET'])
@token_required
def feedback(current_user_id):
    return jsonify({"texto": gerar_feedback_emocional(current_user_id)})

# ===================================================
# 💳 PAGAMENTOS E LOGÍSTICA
# ===================================================

@api_bp.route('/pagamento/criar', methods=['POST'])
@token_required
def criar_pagamento(current_user_id):
    dados = request.get_json(force=True)
    dados['user_id'] = current_user_id
    # A lógica de criar_cobranca agora deve ser capaz de lidar com frete se enviado no payload
    return jsonify(criar_cobranca(dados))

@api_bp.route('/frete/cotar', methods=['POST'])
@token_required
def rota_cotar_frete(current_user_id):
    """
    Endpoint para cotação de frete no Melhor Envio.
    Espera: { "cep": "00000000", "itens": [{ "id": "uuid", "quantidade": 1 }] }
    """
    try:
        dados = request.get_json(force=True)
        cep_destino = dados.get("cep")
        itens_checkout = dados.get("itens", [])

        if not cep_destino or not itens_checkout:
            return jsonify({"erro": "CEP de destino ou itens do carrinho ausentes."}), 400

        # Busca detalhes físicos dos produtos no Banco Aura
        produtos_detalhes = []
        for item in itens_checkout:
            # [AURA FIX] Busca na coleção correta 'ProdutosLoja' usando ObjectId
            try:
                prod_id = str(item["id"]).strip()
                prod_doc = mongo_db["ProdutosLoja"].find_one({"_id": ObjectId(prod_id)})
                
                if prod_doc:
                    # Injeta a quantidade vinda do carrinho para o cálculo de peso total
                    prod_doc["quantidade"] = item.get("quantidade", 1)
                    
                    # [AURA FIX - MAPEAMENTO] Traduz os campos do Banco para o que o logic_frete.py espera
                    # Também removemos o ObjectId bruto para evitar erro de serialização.
                    item_traduzido = {
                        "id": str(prod_doc["_id"]),
                        "quantidade": prod_doc["quantidade"],
                        "peso": prod_doc.get("peso_kg", 0.5),
                        "largura": prod_doc.get("largura_cm", 15),
                        "altura": prod_doc.get("altura_cm", 10),
                        "comprimento": prod_doc.get("comprimento_cm", 20),
                        "preco": prod_doc.get("preco_aura", prod_doc.get("preco_final", 0))
                    }
                    produtos_detalhes.append(item_traduzido)
            except Exception as inner_e:
                logger.warning(f"ID de produto inválido ignorado: {item.get('id')}. Erro: {inner_e}")

        if not produtos_detalhes:
            return jsonify({"erro": "Nenhum produto válido encontrado para cotação."}), 404

        # Chama o motor logístico logic_frete com os nomes de campos já corrigidos
        opcoes = calcular_cotacao_frete(cep_destino, produtos_detalhes)
        return jsonify(opcoes)

    except Exception as e:
        logger.error(f"Erro ao cotar frete para {current_user_id}: {e}")
        return jsonify({"erro": "Falha interna no motor de logística."}), 500

@api_bp.route('/webhook/asaas', methods=['POST'])
def webhook_asaas():
    """
    Webhook para receber confirmações de pagamento do Asaas.
    Aqui disparamos o aviso ao lojista e o registro na planilha.
    """
    try:
        dados = request.get_json(force=True)
        evento = dados.get("event")
        payment = dados.get("payment", {})
        
        # Se o pagamento foi confirmado
        if evento in ["PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"]:
            payment_id = payment.get("id")
            # Buscar o pedido no MongoDB para pegar os dados de frete salvos na criação
            pedido = mongo_db["pedidos"].find_one({"asaas_id": payment_id})
            
            if pedido:
                logger.info(f"✅ Pagamento confirmado para pedido {pedido.get('asaas_id')}. Iniciando logística.")
                
        return jsonify({"status": "received"}), 200
    except Exception as e:
        logger.error(f"Erro no webhook Asaas: {e}")
        return jsonify({"erro": "Internal Error"}), 500