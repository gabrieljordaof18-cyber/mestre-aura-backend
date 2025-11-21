from flask import request, jsonify, Blueprint
import random
from datetime import datetime

# ==========================================================
# 🔌 ROTAS DA API (O PAINEL DE CONTROLE) - FASE 2 ADAPTADA
# ==========================================================

# Importamos as NOVAS ferramentas que criamos nas Fases 1 e 2
from data_user import carregar_memoria, salvar_memoria, obter_status_fisiologico
from data_sensores import coletar_dados
from data_global import carregar_memoria_global, registrar_interacao_global, obter_afinidade

# Importamos a NOVA lógica limpa
from logic_gamificacao import gerar_missoes_diarias, aplicar_xp
from logic_equilibrio import calcular_e_atualizar_equilibrio
from logic import processar_comando 
from logic_feedback import gerar_feedback_emocional

api_bp = Blueprint('api_bp', __name__)

# ============================================
# 🤖 CHAT (Mestre da AURA)
# ============================================
@api_bp.route('/comando', methods=['POST'])
def comando():
    dados = request.get_json(force=True) # force=True ajuda se o header vier errado
    mensagem = dados.get('comando', '').strip()
    if not mensagem:
        return jsonify({"resposta": "..."})
    resposta = processar_comando(mensagem)
    return jsonify({"resposta": resposta})

# ============================================
# 👤 JOGADOR E DADOS
# ============================================
@api_bp.route('/status_jogador')
def status_jogador():
    memoria = carregar_memoria()
    return jsonify(memoria.get("jogador", {}))

@api_bp.route('/status_fisiologico')
def status_fisiologico():
    # Tenta pegar dados frescos, se não, pega da memória
    dados = obter_status_fisiologico()
    return jsonify(dados)

@api_bp.route('/feedback')
def feedback():
    memoria = carregar_memoria()
    texto = gerar_feedback_emocional(memoria)
    return jsonify({"texto": texto})

# ============================================
# 🎯 GAMIFICAÇÃO (Adaptado para Fase 2)
# ============================================
@api_bp.route('/missoes', methods=['GET'])
def listar_missoes():
    # Agora lemos da memória local, que foi atualizada pela lógica
    memoria = carregar_memoria()
    missoes = memoria.get("gamificacao", {}).get("missoes_ativas", [])
    return jsonify({"missoes": missoes})

@api_bp.route('/missoes/gerar', methods=['POST'])
def rota_gerar_missoes():
    # Chama a nova função da logic_gamificacao
    novas = gerar_missoes_diarias()
    return jsonify({"mensagem": "Novas missões geradas!", "missoes": novas})

@api_bp.route('/concluir_missao', methods=['POST'])
def concluir_missao():
    dados = request.get_json(force=True)
    missao_id = dados.get("id")
    
    memoria = carregar_memoria()
    missoes = memoria.get("gamificacao", {}).get("missoes_ativas", [])
    
    missao_encontrada = None
    for m in missoes:
        if m["id"] == missao_id:
            if m["concluida"]: return jsonify({"erro": "Já concluída!"})
            m["concluida"] = True
            missao_encontrada = m
            break
    
    if missao_encontrada:
        # Aplica recompensa usando a nova lógica
        xp_ganho = missao_encontrada.get("xp", 0)
        resultado_xp = aplicar_xp(xp_ganho)
        
        # Salva o estado da missão concluída
        salvar_memoria(memoria)
        
        return jsonify({
            "sucesso": True, 
            "msg": f"Concluída! +{xp_ganho} XP",
            "novo_nivel": resultado_xp["novo_nivel"]
        })
    
    return jsonify({"erro": "Missão não encontrada"}), 404

@api_bp.route('/xp_status', methods=['GET'])
def xp_status():
    memoria = carregar_memoria()
    jog = memoria.get("jogador", {})
    # Recalcula quanto falta para o próximo nível (regra simples: 1000 * nivel)
    nivel = jog.get("nivel", 1)
    prox = 1000 * nivel
    return jsonify({
        "xp_total": jog.get("experiencia", 0),
        "nivel": nivel,
        "xp_por_nivel": prox
    })

# ============================================
# ⚖️ EQUILÍBRIO (Adaptado para Fase 2)
# ============================================
@api_bp.route('/equilibrio', methods=['GET'])
def obter_equilibrio():
    memoria = carregar_memoria()
    # Se não existir, retorna um placeholder
    return jsonify(memoria.get("homeostase", {"score": 0, "estado": "Carregando..."}))

@api_bp.route('/equilibrio/atualizar', methods=['POST'])
def rota_atualizar_equilibrio():
    # Chama a nova lógica centralizada
    novo_estado = calcular_e_atualizar_equilibrio()
    return jsonify(novo_estado)

# ============================================
# ⚙️ OUTROS (Energia, Sincronização)
# ============================================
@api_bp.route('/sincronizar_dinamico', methods=['POST'])
def sincronizar_dinamico():
    # Coleta dados novos (sensores limpos)
    from sensores import coletar_dados
    novos_dados = coletar_dados()
    
    # Atualiza memória via data_user
    memoria = carregar_memoria()
    memoria["dados_fisiologicos"].update(novos_dados)
    salvar_memoria(memoria)
    
    # Recalcula o equilíbrio com os dados novos
    calcular_e_atualizar_equilibrio()
    
    return jsonify({"dados": novos_dados})