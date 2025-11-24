from flask import request, jsonify, Blueprint
import random
from datetime import datetime

# ==========================================================
# 🔌 ROTAS DA API (O PAINEL DE CONTROLE)
# ==========================================================

# Importamos as ferramentas antigas (Mantidas para compatibilidade do Chat)
from data_user import carregar_memoria, salvar_memoria, obter_status_fisiologico
from data_sensores import coletar_dados
from data_global import carregar_memoria_global, registrar_interacao_global, obter_afinidade

# Importamos a lógica de gamificação e equilíbrio
from logic_gamificacao import gerar_missoes_diarias, aplicar_xp
from logic_equilibrio import calcular_e_atualizar_equilibrio
from logic import processar_comando 
from logic_feedback import gerar_feedback_emocional

# --- NOVA IMPORTAÇÃO (INTEGRAÇÃO MONGODB/STRAVA) ---
from data_manager import ler_dados_jogador

# Definimos o Blueprint com prefixo '/api'. 
# Assim, todas as rotas abaixo começam com /api (ex: /api/comando)
api_bp = Blueprint('api_bp', __name__, url_prefix='/api')

# ===================================================
# 📊 ROTA DE STATUS DO JOGADOR (XP REAL & NÍVEL) - NOVO!
# ===================================================
@api_bp.route('/usuario/status', methods=['GET'])
def get_status_jogador():
    """
    Rota que o Base44 vai chamar para saber quanto XP o jogador tem.
    Lê direto do MongoDB (via data_manager) e calcula o nível.
    """
    # 1. Busca os dados reais no MongoDB
    dados = ler_dados_jogador()
    
    if not dados:
        # Se não tiver ninguém no banco, retorna dados zerados
        return jsonify({
            "nome": "Iniciado",
            "xp_total": 0,
            "nivel": 1,
            "xp_necessario_proximo": 1000,
            "barra_progresso": 0,
            "foto": ""
        })

    # 2. Extrai o XP Real e Nome
    xp_atual = dados.get("xp_total", 0)
    nome = dados.get("nome", "Atleta")
    foto = dados.get("foto_perfil", "")

    # 3. Matemática do Nível (Regra: 1 Nível a cada 1000 XP)
    XP_POR_NIVEL = 1000
    
    nivel_atual = int(xp_atual / XP_POR_NIVEL) + 1
    xp_restante_para_proximo = XP_POR_NIVEL - (xp_atual % XP_POR_NIVEL)
    
    # Calcula a porcentagem da barra de progresso (0 a 100)
    xp_nesse_nivel = xp_atual % XP_POR_NIVEL
    progresso_percent = int((xp_nesse_nivel / XP_POR_NIVEL) * 100)

    # 4. Retorna o JSON estruturado para o App
    return jsonify({
        "nome": nome,
        "foto": foto,
        "xp_total": xp_atual,
        "nivel": nivel_atual,
        "xp_necessario_proximo": xp_restante_para_proximo,
        "barra_progresso": progresso_percent,
        "strava_conectado": True
    })

# ============================================
# 🤖 CHAT (Mestre da AURA)
# ============================================
@api_bp.route('/comando', methods=['POST'])
def comando():
    dados = request.get_json(force=True) 
    mensagem = dados.get('comando', '').strip()
    if not mensagem:
        return jsonify({"resposta": "..."})
    resposta = processar_comando(mensagem)
    return jsonify({"resposta": resposta})

# ============================================
# 👤 JOGADOR E DADOS (LEGADO/COMPATIBILIDADE)
# ============================================
@api_bp.route('/status_jogador')
def status_jogador():
    memoria = carregar_memoria()
    return jsonify(memoria.get("jogador", {}))

@api_bp.route('/status_fisiologico')
def status_fisiologico():
    dados = obter_status_fisiologico()
    return jsonify(dados)

@api_bp.route('/feedback')
def feedback():
    memoria = carregar_memoria()
    texto = gerar_feedback_emocional(memoria)
    return jsonify({"texto": texto})

# ============================================
# 🎯 GAMIFICAÇÃO 
# ============================================
@api_bp.route('/missoes', methods=['GET'])
def listar_missoes():
    memoria = carregar_memoria()
    missoes = memoria.get("gamificacao", {}).get("missoes_ativas", [])
    return jsonify({"missoes": missoes})

@api_bp.route('/missoes/gerar', methods=['POST'])
def rota_gerar_missoes():
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
        xp_ganho = missao_encontrada.get("xp", 0)
        resultado_xp = aplicar_xp(xp_ganho)
        salvar_memoria(memoria)
        
        return jsonify({
            "sucesso": True, 
            "msg": f"Concluída! +{xp_ganho} XP",
            "novo_nivel": resultado_xp["novo_nivel"]
        })
    
    return jsonify({"erro": "Missão não encontrada"}), 404

# ============================================
# ⚖️ EQUILÍBRIO
# ============================================
@api_bp.route('/equilibrio', methods=['GET'])
def obter_equilibrio():
    memoria = carregar_memoria()
    return jsonify(memoria.get("homeostase", {"score": 0, "estado": "Carregando..."}))

@api_bp.route('/equilibrio/atualizar', methods=['POST'])
def rota_atualizar_equilibrio():
    novo_estado = calcular_e_atualizar_equilibrio()
    return jsonify(novo_estado)

# ============================================
# ⚙️ OUTROS
# ============================================
@api_bp.route('/sincronizar_dinamico', methods=['POST'])
def sincronizar_dinamico():
    from data_sensores import coletar_dados # Importação local para evitar ciclo
    novos_dados = coletar_dados()
    
    memoria = carregar_memoria()
    memoria["dados_fisiologicos"].update(novos_dados)
    salvar_memoria(memoria)
    
    calcular_e_atualizar_equilibrio()
    
    return jsonify({"dados": novos_dados})