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
# ⚙️ CONSTANTES DE JOGO (BALANCEAMENTO 3.0)
# ======================================================
XP_BASE_NIVEL = 1000        # Custo base para subir de nível

# [AURA ROBUST] Bônus escalonados para o novo fluxo de 10 exercícios
XP_SONO_OTIMO = 60          
XP_SONO_BOM = 35            
XP_TREINO_INSANO = 150      # Para treinos de 10 exercícios ou alta intensidade Strava
XP_TREINO_COMPLEXO = 80     # Para treinos entre 5 e 8 exercícios
XP_TREINO_BOM = 50          

# Economia Premium (Bônus extra ao subir de nível)
CRISTAIS_POR_LEVEL_UP = 25  

# ======================================================
# 🎮 NÚCLEO DE GAMIFICAÇÃO (LEVELS E MISSÕES)
# ======================================================

def gerar_missoes_diarias(user_id: str) -> List[Dict[str, Any]]:
    """
    Gera ou recupera as 3 missões diárias do usuário.
    Sincronizado com a coleção 'missoes' do MongoDB Atlas.
    Agora inclui desafios para o fluxo de treinos híbridos.
    """
    if not user_id: return []

    memoria = carregar_memoria(user_id)
    if not memoria: return []

    hoje_str = datetime.now().date().isoformat()
    gamificacao = memoria.get("gamificacao", {})
    
    ultima_geracao = str(gamificacao.get("ultima_geracao_missoes", "")).split("T")[0]
    missoes_atuais = gamificacao.get("missoes_ativas", [])

    # Se já gerou missões hoje, retorna as mesmas para manter consistência
    if ultima_geracao == hoje_str and missoes_atuais:
        return missoes_atuais

    pool_missoes = []
    if mongo_db is not None:
        try:
            cursor = mongo_db["missoes"].find({"ativo": True}, {"_id": 0})
            pool_missoes = list(cursor)
        except Exception as e:
            logger.error(f"❌ Erro ao acessar coleção 'missoes': {e}")

    # Fallback caso a coleção esteja vazia (Inclui missões híbridas)
    if not pool_missoes:
        pool_missoes = [
            {"id": "m_h2o", "titulo": "Hidratação", "descricao": "Beber 3L de água", "xp": 100, "categoria": "saude", "icone": "Zap"},
            {"id": "m_hybrid", "titulo": "Foco Híbrido", "descricao": "Musculação + 10min Cardio", "xp": 150, "categoria": "treino", "icone": "Flame"},
            {"id": "m_mov", "titulo": "Consistência", "descricao": "Bater 10.000 passos", "xp": 100, "categoria": "treino", "icone": "Rocket"},
            {"id": "m_sono", "titulo": "Repouso Mestre", "descricao": "Dormir antes das 23h", "xp": 120, "categoria": "saude", "icone": "Moon"}
        ]

    try:
        # Seleção aleatória de 3 desafios únicos
        selecionadas = random.sample(pool_missoes, min(3, len(pool_missoes)))
    except ValueError:
        selecionadas = pool_missoes

    missoes_ativas = []
    for m in selecionadas:
        missoes_ativas.append({
            "id": m.get("id"),
            "titulo": m.get("titulo", "Desafio Aura"),
            "descricao": m.get("descricao"),
            "xp": m.get("xp", 100),
            "categoria": m.get("categoria", "geral"),
            "icone": m.get("icone", "Target"),
            "concluida": False,
            "data_geracao": hoje_str
        })

    # Atualiza a memória local antes de salvar no Atlas
    if "gamificacao" not in memoria: 
        memoria["gamificacao"] = {}
    
    memoria["gamificacao"]["missoes_ativas"] = missoes_ativas
    memoria["gamificacao"]["ultima_geracao_missoes"] = datetime.now().isoformat()
    
    salvar_memoria(user_id, memoria)
    logger.info(f"🎲 [GAMIFICAÇÃO] Ciclo de missões renovado para {user_id}")
    
    return missoes_ativas

def aplicar_xp(user_id: str, quantidade: int) -> Dict[str, Any]:
    """
    Adiciona XP e gerencia a progressão econômica Aura.
    LÓGICA UNIFICADA: 
    - Moedas = XP Ganhos (1:1)
    - Cristais = XP Ganhos / 10 (Garante inteiro)
    - Bônus de Level Up incluído com proteção contra loop.
    """
    if not user_id: return {"erro": "ID ausente"}

    memoria = carregar_memoria(user_id)
    if not memoria: return {"erro": "Perfil não carregado"}

    # Captura de saldos na raiz (XP, Moedas, Cristais)
    xp_atual = int(memoria.get("xp_total", 0))
    nivel_atual = int(memoria.get("nivel", 1))
    moedas_atuais = int(memoria.get("moedas", 0))
    cristais_atuais = int(memoria.get("saldo_cristais", 0))

    # [AURA FIX] Cristais agora são sempre inteiros
    ganho_moedas = int(quantidade)
    ganho_cristais = int(quantidade // 10)

    xp_atual += ganho_moedas
    moedas_atuais += ganho_moedas
    cristais_atuais += ganho_cristais

    subiu_nivel = False
    bonus_level_up_cristais = 0
    
    # [AURA FIX] Lógica de Progressão com proteção contra looping infinito
    # Limitamos a subida a no máximo 10 níveis por vez para evitar travamentos de processamento
    seguranca_loop = 0
    while xp_atual >= (XP_BASE_NIVEL * nivel_atual) and seguranca_loop < 10:
        xp_atual -= (XP_BASE_NIVEL * nivel_atual)
        nivel_atual += 1
        bonus_level_up_cristais += CRISTAIS_POR_LEVEL_UP
        subiu_nivel = True
        seguranca_loop += 1
        logger.info(f"🆙 [LEVEL UP] {user_id} atingiu o Nível {nivel_atual}")

    # Atualiza o saldo final com bônus de nível
    cristais_atuais += bonus_level_up_cristais

    # Persistência na RAIZ do documento do Atlas para sincronia com Base44
    memoria["xp_total"] = xp_atual
    memoria["nivel"] = nivel_atual
    memoria["moedas"] = moedas_atuais
    memoria["saldo_cristais"] = cristais_atuais
    
    # Atualiza estatísticas de performance para o perfil
    if "gamificacao" in memoria:
        if "estatisticas" not in memoria["gamificacao"]:
            memoria["gamificacao"]["estatisticas"] = {"missoes_completadas": 0, "total_atividades": 0, "dias_seguidos": 0}
        memoria["gamificacao"]["estatisticas"]["total_atividades"] += 1

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
    """Traduz dados de biometria em economia ativa."""
    xp_ganho = 0
    
    # Extração robusta dos campos unificados do Atlas
    sono = float(dados_fisiologicos.get("sono_horas", 0))
    passos = int(dados_fisiologicos.get("passos_hoje", 0))
    fadiga = int(dados_fisiologicos.get("fadiga", 0))

    # Recompensa por Sono de Qualidade
    if sono >= 7.5: xp_ganho += XP_SONO_OTIMO
    elif sono >= 6.5: xp_ganho += XP_SONO_BOM

    # Recompensa por Movimentação Diária
    if passos >= 12000: xp_ganho += 70
    elif passos >= 8000: xp_ganho += 40
    
    # Bônus por consistência em dias de fadiga controlada
    if fadiga < 30 and passos > 5000:
        xp_ganho += 20

    return xp_ganho