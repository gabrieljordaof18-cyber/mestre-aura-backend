import logging
import random
from datetime import datetime
from typing import Dict, Any, List

# Importações da Nova Arquitetura
from data_user import carregar_memoria, salvar_memoria
from data_manager import mongo_db

# Configuração de Logs
logger = logging.getLogger("AURA_GAMIFICACAO")

# ======================================================
# ⚙️ CONSTANTES DE JOGO (BALANCEAMENTO)
# ======================================================
XP_BASE_NIVEL = 1000        # Custo base para subir de nível

# [AURA INFO] Bônus por sensores (também seguirão a regra 1:1)
XP_SONO_OTIMO = 50          
XP_SONO_BOM = 30            
XP_TREINO_INSANO = 100      
XP_TREINO_BOM = 50          

# Economia Premium (Bônus extra ao subir de nível)
CRISTAIS_POR_LEVEL_UP = 20  

# ======================================================
# 🎮 NÚCLEO DE GAMIFICAÇÃO (LEVELS E MISSÕES)
# ======================================================

def gerar_missoes_diarias(user_id: str) -> List[Dict[str, Any]]:
    """
    Gera ou recupera as 3 missões diárias do usuário.
    Sincronizado com a coleção 'missoes' do MongoDB Atlas.
    """
    if not user_id: return []

    memoria = carregar_memoria(user_id)
    if not memoria: return []

    hoje_str = datetime.now().date().isoformat()
    gamificacao = memoria.get("gamificacao", {})
    
    ultima_geracao = str(gamificacao.get("ultima_geracao_missoes", "")).split("T")[0]
    missoes_atuais = gamificacao.get("missoes_ativas", [])

    if ultima_geracao == hoje_str and missoes_atuais:
        return missoes_atuais

    pool_missoes = []
    if mongo_db is not None:
        try:
            cursor = mongo_db["missoes"].find({"ativo": True}, {"_id": 0})
            pool_missoes = list(cursor)
        except Exception as e:
            logger.error(f"❌ Erro ao acessar coleção 'missoes': {e}")

    if not pool_missoes:
        pool_missoes = [
            {"id": "m_h2o", "titulo": "Hidratação", "descricao": "Beber 2L de água", "xp": 100, "categoria": "saude", "icone": "Zap"},
            {"id": "m_mov", "titulo": "Movimento", "descricao": "Caminhada de 20 min", "xp": 100, "categoria": "treino", "icone": "Rocket"}
        ]

    try:
        selecionadas = random.sample(pool_missoes, min(3, len(pool_missoes)))
    except ValueError:
        selecionadas = pool_missoes

    missoes_ativas = []
    for m in selecionadas:
        missoes_ativas.append({
            "id": m.get("id"),
            "titulo": m.get("titulo", "Desafio"),
            "descricao": m.get("descricao"),
            "xp": m.get("xp", 100),
            "categoria": m.get("categoria", "geral"),
            "icone": m.get("icone", "Target"),
            "concluida": False,
            "data_geracao": hoje_str
        })

    if "gamificacao" not in memoria: 
        memoria["gamificacao"] = {}
    
    memoria["gamificacao"]["missoes_ativas"] = missoes_ativas
    memoria["gamificacao"]["ultima_geracao_missoes"] = datetime.now().isoformat()
    
    salvar_memoria(user_id, memoria)
    logger.info(f"🎲 Ciclo de missões renovado no Atlas para {user_id}")
    
    return missoes_ativas

def aplicar_xp(user_id: str, quantidade: int) -> Dict[str, Any]:
    """
    Adiciona XP e gerencia a progressão econômica Aura.
    LÓGICA: 
    - Aura Coins = XP Ganhos (1:1)
    - Cristais = XP Ganhos / 10
    """
    if not user_id: return {"erro": "ID ausente"}

    memoria = carregar_memoria(user_id)
    if not memoria: return {"erro": "Perfil não carregado"}

    # [AURA FIX] Captura de saldos na raiz (XP, Moedas, Cristais)
    xp_atual = int(memoria.get("xp_total", 0))
    nivel_atual = int(memoria.get("nivel", 1))
    # 'moedas' representa suas Aura Coins Oficiais (os 18.800)
    moedas_atuais = int(memoria.get("moedas", 0))
    cristais_atuais = int(memoria.get("saldo_cristais", 0))

    # --- APLICAÇÃO DA REGRA DE NEGÓCIO ---
    ganho_moedas = quantidade
    ganho_cristais = int(quantidade / 10)

    xp_atual += quantidade
    moedas_atuais += ganho_moedas
    cristais_atuais += ganho_cristais

    subiu_nivel = False
    bonus_level_up_cristais = 0
    
    # Lógica de Progressão de Nível
    while xp_atual >= (XP_BASE_NIVEL * nivel_atual):
        xp_atual -= (XP_BASE_NIVEL * nivel_atual)
        nivel_atual += 1
        bonus_level_up_cristais += CRISTAIS_POR_LEVEL_UP
        subiu_nivel = True
        logger.info(f"🆙 LEVEL UP: {user_id} atingiu o Nível {nivel_atual}")

    # Atualiza o saldo final com bônus de nível se houver
    cristais_atuais += bonus_level_up_cristais

    # [AURA FIX] Persistência direta na RAIZ para sincronia total com Atlas e Base44
    memoria["xp_total"] = xp_atual
    memoria["nivel"] = nivel_atual
    memoria["moedas"] = moedas_atuais
    memoria["saldo_cristais"] = cristais_atuais
    
    salvar_memoria(user_id, memoria)
    
    return {
        "novo_xp": xp_atual, 
        "novo_nivel": nivel_atual, 
        "moedas_ganhas": ganho_moedas,
        "cristais_ganhos": ganho_cristais + bonus_level_up_cristais,
        "subiu": subiu_nivel
    }

# ======================================================
# 📐 PROCESSAMENTO DE SENSORES
# ======================================================

def calcular_xp_fisiologico(dados_fisiologicos: Dict[str, Any]) -> int:
    """Traduz dados de saúde em experiência e economia."""
    xp_ganho = 0
    
    sono = _extrair(dados_fisiologicos, "sono_horas", "")
    passos = _extrair(dados_fisiologicos, "passos_hoje", "") 

    if sono >= 7: xp_ganho += XP_SONO_OTIMO
    elif sono >= 6: xp_ganho += XP_SONO_BOM

    if passos >= 10000: xp_ganho += 50
    elif passos >= 5000: xp_ganho += 20

    return xp_ganho

def _extrair(dados: dict, chave: str, sub: str) -> float:
    if not dados: return 0.0
    raw = dados.get(chave, 0)
    if isinstance(raw, dict) and sub:
        return float(raw.get(sub, 0))
    try: 
        return float(raw)
    except (ValueError, TypeError): 
        return 0.0