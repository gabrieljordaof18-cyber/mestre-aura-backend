import logging
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
from logic_pedidos import processar_venda_confirmada # <--- NOVA IMPORTAÇÃO LOGÍSTICA

# Configuração de Logs
logger = logging.getLogger("AURA_API")

# Definição do Blueprint
api_bp = Blueprint('api_bp', __name__, url_prefix='/api')

# ===================================================
# 📊 USUÁRIO E STATUS
# ===================================================

@api_bp.route('/usuario/status', methods=['GET'])
def get_status_jogador():
    """Retorna XP, Nível e Aura Coins para o Frontend."""
    try:
        dados = ler_dados_jogador()
        
        if not dados:
            return jsonify({
                "nome": "Iniciado", "xp_total": 0, "aura_coins": 0,
                "nivel": 1, "xp_necessario_proximo": 1000, "barra_progresso": 0,
                "foto": ""
            })

        xp_atual = dados.get("xp_total", 0)
        
        XP_POR_NIVEL = 1000
        nivel_atual = int(xp_atual / XP_POR_NIVEL) + 1
        xp_restante = XP_POR_NIVEL - (xp_atual % XP_POR_NIVEL)
        progresso = int(((xp_atual % XP_POR_NIVEL) / XP_POR_NIVEL) * 100)

        return jsonify({
            "nome": dados.get("nome", "Atleta"),
            "foto": dados.get("foto_perfil", ""),
            "xp_total": xp_atual,
            "aura_coins": dados.get("aura_coins", 0),
            "nivel": nivel_atual,
            "xp_necessario_proximo": xp_restante,
            "barra_progresso": progresso,
            "strava_conectado": True
        })
    except Exception as e:
        logger.error(f"Erro ao obter status: {e}")
        return jsonify({"erro": "Falha interna"}), 500

# ===================================================
# 🏆 COMUNIDADE E RANKING
# ===================================================

@api_bp.route('/cla/ranking', methods=['GET'])
def get_ranking_cla():
    """Retorna Top 20 Jogadores."""
    try:
        ranking = obter_ranking_global(limite=20) 
        return jsonify({"ranking": ranking})
    except Exception as e:
        logger.error(f"Erro no ranking: {e}")
        return jsonify({"ranking": []})

# ===================================================
# 🕵️ SEGURANÇA (ANTI-FRAUDE)
# ===================================================

@api_bp.route('/antifraude/validar', methods=['POST'])
def validar_atividade():
    try:
        dados_input = request.get_json(force=True)
        data_declarada = dados_input.get('data') 
        
        usuario = ler_dados_jogador()
        if not usuario:
            return jsonify({"aprovado": False, "motivo": "Usuário não encontrado."}), 404

        historico = usuario.get('historico_atividades', [])
        encontrou = False
        
        for atividade in historico:
            data_real = atividade.get('data')
            if isinstance(data_real, datetime):
                data_real = data_real.strftime('%Y-%m-%d')
            elif isinstance(data_real, str):
                data_real = data_real[:10]
            
            if data_real == data_declarada:
                encontrou = True
                break
        
        if encontrou:
            return jsonify({"aprovado": True, "msg": "Validação Strava confirmada."})
        else:
            return jsonify({
                "aprovado": False, 
                "motivo": "Nenhuma atividade encontrada no Strava nesta data."
            })
            
    except Exception as e:
        logger.error(f"Erro antifraude: {e}")
        return jsonify({"aprovado": False, "motivo": "Erro de validação."}), 500

# ===================================================
# 🤖 CHATBOT IA
# ===================================================

@api_bp.route('/comando', methods=['POST'])
def comando():
    try:
        dados = request.get_json(force=True) 
        mensagem = dados.get('comando', '').strip()
        
        if not mensagem:
            return jsonify({"resposta": "..."})
            
        resposta = processar_comando(mensagem)
        return jsonify({"resposta": resposta})
    except Exception as e:
        logger.error(f"Erro no chat: {e}")
        return jsonify({"resposta": "⚠️ Erro de comunicação com o Mestre."})

# ===================================================
# 🎯 GAMIFICAÇÃO & MISSÕES
# ===================================================

@api_bp.route('/missoes', methods=['GET'])
def listar_missoes():
    """
    Retorna as missões do dia.
    Se detectar que mudou o dia, gera novas automaticamente.
    """
    memoria = carregar_memoria()
    gamificacao = memoria.get("gamificacao", {})
    
    # Data de hoje (YYYY-MM-DD)
    hoje_str = datetime.now().strftime("%Y-%m-%d")
    ultima_atualizacao = gamificacao.get("data_ultima_atualizacao", "")

    # Se a data salva for diferente de hoje, gera novas missões
    if ultima_atualizacao != hoje_str:
        print(f"🔄 Novo dia detectado ({hoje_str}). Gerando novas missões...")
        novas_missoes = gerar_missoes_diarias()
        
        # Atualiza a memória com as novas missões e a nova data
        memoria["gamificacao"]["missoes_ativas"] = novas_missoes
        memoria["gamificacao"]["data_ultima_atualizacao"] = hoje_str
        salvar_memoria(memoria)
        
        return jsonify({"missoes": novas_missoes})
    
    # Se for o mesmo dia, retorna as que já existem
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
            return jsonify({
                "sucesso": True, 
                "msg": f"Concluída! +{xp} XP", 
                "novo_nivel": resultado["novo_nivel"]
            })
        
        return jsonify({"erro": "Missão não encontrada"}), 404
    except Exception as e:
        logger.error(f"Erro concluir missão: {e}")
        return jsonify({"erro": "Falha interna"}), 500

# ===================================================
# 🧬 FISIOLOGIA & EQUILÍBRIO
# ===================================================

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

# ===================================================
# 📂 GESTÃO DE PLANOS (DIETA & TREINO)
# ===================================================

@api_bp.route('/usuario/planos', methods=['GET'])
def get_plano_usuario():
    try:
        tipo = request.args.get('tipo') 
        if tipo not in ['dieta', 'treino']:
            return jsonify({"erro": "Tipo inválido. Use 'dieta' ou 'treino'."}), 400
        dados_plano = ler_plano_mestre(tipo)
        return jsonify({
            "tipo": tipo,
            "dados": dados_plano
        })
    except Exception as e:
        logger.error(f"Erro ao buscar plano: {e}")
        return jsonify({"erro": "Falha ao carregar plano."}), 500

# ===================================================
# 💳 PAGAMENTOS & LOGÍSTICA (ASAAS)
# ===================================================

@api_bp.route('/pagamento/criar', methods=['POST'])
def criar_pagamento_asaas():
    """
    Simula a criação de um pagamento no Asaas.
    Retorna um QR Code de teste para o frontend.
    """
    try:
        dados = request.get_json(force=True)
        valor = dados.get('valor')
        metodo = dados.get('metodo') # 'pix' ou 'card'
        ref_pedido = dados.get('external_reference')
        
        # Simulação de resposta do Asaas (Sandbox)
        # Em produção, aqui chamaríamos requests.post('https://api.asaas.com/v3/payments'...)
        
        logger.info(f"💰 Criando pagamento simulado para Pedido #{ref_pedido} no valor de R${valor}")

        if metodo == 'pix':
            return jsonify({
                "tipo": "pix",
                "sucesso": True,
                "payload_pix": "00020126330014BR.GOV.BCB.PIX011141993285806520400005303986540550.005802BR5925Aura Performance Ltda6009Sao Paulo62070503***6304E2CA",
                # Imagem genérica de QR Code para teste visual
                "imagem_qr": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAAANSURBVBhXY2BgYAAAAAQAAVzN/2kAAAAASUVORK5CYII=" 
            })
        else:
            # Simulação Cartão
            return jsonify({
                "tipo": "cartao",
                "sucesso": True,
                "link_pagamento": "https://www.asaas.com/c/123teste"
            })

    except Exception as e:
        logger.error(f"Erro ao criar pagamento: {e}")
        return jsonify({"erro": "Falha na comunicação com gateway."}), 500

@api_bp.route('/webhook/asaas', methods=['POST'])
def webhook_asaas():
    """
    Recebe notificação do Asaas (ou simulação) de que o Pix foi pago.
    Dispara a logística de separação de pedidos.
    """
    try:
        dados = request.get_json(force=True)
        
        # O Asaas envia o evento "PAYMENT_RECEIVED" ou "PAYMENT_CONFIRMED"
        evento = dados.get('event')
        pagamento = dados.get('payment', {})
        
        # Pega o ID do nosso pedido que estava salvo no campo 'externalReference' do Asaas
        pedido_id_aura = pagamento.get('externalReference')
        
        if evento in ['PAYMENT_RECEIVED', 'PAYMENT_CONFIRMED']:
            if pedido_id_aura:
                print(f"🔔 WEBHOOK RECEBIDO: Pagamento confirmado para Pedido {pedido_id_aura}")
                
                # CHAMA O CÉREBRO DA LOGÍSTICA
                sucesso = processar_venda_confirmada(pedido_id_aura)
                
                if sucesso:
                    return jsonify({"status": "SUCCESS", "msg": "Logística iniciada."})
                else:
                    return jsonify({"status": "ERROR", "msg": "Erro interno na logística."}), 500
            else:
                logger.warning("Webhook recebido sem externalReference.")
                
        return jsonify({"status": "RECEIVED"}) # Sempre retorna 200 pro Asaas não reenviar

    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        return jsonify({"erro": "Falha interna"}), 500