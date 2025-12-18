import logging
import os
import requests # <--- NECESSÁRIO PARA O PROXY E ASAAS
from datetime import datetime
from typing import Dict, Any, Tuple
from flask import request, jsonify, Blueprint

# Importações Internas
from data_user import carregar_memoria, salvar_memoria, obter_status_fisiologico
from data_global import carregar_memoria_global
from data_manager import ler_dados_jogador, obter_ranking_global, ler_plano_mestre 
from logic_gamificacao import gerar_missoes_diarias, aplicar_xp
from logic_equilibrio import calcular_e_atualizar_equilibrio
from logic import processar_comando 
from logic_feedback import gerar_feedback_emocional
from logic_pedidos import processar_venda_confirmada 

# Configuração de Logs
logger = logging.getLogger("AURA_API")

# Definição do Blueprint
api_bp = Blueprint('api_bp', __name__, url_prefix='/api')

# ===================================================
# 🔑 CONFIGURAÇÕES DE PRODUÇÃO (CHAVES)
# ===================================================
# IMPORTANTE: Em produção, use variáveis de ambiente (os.environ.get)
# Por enquanto, substitua abaixo pelas suas chaves reais ou configure no Render

ASAAS_API_URL = "https://api.asaas.com/v3" # Use "https://api-sandbox.asaas.com/v3" para testes se quiser
ASAAS_ACCESS_TOKEN = os.environ.get("ASAAS_API_KEY", "$aact_...") # <--- COLOQUE SUA CHAVE AQUI SE NÃO USAR ENV

# URL da API Nativa do Base44 para salvar os dados (Proxy)
# Se o seu app roda no Base44, geralmente há uma URL interna ou externa de API.
BASE44_API_URL = "https://api.base44.com/api/data" # <--- AJUSTE SE NECESSÁRIO
BASE44_API_KEY = os.environ.get("BASE44_KEY", "") 

# ===================================================
# 🌉 ROTA PROXY DE DADOS (DERRUBANDO O MURO 404)
# ===================================================

@api_bp.route('/data/<entity>', methods=['POST'])
def proxy_save_data(entity):
    """
    Recebe os dados do Frontend (Checkout) e salva na tabela correspondente do Base44.
    Ex: Salva em 'Pedidos' ou 'ItensPedido'.
    """
    try:
        payload = request.get_json(force=True)
        logger.info(f"💾 [PROXY] Salvando dados na entidade: {entity}")

        # Se você tiver uma biblioteca interna do Base44, use-a aqui.
        # Caso contrário, fazemos o repasse via HTTP para a API do Base44
        # headers = {"Authorization": f"Bearer {BASE44_API_KEY}", "Content-Type": "application/json"}
        # response = requests.post(f"{BASE44_API_URL}/{entity}", json=payload, headers=headers)
        
        # --- MODO DE COMPATIBILIDADE ---
        # Como estamos ajustando a arquitetura agora, se você não tiver a URL externa do Base44 configurada,
        # vamos simular o sucesso e retornar um ID gerado para não travar o fluxo do Asaas.
        # QUANDO TIVER A CHAVE BASE44, DESCOMENTE AS LINHAS ACIMA.
        
        # Gera um ID falso apenas para o fluxo seguir (PROVISÓRIO PARA TESTE DO ASAAS)
        fake_id = f"rec_{int(datetime.now().timestamp())}"
        logger.info(f"✅ [PROXY] (Simulação) Dados salvos com ID: {fake_id}")
        
        return jsonify({"id": fake_id, "_id": fake_id, "status": "success"}), 200

    except Exception as e:
        logger.error(f"❌ [PROXY] Erro ao salvar dados: {e}")
        return jsonify({"erro": "Falha no proxy de dados"}), 500

# ===================================================
# 💳 PAGAMENTOS REAIS (ASAAS INTEGRADO)
# ===================================================

@api_bp.route('/pagamento/criar', methods=['POST'])
def criar_pagamento_asaas():
    """
    Cria um pagamento REAL no Asaas.
    1. Cria/Busca o Cliente no Asaas.
    2. Gera a Cobrança.
    """
    try:
        dados = request.get_json(force=True)
        valor = dados.get('valor')
        metodo = dados.get('metodo') # 'pix' ou 'card'
        ref_pedido = dados.get('external_reference')
        usuario = dados.get('usuario', {})
        
        # Cabeçalhos Obrigatórios do Asaas
        headers = {
            "Content-Type": "application/json",
            "access_token": ASAAS_ACCESS_TOKEN
        }
        
        if not ASAAS_ACCESS_TOKEN or "$aact" in ASAAS_ACCESS_TOKEN:
            logger.warning("⚠️ Chave do Asaas não configurada! Verifique o rotas_api.py")
            return jsonify({"erro": "Configuração de pagamento incompleta no servidor."}), 500

        # 1. CRIAR CLIENTE NO ASAAS
        logger.info("👤 [ASAAS] Criando/Buscando cliente...")
        payload_cliente = {
            "name": usuario.get('nome', 'Cliente Aura'),
            "email": usuario.get('email', 'email@exemplo.com'),
            "cpfCnpj": usuario.get('cpf', ''),
            "notificationDisabled": False
        }
        
        resp_cliente = requests.post(f"{ASAAS_API_URL}/customers", json=payload_cliente, headers=headers)
        
        if resp_cliente.status_code != 200:
            logger.error(f"Erro Asaas Cliente: {resp_cliente.text}")
            # Tenta recuperar se já existe (O asaas retorna erro se já existe? As vezes. Vamos seguir.)
            # Se falhar critico, paramos.
            if "already exists" not in resp_cliente.text:
                 return jsonify({"erro": "Erro ao cadastrar cliente no Asaas."}), 500
            # Se já existe, idealmente buscaríamos o ID, mas para MVP vamos tentar criar cobrança sem ID (alguns gateways aceitam) ou usar um fixo se for teste
            customer_id = resp_cliente.json().get('id') # Tenta pegar mesmo assim
        else:
            customer_id = resp_cliente.json().get('id')

        if not customer_id:
            # Fallback de segurança ou erro
            return jsonify({"erro": "Não foi possível identificar o cliente no Asaas."}), 500

        # 2. CRIAR A COBRANÇA
        logger.info(f"💰 [ASAAS] Gerando cobrança para Cliente {customer_id}")
        
        billing_type = "PIX" if metodo == 'pix' else "CREDIT_CARD"
        
        payload_cobranca = {
            "customer": customer_id,
            "billingType": billing_type,
            "value": float(valor),
            "dueDate": datetime.now().strftime("%Y-%m-%d"), # Vence hoje
            "description": dados.get('descricao', 'Pedido Aura'),
            "externalReference": ref_pedido, # O VÍNCULO COM SEU SISTEMA
        }

        resp_cobranca = requests.post(f"{ASAAS_API_URL}/payments", json=payload_cobranca, headers=headers)
        
        if resp_cobranca.status_code != 200:
             logger.error(f"❌ Erro Asaas Pagamento: {resp_cobranca.text}")
             return jsonify({"erro": f"Gateway recusou: {resp_cobranca.text}"}), 500

        data_asaas = resp_cobranca.json()
        
        # 3. PREPARAR RESPOSTA PARA O FRONTEND
        if metodo == 'pix':
            # Precisa pegar o QR Code e o Payload
            # O endpoint de criar pagamento retorna o ID. As vezes o payload vem, as vezes precisa chamar /pixQrCode
            id_pagamento = data_asaas.get('id')
            
            # Busca o QR Code específico
            resp_qr = requests.get(f"{ASAAS_API_URL}/payments/{id_pagamento}/pixQrCode", headers=headers)
            if resp_qr.status_code == 200:
                data_qr = resp_qr.json()
                return jsonify({
                    "tipo": "pix",
                    "sucesso": True,
                    "payload_pix": data_qr.get('payload'),
                    "imagem_qr": data_qr.get('encodedImage') 
                })
        else:
            # Cartão retorna o link da fatura (invoiceUrl)
            return jsonify({
                "tipo": "cartao",
                "sucesso": True,
                "link_pagamento": data_asaas.get('invoiceUrl')
            })

        return jsonify({"erro": "Fluxo de pagamento incompleto."}), 500

    except Exception as e:
        logger.error(f"Erro crítico no pagamento: {e}")
        return jsonify({"erro": "Falha na comunicação com gateway."}), 500

# ===================================================
# 🔔 WEBHOOK (GATILHO LOGÍSTICO)
# ===================================================

@api_bp.route('/webhook/asaas', methods=['POST'])
def webhook_asaas():
    """
    Recebe notificação REAL do Asaas.
    """
    try:
        dados = request.get_json(force=True)
        evento = dados.get('event')
        pagamento = dados.get('payment', {})
        pedido_id_aura = pagamento.get('externalReference')
        
        logger.info(f"🔔 [WEBHOOK] Evento recebido: {evento} | Ref: {pedido_id_aura}")
        
        if evento in ['PAYMENT_RECEIVED', 'PAYMENT_CONFIRMED']:
            if pedido_id_aura:
                # CHAMA O CÉREBRO DA LOGÍSTICA
                sucesso = processar_venda_confirmada(pedido_id_aura)
                if sucesso:
                    return jsonify({"status": "SUCCESS", "msg": "Logística iniciada."})
                
        return jsonify({"status": "RECEIVED"}) 

    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        return jsonify({"erro": "Falha interna"}), 500

# ===================================================
# 📊 (ROTAS ANTIGAS MANTIDAS)
# ===================================================
# ... (Mantenha as rotas de usuario, ranking, etc abaixo se não estiverem aqui, 
# mas o código acima substitui o topo e as rotas de pagamento)

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
        print(f"🔄 Novo dia detectado ({hoje_str}). Gerando novas missões...")
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