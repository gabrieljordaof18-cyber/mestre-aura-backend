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

# --- IMPORTAÇÃO (INTEGRAÇÃO MONGODB/STRAVA/RANKING) ---
from data_manager import ler_dados_jogador, obter_ranking_global

# Definimos o Blueprint com prefixo '/api'
api_bp = Blueprint('api_bp', __name__, url_prefix='/api')

# ===================================================
# 📊 ROTA DE STATUS DO JOGADOR (XP, NÍVEL E MOEDAS)
# ===================================================
@api_bp.route('/usuario/status', methods=['GET'])
def get_status_jogador():
    """
    Retorna XP, Nível e Aura Coins para o App.
    """
    dados = ler_dados_jogador()
    
    if not dados:
        return jsonify({
            "nome": "Iniciado",
            "xp_total": 0,
            "aura_coins": 0,
            "nivel": 1,
            "xp_necessario_proximo": 1000,
            "barra_progresso": 0,
            "foto": ""
        })

    # Extrai dados
    xp_atual = dados.get("xp_total", 0)
    aura_coins = dados.get("aura_coins", 0)
    nome = dados.get("nome", "Atleta")
    foto = dados.get("foto_perfil", "")

    # Matemática do Nível
    XP_POR_NIVEL = 1000
    nivel_atual = int(xp_atual / XP_POR_NIVEL) + 1
    xp_restante_para_proximo = XP_POR_NIVEL - (xp_atual % XP_POR_NIVEL)
    
    xp_nesse_nivel = xp_atual % XP_POR_NIVEL
    progresso_percent = int((xp_nesse_nivel / XP_POR_NIVEL) * 100)

    return jsonify({
        "nome": nome,
        "foto": foto,
        "xp_total": xp_atual,
        "aura_coins": aura_coins,
        "nivel": nivel_atual,
        "xp_necessario_proximo": xp_restante_para_proximo,
        "barra_progresso": progresso_percent,
        "strava_conectado": True
    })

# ===================================================
# 🏆 ROTA DE RANKING (CLÃ)
# ===================================================
@api_bp.route('/cla/ranking', methods=['GET'])
def get_ranking_cla():
    """
    Retorna a lista dos Top Jogadores ordenados por XP.
    """
    ranking = obter_ranking_global(limite=20) 
    return jsonify({"ranking": ranking})

# ===================================================
# 🕵️ ROTA ANTI-FRAUDE (O DETETIVE) - NOVO!
# ===================================================
@api_bp.route('/antifraude/validar', methods=['POST'])
def validar_atividade():
    """
    Recebe uma data (YYYY-MM-DD) e verifica se existe 
    atividade real do Strava nesse dia no histórico do usuário.
    """
    try:
        dados_input = request.get_json(force=True)
        data_declarada_str = dados_input.get('data') # Ex: "2025-11-27"
        
        # 1. Busca os dados do usuário e seu histórico no Mongo
        usuario = ler_dados_jogador()
        
        if not usuario:
            return jsonify({"aprovado": False, "motivo": "Usuário não encontrado no banco de dados."}), 404

        historico = usuario.get('historico_atividades', [])
        
        # 2. O Grande Loop: Procura se TEM prova no Strava
        encontrou_prova = False
        
        for atividade in historico:
            data_real = atividade.get('data')
            
            # Tratamento de formato de data (pode vir como string ou objeto datetime)
            if isinstance(data_real, str):
                data_real_str = data_real[:10] # Pega YYYY-MM-DD
            elif isinstance(data_real, datetime):
                data_real_str = data_real.strftime('%Y-%m-%d')
            else:
                continue # Pula se formato desconhecido
                
            if data_real_str == data_declarada_str:
                encontrou_prova = True
                break
        
        # 3. O Veredito
        if encontrou_prova:
            return jsonify({
                "aprovado": True, 
                "msg": "Validação biométrica confirmada via Strava."
            })
        else:
            return jsonify({
                "aprovado": False, 
                "motivo": "Nenhuma atividade encontrada no seu Strava/Wearable nesta data. Sincronize seu relógio e tente novamente."
            })
            
    except Exception as e:
        print(f"Erro na validação antifraude: {e}")
        return jsonify({"aprovado": False, "motivo": "Erro interno na verificação."}), 500

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
# 👤 JOGADOR E DADOS (LEGADO)
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