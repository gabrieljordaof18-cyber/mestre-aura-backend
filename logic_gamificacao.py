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
XP_SONO_OTIMO = 50          # Recompensa por sono > 7h
XP_SONO_BOM = 30            
XP_TREINO_INSANO = 100      # Intensidade alta ou longa duração
XP_TREINO_BOM = 50          

# Economia Premium (Conforme modelos_banco_aura.txt)
CRISTAIS_POR_LEVEL_UP = 10  # Saldo de Cristais (Premium)

# ======================================================
# 🎮 NÚCLEO DE GAMIFICAÇÃO (LEVELS E MISSÕES)
# ======================================================

def gerar_missoes_diarias(user_id: str) -> List[Dict[str, Any]]:
    """
    Gera ou recupera as 3 missões diárias do usuário.
    Garante que o pool de missões venha do banco central.
    """
    if not user_id: return []

    memoria = carregar_memoria(user_id)
    if not memoria: return []

    hoje_str = datetime.now().date().isoformat()
    gamificacao = memoria.get("gamificacao", {})
    
    # 1. Verificação de Idempotência (Evita resetar missões no mesmo dia)
    ultima_geracao = gamificacao.get("ultima_geracao_missoes", "").split("T")[0]
    missoes_atuais = gamificacao.get("missoes_ativas", [])

    if ultima_geracao == hoje_str and missoes_atuais:
        return missoes_atuais

    # 2. Busca o Pool de Missões no MongoDB (Coleção 'missoes')
    pool_missoes = []
    if mongo_db is not None:
        try:
            # Filtra apenas missões ativas conforme definido no JSON anterior
            cursor = mongo_db["missoes"].find({"ativo": True}, {"_id": 0})
            pool_missoes = list(cursor)
        except Exception as e:
            logger.error(f"❌ Erro ao acessar banco de missões: {e}")

    # Fallback caso o banco esteja offline ou vazio
    if not pool_missoes:
        pool_missoes = [{"id": "m_h2o", "descricao": "Beber 2L de água", "xp": 50, "categoria": "saude"}]

    # 3. Sorteio Aleatório de 3 Desafios
    selecionadas = random.sample(pool_missoes, min(3, len(pool_missoes)))

    missoes_ativas = []
    for m in selecionadas:
        missoes_ativas.append({
            "id": m.get("id"),
            "descricao": m.get("descricao"),
            "xp": m.get("xp", 50),
            "categoria": m.get("categoria", "geral"),
            "concluida": False,
            "data_geracao": hoje_str
        })

    # 4. Atualiza Memória do Jogador (Schema 2.0)
    if "gamificacao" not in memoria: memoria["gamificacao"] = {}
    
    memoria["gamificacao"]["missoes_ativas"] = missoes_ativas
    memoria["gamificacao"]["ultima_geracao_missoes"] = datetime.now().isoformat()
    
    salvar_memoria(user_id, memoria)
    logger.info(f"🎲 Ciclo de missões renovado para o usuário {user_id}")
    
    return missoes_ativas

def aplicar_xp(user_id: str, quantidade: int) -> Dict[str, Any]:
    """
    Adiciona XP e gerencia a progressão de nível e moedas premium.
    """
    if not user_id: return {"erro": "ID ausente"}

    memoria = carregar_memoria(user_id)
    if not memoria: return {"erro": "Perfil não carregado"}

    jogador = memoria.get("jogador", {})
    
    xp_atual = jogador.get("experiencia", 0)
    nivel_atual = jogador.get("nivel", 1)
    cristais_atuais = jogador.get("saldo_cristais", 0)

    xp_atual += quantidade
    subiu_nivel = False
    total_cristais_ganhos = 0
    
    # Lógica de Progressão (XP Necessário aumenta com o nível)
    while xp_atual >= (XP_BASE_NIVEL * nivel_atual):
        xp_atual -= (XP_BASE_NIVEL * nivel_atual)
        nivel_atual += 1
        total_cristais_ganhos += CRISTAIS_POR_LEVEL_UP
        subiu_nivel = True
        logger.info(f"🆙 LEVEL UP: {user_id} atingiu o Nível {nivel_atual}")

    # Atualiza Atributos do Jogador
    jogador["experiencia"] = xp_atual
    jogador["nivel"] = nivel_atual
    jogador["saldo_cristais"] = cristais_atuais + total_cristais_ganhos
    
    memoria["jogador"] = jogador
    salvar_memoria(user_id, memoria)
    
    return {
        "novo_xp": xp_atual, 
        "novo_nivel": nivel_atual, 
        "subiu": subiu_nivel,
        "cristais_ganhos": total_cristais_ganhos
    }

# ======================================================
# 📐 PROCESSAMENTO DE SENSORES
# ======================================================

def calcular_xp_fisiologico(dados_fisiologicos: Dict[str, Any]) -> int:
    """Traduz dados de saúde em experiência de jogo."""
    xp_ganho = 0
    
    sono = _extrair(dados_fisiologicos, "sono", "horas")
    passos = _extrair(dados_fisiologicos, "passos_hoje", "") # Direto no schema 2.0

    if sono >= 7: xp_ganho += XP_SONO_OTIMO
    elif sono >= 6: xp_ganho += XP_SONO_BOM

    # Exemplo: XP por passos (Gamificação de movimento)
    if passos >= 10000: xp_ganho += 50
    elif passos >= 5000: xp_ganho += 20

    return xp_ganho

def _extrair(dados: dict, chave: str, sub: str) -> float:
    raw = dados.get(chave, 0)
    if isinstance(raw, dict) and sub:
        return float(raw.get(sub, 0))
    try: return float(raw)
    except: return 0.0