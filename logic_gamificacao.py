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
XP_BASE_NIVEL = 1000        # Custo do primeiro nível
XP_SONO_OTIMO = 50          # Dormiu > 7h
XP_SONO_BOM = 30            # Dormiu > 6h
XP_TREINO_INSANO = 100      # Intensidade > 80% ou Duração > 45min
XP_TREINO_BOM = 50          # Intensidade > 50%

# Economia Premium
CRISTAIS_POR_LEVEL_UP = 10  # Moeda forte ganha ao evoluir

# ======================================================
# 🎮 LÓGICA CENTRAL DE GAMIFICAÇÃO
# ======================================================

def gerar_missoes_diarias(user_id: str) -> List[Dict[str, Any]]:
    """
    Sorteia 3 novas missões para o usuário específico.
    Verifica se já existem missões hoje para garantir idempotência.
    """
    if not user_id: return []

    memoria = carregar_memoria(user_id)
    if not memoria: return []

    hoje_str = str(datetime.now().date())
    gamificacao = memoria.get("gamificacao", {})
    
    # 1. Verificação de Idempotência (Já gerou hoje?)
    ultima_geracao = gamificacao.get("ultima_geracao_missoes", "").split(" ")[0]
    missoes_atuais = gamificacao.get("missoes_ativas", [])

    if ultima_geracao == hoje_str and missoes_atuais:
        # Se já tem missões de hoje, retorna elas (cache)
        return missoes_atuais

    # 2. Buscar Banco de Missões no MongoDB
    todas_missoes = []
    if mongo_db is not None:
        try:
            # Converte cursor para lista e pega apenas campos necessários
            cursor = mongo_db["missoes"].find({}, {"_id": 0, "id": 1, "descricao": 1, "xp": 1})
            todas_missoes = list(cursor)
        except Exception as e:
            logger.error(f"Erro ao buscar missões no banco: {e}")

    # Fallback se banco estiver vazio
    if not todas_missoes:
        todas_missoes = [
            {"id": "m_fallback", "descricao": "Beba 2L de água", "xp": 50},
            {"id": "m_fallback_2", "descricao": "Caminhe 15 min", "xp": 30}
        ]

    # 3. Sorteio de 3 Missões Aleatórias
    qtd_sorteio = min(3, len(todas_missoes))
    novas = random.sample(todas_missoes, qtd_sorteio)

    missoes_ativas = []
    for m in novas:
        missoes_ativas.append({
            "id": m.get("id", "sem_id"),
            "descricao": m.get("descricao", "Missão Misteriosa"),
            "xp": m.get("xp", 10),
            "concluida": False,
            "data_geracao": hoje_str
        })

    # 4. Salvar no Perfil do Usuário
    if "gamificacao" not in memoria: memoria["gamificacao"] = {}
    
    memoria["gamificacao"]["missoes_ativas"] = missoes_ativas
    memoria["gamificacao"]["ultima_geracao_missoes"] = str(datetime.now())
    
    salvar_memoria(user_id, memoria)
    logger.info(f"🎲 Novas missões geradas para User {user_id}")
    
    return missoes_ativas

def aplicar_xp(user_id: str, quantidade: int) -> Dict[str, Any]:
    """
    Adiciona XP ao jogador, verifica Level Up e concede recompensas.
    Retorna o status pós-operação.
    """
    if not user_id: return {"erro": "Sem user_id"}

    memoria = carregar_memoria(user_id)
    if not memoria: return {"erro": "Usuário não encontrado"}

    jogador = memoria.get("jogador", {})
    
    # Inicialização defensiva
    xp_atual = jogador.get("experiencia", 0)
    nivel_atual = jogador.get("nivel", 1)
    cristais_atuais = jogador.get("saldo_cristais", 0)

    # Aplica XP
    xp_atual += quantidade
    subiu_de_nivel = False
    cristais_ganhos_total = 0
    
    # Loop de Level Up (Pode subir mais de um nível se ganhar muito XP)
    while True:
        xp_necessario = XP_BASE_NIVEL * nivel_atual
        
        if xp_atual >= xp_necessario:
            xp_atual -= xp_necessario # Reseta a barra (estilo RPG clássico) ou mantém o excedente
            nivel_atual += 1
            
            # Recompensa Premium
            cristais_ganhos_total += CRISTAIS_POR_LEVEL_UP
            cristais_atuais += CRISTAIS_POR_LEVEL_UP
            
            subiu_de_nivel = True
            logger.info(f"🆙 LEVEL UP! User {user_id} -> Nível {nivel_atual}")
        else:
            break
            
    # Atualiza o objeto jogador
    jogador["experiencia"] = xp_atual
    jogador["nivel"] = nivel_atual
    jogador["saldo_cristais"] = cristais_atuais
    
    # Salva no banco
    memoria["jogador"] = jogador
    salvar_memoria(user_id, memoria)
    
    return {
        "novo_xp": xp_atual, 
        "novo_nivel": nivel_atual, 
        "subiu": subiu_de_nivel,
        "cristais_ganhos": cristais_ganhos_total
    }

# ======================================================
# 📐 CÁLCULOS AUXILIARES (SENSORES)
# ======================================================

def calcular_xp_fisiologico(dados_fisiologicos: Dict[str, Any]) -> int:
    """
    Calcula XP baseado nos dados dos sensores (Sono e Treino).
    Chamado pelo rotina_diaria ou webhook.
    """
    xp_ganho = 0
    
    # Helpers de extração segura
    horas_sono = _extrair_valor(dados_fisiologicos, "sono", "horas")
    intensidade_treino = _extrair_valor(dados_fisiologicos, "treino", "intensidade")
    duracao_treino = _extrair_valor(dados_fisiologicos, "treino", "duracao_min")

    # Regra 1: Sono Reparador
    if horas_sono >= 7: xp_ganho += XP_SONO_OTIMO
    elif horas_sono >= 6: xp_ganho += XP_SONO_BOM

    # Regra 2: Esforço Físico
    if intensidade_treino > 80 or duracao_treino > 45:
        xp_ganho += XP_TREINO_INSANO
    elif intensidade_treino > 50:
        xp_ganho += XP_TREINO_BOM

    return xp_ganho

def _extrair_valor(dados: dict, chave: str, subchave: str) -> float:
    """Extrai valor numérico lidando com dicionários aninhados."""
    raw = dados.get(chave, {})
    if isinstance(raw, dict):
        return float(raw.get(subchave, 0))
    try:
        return float(raw)
    except (ValueError, TypeError):
        return 0.0