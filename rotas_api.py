import logging
import os
import requests 
from datetime import datetime
from typing import Dict, Any
from flask import request, jsonify, Blueprint

# --- IMPORTAÇÕES MANTIDAS (Gamificação e Usuário) ---
from data_user import carregar_memoria, salvar_memoria, obter_status_fisiologico
from data_global import carregar_memoria_global
from data_manager import ler_dados_jogador, obter_ranking_global, ler_plano_mestre 
from logic_gamificacao import gerar_missoes_diarias, aplicar_xp
from logic_equilibrio import calcular_e_atualizar_equilibrio
from logic import processar_comando 
from logic_feedback import gerar_feedback_emocional

# Configuração de Logs
logger = logging.getLogger("AURA_API")

api_bp = Blueprint('api_bp', __name__, url_prefix='/api')

# ===================================================
# 🔑 CONFIGURAÇÕES
# ===================================================

ASAAS_API_URL = "https://api.asaas.com/v3"
ASAAS_ACCESS_TOKEN = os.environ.get("ASAAS_API_KEY") 

# ===================================================
# 🌉 ROTA PROXY DE DADOS (FRONTEND -> BASE44)
# ===================================================

@api_bp.route('/data/<entity>', methods=['POST'])
def proxy_save_data(entity):
    """
    Rota de pass-through. 
    Idealmente o Frontend usa o SDK do Base44, mas mantemos isso 
    para compatibilidade com o Checkout.js atual.
    """
    try:
        # Gera um ID de referência para o fluxo não quebrar
        fake_id = f"rec_{int(datetime.now().timestamp())}"
        logger.info(f"✅ [PROXY] ID de fluxo gerado: {fake_id}")
        
        # Retorna sucesso simulado para o Checkout prosseguir para o pagamento
        return jsonify({"id": fake_id, "_id": fake_id, "status": "proxy_ok"}), 200

    except Exception as e:
        logger.error(f"❌ [PROXY] Erro: {e}")
        return jsonify({"erro": "Falha no proxy"}), 500

# ===================================================
# 💳 PAGAMENTOS (CRIAÇÃO APENAS)
# ===================================================

@api_bp.route('/pagamento/criar', methods=['POST'])
def criar_pagamento_asaas():
    """
    Gera o PIX/Boleto no Asaas.
    O vínculo e atualização de status agora são feitos via Webhook direto no Base44.
    """
    try:
        dados = request.get_json(force=True)
        valor = dados.get('valor')
        metodo = dados.get('metodo') # 'pix' ou 'card'
        ref_pedido = dados.get('external_reference') # ID do pedido
        usuario = dados.get('usuario', {})
        
        logger.info(f"💳 [ASAAS] Criando cobrança | Pedido: {ref_pedido} | R$ {valor}")

        if not ASAAS_ACCESS_TOKEN:
            return jsonify({"erro": "Erro: Chave ASAAS_API_KEY não configurada."}), 500

        headers = {
            "Content-Type": "application/json",
            "access_token": ASAAS_ACCESS_TOKEN
        }

        # 1. CRIAR/BUSCAR CLIENTE
        payload_cliente = {
            "name": usuario.get('nome', 'Cliente Aura'),
            "email": usuario.get('email', 'email@exemplo.com'),
            "cpfCnpj": usuario.get('cpf', ''),
            "notificationDisabled": False
        }
        
        resp_cliente = requests.post(f"{ASAAS_API_URL}/customers", json=payload_cliente, headers=headers)
        
        customer_id = None
        if resp_cliente.status_code == 200:
            customer_id = resp_cliente.json().get('id')
        elif "already exists" in resp_cliente.text:
            # Busca cliente por email se já existir
            email = usuario.get('email')
            resp_busca = requests.get(f"{ASAAS_API_URL}/customers?email={email}", headers=headers)
            if resp_busca.status_code == 200 and resp_busca.json().get('data'):
                customer_id = resp_busca.json()['data'][0]['id']
        
        if not customer_id:
            logger.error(f"❌ Erro Cliente Asaas: {resp_cliente.text}")
            return jsonify({"erro": "Falha ao identificar cliente."}), 500

        # 2. CRIAR A COBRANÇA
        payload_cobranca = {
            "customer": customer_id,
            "billingType": "PIX" if metodo == 'pix' else "CREDIT_CARD",
            "value": float(valor),
            "dueDate": datetime.now().strftime("%Y-%m-%d"),
            "description": dados.get('descricao', 'Pedido Aura'),
            "externalReference": ref_pedido, # O Webhook do Base44 usará isso para achar o pedido
        }

        resp_cobranca = requests.post(f"{ASAAS_API_URL}/payments", json=payload_cobranca, headers=headers)
        
        if resp_cobranca.status_code != 200:
             logger.error(f"❌ Erro Cobrança Asaas: {resp_cobranca.text}")
             return jsonify({"erro": "Gateway recusou a transação."}), 500

        data_asaas = resp_cobranca.json()
        asaas_id = data_asaas.get('id')

        # 3. RESPOSTA PARA O FRONTEND
        if metodo == 'pix':
            resp_qr = requests.get(f"{ASAAS_API_URL}/payments/{asaas_id}/pixQrCode", headers=headers)
            if resp_qr.status_code == 200:
                data_qr = resp_qr.json()
                return jsonify({
                    "tipo": "pix",
                    "sucesso": True,
                    "payload_pix": data_qr.get('payload'),
                    "imagem_qr": data_qr.get('encodedImage') 
                })
        else:
            return jsonify({
                "tipo": "cartao",
                "sucesso": True,
                "link_pagamento": data_asaas.get('invoiceUrl')
            })

    except Exception as e:
        logger.error(f"Erro crítico: {e}")
        return jsonify({"erro": "Falha interna."}), 500


# ===================================================
# ROTAS DO APP (MANTIDAS)
# ===================================================

@api_bp.route('/usuario/status', methods=['GET'])
def get_status_jogador():
    try:
        dados = ler_dados_jogador()
        if not dados: return jsonify({"nome": "Iniciado", "xp_total": 0, "aura_coins": 0, "nivel": 1, "xp_necessario_proximo": 1000, "barra_progresso": 0, "foto": ""})
        xp_atual = dados.get("xp_total", 0)
        XP_POR_NIVEL = 1000
        nivel_atual = int(xp_atual / XP_POR_NIVEL) + 1
        xp_restante = XP_POR_NIVEL - (xp_atual % XP_POR_NIVEL)
        progresso = int(((xp_atual % XP_POR_NIVEL) / XP_POR_NIVEL) * 100)
        return jsonify({"nome": dados.get("nome", "Atleta"), "foto": dados.get("foto_perfil", ""), "xp_total": xp_atual, "aura_coins": dados.get("aura_coins", 0), "nivel": nivel_atual, "xp_necessario_proximo": xp_restante, "barra_progresso": progresso, "strava_conectado": True})
    except Exception as e:
        logger.error(f"Erro ao obter status: {e}")
        return jsonify({"erro": "Falha interna"}), 500

@api_bp.route('/cla/ranking', methods=['GET'])
def get_ranking_cla():
    try:
        ranking = obter_ranking_global(limite=20) 
        return jsonify({"ranking": ranking})
    except Exception as e:
        logger.error(f"Erro no ranking: {e}")
        return jsonify({"ranking": []})

@api_bp.route('/antifraude/validar', methods=['POST'])
def validar_atividade():
    try:
        dados_input = request.get_json(force=True)
        data_declarada = dados_input.get('data') 
        usuario = ler_dados_jogador()
        if not usuario: return jsonify({"aprovado": False, "motivo": "Usuário não encontrado."}), 404
        historico = usuario.get('historico_atividades', [])
        encontrou = False
        for atividade in historico:
            data_real = atividade.get('data')
            if isinstance(data_real, datetime): data_real = data_real.strftime('%Y-%m-%d')
            elif isinstance(data_real, str): data_real = data_real[:10]
            if data_real == data_declarada:
                encontrou = True
                break
        if encontrou: return jsonify({"aprovado": True, "msg": "Validação Strava confirmada."})
        else: return jsonify({"aprovado": False, "motivo": "Nenhuma atividade encontrada no Strava nesta data."})
    except Exception as e:
        logger.error(f"Erro antifraude: {e}")
        return jsonify({"aprovado": False, "motivo": "Erro de validação."}), 500

@api_bp.route('/comando', methods=['POST'])
def comando():
    try:
        dados = request.get_json(force=True) 
        mensagem = dados.get('comando', '').strip()
        if not mensagem: return jsonify({"resposta": "..."})
        resposta = processar_comando(mensagem)
        return jsonify({"resposta": resposta})
    except Exception as e:
        logger.error(f"Erro no chat: {e}")
        return jsonify({"resposta": "⚠️ Erro de comunicação com o Mestre."})

@api_bp.route('/missoes', methods=['GET'])
def listar_missoes():
    memoria = carregar_memoria()
    gamificacao = memoria.get("gamificacao", {})
    hoje_str = datetime.now().strftime("%Y-%m-%d")
    ultima_atualizacao = gamificacao.get("data_ultima_atualizacao", "")
    if ultima_atualizacao != hoje_str:
        # print(f"🔄 Novo dia detectado ({hoje_str}). Gerando novas missões...")
        novas_missoes = gerar_missoes_diarias()
        memoria["gamificacao"]["missoes_ativas"] = novas_missoes
        memoria["gamificacao"]["data_ultima_atualizacao"] = hoje_str
        salvar_memoria(memoria)
        return jsonify({"missoes": novas_missoes})
    return jsonify({"missoes": gamificacao.get("missoes_ativas", [])})

@api_bp.route('/missoes/gerar', methods=['POST'])
def rota_gerar_missoes():
    novas = gerar_missoes_diarias()
    return jsonify({"mensagem": "Novas missões geradas!", "missoes": novas})

@api_bp.route('/concluir_missao', methods=['POST'])
def concluir_missao():
    try:
        dados = request.get_json(force=True)
        missao_id = dados.get("id")
        memoria = carregar_memoria()
        missoes = memoria.get("gamificacao", {}).get("missoes_ativas", [])
        missao_alvo = None
        for m in missoes:
            if m["id"] == missao_id:
                if m["concluida"]: return jsonify({"erro": "Já concluída!"})
                m["concluida"] = True
                missao_alvo = m
                break
        if missao_alvo:
            xp = missao_alvo.get("xp", 0)
            resultado = aplicar_xp(xp)
            salvar_memoria(memoria)
            return jsonify({"sucesso": True, "msg": f"Concluída! +{xp} XP", "novo_nivel": resultado["novo_nivel"]})
        return jsonify({"erro": "Missão não encontrada"}), 404
    except Exception as e:
        logger.error(f"Erro concluir missão: {e}")
        return jsonify({"erro": "Falha interna"}), 500

@api_bp.route('/equilibrio', methods=['GET'])
def obter_equilibrio():
    memoria = carregar_memoria()
    return jsonify(memoria.get("homeostase", {"score": 0, "estado": "Carregando..."}))

@api_bp.route('/status_fisiologico', methods=['GET'])
def status_fisiologico():
    dados = obter_status_fisiologico()
    return jsonify(dados)

@api_bp.route('/feedback', methods=['GET'])
def feedback():
    memoria = carregar_memoria()
    texto = gerar_feedback_emocional(memoria)
    return jsonify({"texto": texto})

@api_bp.route('/sincronizar_dinamico', methods=['POST'])
def sincronizar_dinamico():
    from data_sensores import obter_dados_fisiologicos
    novos_dados = obter_dados_fisiologicos()
    calcular_e_atualizar_equilibrio()
    return jsonify({"dados": novos_dados})

@api_bp.route('/usuario/planos', methods=['GET'])
def get_plano_usuario():
    try:
        tipo = request.args.get('tipo') 
        if tipo not in ['dieta', 'treino']: return jsonify({"erro": "Tipo inválido. Use 'dieta' ou 'treino'."}), 400
        dados_plano = ler_plano_mestre(tipo)
        return jsonify({"tipo": tipo, "dados": dados_plano})
    except Exception as e:
        logger.error(f"Erro ao buscar plano: {e}")
        return jsonify({"erro": "Falha ao carregar plano."}), 500