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

# Economia Premium
CRISTAIS_POR_LEVEL_UP = 10  # Saldo de Cristais (Premium)

# ======================================================
# 🎮 NÚCLEO DE GAMIFICAÇÃO (LEVELS E MISSÕES)
# ======================================================

def gerar_missoes_diarias(user_id: str) -> List[Dict[str, Any]]:
    """
    Gera ou recupera as 3 missões diárias do usuário.
    Garante que o pool de missões venha da coleção 'missoes' do MongoDB.
    """
    if not user_id: return []

    # 1. Carrega Perfil (Sincronizado com o ID do Render)
    memoria = carregar_memoria(user_id)
    if not memoria: return []

    hoje_str = datetime.now().date().isoformat()
    gamificacao = memoria.get("gamificacao", {})
    
    # Verificação de Idempotência (Evita resetar missões no mesmo dia)
    ultima_geracao = str(gamificacao.get("ultima_geracao_missoes", "")).split("T")[0]
    missoes_atuais = gamificacao.get("missoes_ativas", [])

    if ultima_geracao == hoje_str and missoes_atuais:
        return missoes_atuais

    # 2. Busca o Pool de Missões no MongoDB Atlas
    pool_missoes = []
    # [AURA FIX] Comparação explícita com None exigida pelo PyMongo
    if mongo_db is not None:
        try:
            # Buscamos as missões que definimos no passo 2 da nossa auditoria
            cursor = mongo_db["missoes"].find({"ativo": True}, {"_id": 0})
            pool_missoes = list(cursor)
        except Exception as e:
            logger.error(f"❌ Erro ao acessar coleção 'missoes': {e}")

    # Fallback robusto caso o banco esteja vazio
    if not pool_missoes:
        pool_missoes = [
            {"id": "m_h2o", "titulo": "Hidratação", "descricao": "Beber 2L de água", "xp": 50, "categoria": "saude", "icone": "Zap"},
            {"id": "m_mov", "titulo": "Movimento", "descricao": "Caminhada de 20 min", "xp": 60, "categoria": "treino", "icone": "Rocket"}
        ]

    # 3. Sorteio Aleatório de 3 Desafios Únicos
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
            "xp": m.get("xp", 50),
            "categoria": m.get("categoria", "geral"),
            "icone": m.get("icone", "Target"),
            "concluida": False,
            "data_geracao": hoje_str
        })

    # 4. Atualiza Memória do Jogador (Sincronização MongoDB Atlas)
    if "gamificacao" not in memoria: 
        memoria["gamificacao"] = {}
    
    memoria["gamificacao"]["missoes_ativas"] = missoes_ativas
    memoria["gamificacao"]["ultima_geracao_missoes"] = datetime.now().isoformat()
    
    # Persistência via Render
    salvar_memoria(user_id, memoria)
    logger.info(f"🎲 Ciclo de missões renovado no Atlas para {user_id}")
    
    return missoes_ativas

def aplicar_xp(user_id: str, quantidade: int) -> Dict[str, Any]:
    """
    Adiciona XP e gerencia progressão de nível e cristais.
    [AURA FIX] Ajustado para salvar na RAIZ do documento conforme seu MongoDB real.
    """
    if not user_id: return {"erro": "ID ausente"}

    memoria = carregar_memoria(user_id)
    if not memoria: return {"erro": "Perfil não carregado"}

    # [AURA FIX] Mapeamento direto com os campos do seu Atlas (sem o objeto 'jogador')
    xp_atual = int(memoria.get("xp_total", 0))
    nivel_atual = int(memoria.get("nivel", 1))
    cristais_atuais = int(memoria.get("saldo_cristais", 0))

    xp_atual += quantidade
    subiu_nivel = False
    total_cristais_ganhos = 0
    
    # Lógica de Progressão: Custo aumenta linearmente
    while xp_atual >= (XP_BASE_NIVEL * nivel_atual):
        xp_atual -= (XP_BASE_NIVEL * nivel_atual)
        nivel_atual += 1
        total_cristais_ganhos += CRISTAIS_POR_LEVEL_UP
        subiu_nivel = True
        logger.info(f"🆙 LEVEL UP: {user_id} atingiu o Nível {nivel_atual}")

    # [AURA FIX] Atualiza diretamente na raiz da memória para sincronizar com o Frontend
    memoria["xp_total"] = xp_atual
    memoria["nivel"] = nivel_atual
    memoria["saldo_cristais"] = cristais_atuais + total_cristais_ganhos
    
    # Salva a evolução no MongoDB Atlas
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
    """Traduz dados de saúde (status_atual) em experiência de jogo."""
    xp_ganho = 0
    
    # [AURA FIX] Extração segura do objeto 'status_atual'
    sono = _extrair(dados_fisiologicos, "sono", "horas")
    passos = _extrair(dados_fisiologicos, "passos_hoje", "") 

    if sono >= 7: xp_ganho += XP_SONO_OTIMO
    elif sono >= 6: xp_ganho += XP_SONO_BOM

    # Gamificação de movimento detectado
    if passos >= 10000: xp_ganho += 50
    elif passos >= 5000: xp_ganho += 20

    return xp_ganho

def _extrair(dados: dict, chave: str, sub: str) -> float:
    """Navega no dicionário de dados de sensores com segurança."""
    if not dados: return 0.0
    raw = dados.get(chave, 0)
    if isinstance(raw, dict) and sub:
        return float(raw.get(sub, 0))
    try: 
        return float(raw)
    except (ValueError, TypeError): 
        return 0.0