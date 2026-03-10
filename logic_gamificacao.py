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
# ⚙️ CONSTANTES DE JOGO (BALANCEAMENTO 3.1 - NATIVE READY)
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
    [AURA SYNC] Títulos e Ícones ajustados para o novo layout do Perfil.jsx e Home.
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
            # Buscamos as missões ativas no Atlas
            cursor = mongo_db["missoes"].find({"ativo": True}, {"_id": 0})
            pool_missoes = list(cursor)
        except Exception as e:
            logger.error(f"❌ Erro ao acessar coleção 'missoes': {e}")

    # [AURA SYNC] Fallback com títulos imersivos (Substituindo o genérico 'Desafio Aura')
    if not pool_missoes:
        pool_missoes = [
            {"id": "m_h2o", "titulo": "Caminho da Água", "descricao": "Ingerir 3.5L de água hoje", "xp": 100, "categoria": "saude", "icone": "Zap"},
            {"id": "m_hybrid", "titulo": "Protocolo Híbrido", "descricao": "Musculação + 15min de Cardio", "xp": 150, "categoria": "treino", "icone": "Flame"},
            {"id": "m_mov", "titulo": "Nômade Moderno", "descricao": "Bater a meta de 10.000 passos", "xp": 100, "categoria": "treino", "icone": "Activity"},
            {"id": "m_sono", "titulo": "Mestre do Descanso", "descricao": "Garantir 8h de sono profundo", "xp": 120, "categoria": "descanso", "icone": "Moon"},
            {"id": "m_foco", "titulo": "Mente Blindada", "descricao": "Completar 10min de Meditação", "xp": 80, "categoria": "mente", "icone": "Brain"}
        ]

    try:
        # Seleção aleatória de 3 desafios únicos
        selecionadas = random.sample(pool_missoes, min(3, len(pool_missoes)))
    except ValueError:
        selecionadas = pool_missoes

    missoes_ativas = []
    for m in selecionadas:
        # [AURA SYNC] Prioridade absoluta para o Título Específico para evitar duplicidade visual no front
        titulo_final = m.get("titulo") or "Missão Diária"

        missoes_ativas.append({
            "id": m.get("id"),
            "titulo": titulo_final,
            "descricao": m.get("descricao", "Complete o desafio para evoluir"),
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
    logger.info(f"🎲 [GAMIFICAÇÃO] Ciclo de missões renovado com novos títulos para {user_id}")
    
    return missoes_ativas

def aplicar_xp(user_id: str, quantidade: int) -> Dict[str, Any]:
    """
    Adiciona XP e gerencia a progressão econômica Aura.
    LÓGICA UNIFICADA 3.1: 
    - Moedas = XP Ganhos (1:1)
    - Cristais = XP Ganhos / 10 (Divisão inteira //)
    - Bônus de Level Up com verificação de Schema.
    """
    if not user_id: return {"erro": "ID ausente"}

    memoria = carregar_memoria(user_id)
    if not memoria: return {"erro": "Perfil não carregado"}

    # Captura de saldos na raiz (Sincronizado com data_user.py blindado)
    xp_atual = int(memoria.get("xp_total", 0))
    nivel_atual = int(memoria.get("nivel", 1))
    moedas_atuais = int(memoria.get("moedas", 0))
    cristais_atuais = int(memoria.get("saldo_cristais", 0))

    ganho_moedas = int(quantidade)
    ganho_cristais = int(quantidade // 10)

    xp_atual += ganho_moedas
    moedas_atuais += ganho_moedas
    cristais_atuais += ganho_cristais

    subiu_nivel = False
    bonus_level_up_cristais = 0
    
    # [AURA FIX] Lógica de Progressão Estável
    seguranca_loop = 0
    while xp_atual >= (XP_BASE_NIVEL * nivel_atual) and seguranca_loop < 10:
        xp_atual -= (XP_BASE_NIVEL * nivel_atual)
        nivel_atual += 1
        bonus_level_up_cristais += CRISTAIS_POR_LEVEL_UP
        subiu_nivel = True
        seguranca_loop += 1
        logger.info(f"🆙 [LEVEL UP] {user_id} subiu para Nível {nivel_atual}")

    # Atualiza o saldo final com bônus de nível
    cristais_atuais += bonus_level_up_cristais

    # Persistência garantida na raiz do documento
    memoria["xp_total"] = xp_atual
    memoria["nivel"] = nivel_atual
    memoria["moedas"] = moedas_atuais
    memoria["saldo_cristais"] = cristais_atuais
    
    # Estatísticas de engajamento para Rewards futuros
    if "gamificacao" in memoria:
        if "estatisticas" not in memoria["gamificacao"]:
            memoria["gamificacao"]["estatisticas"] = {"missoes_completadas": 0, "total_atividades": 0, "dias_seguidos": 0}
        memoria["gamificacao"]["estatisticas"]["total_atividades"] += 1
        memoria["gamificacao"]["estatisticas"]["missoes_completadas"] += 1

    salvar_memoria(user_id, memoria)
    
    return {
        "novo_xp": xp_atual, 
        "novo_nivel": nivel_atual, 
        "moedas_ganhas": ganho_moedas,
        "cristais_ganhos": ganho_cristais + bonus_level_up_cristais,
        "subiu": subiu_nivel
    }

def calcular_xp_fisiologico(dados_fisiologicos: Dict[str, Any]) -> int:
    """Traduz dados de biometria e sensores em economia ativa para o app nativo."""
    xp_ganho = 0
    
    # Extração de campos via Schema 3.1
    sono = float(dados_fisiologicos.get("sono_horas", 0))
    passos = int(dados_fisiologicos.get("passos_hoje", 0))
    fadiga = int(dados_fisiologicos.get("fadiga", 0))

    # [AURA BALANCE] Recompensa por sono otimizado
    if sono >= 7.5: xp_ganho += XP_SONO_OTIMO
    elif sono >= 6.5: xp_ganho += XP_SONO_BOM

    # [AURA BALANCE] Recompensa por passos (Metas Apple Health Ready)
    if passos >= 12000: xp_ganho += 70
    elif passos >= 8000: xp_ganho += 40
    
    # Bônus de resiliência (atividade física com fadiga baixa)
    if fadiga < 30 and passos > 5000:
        xp_ganho += 20

    return xp_ganho