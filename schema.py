# schema.py
from datetime import datetime

# ==============================================================
# 📘 DICIONÁRIO OFICIAL DE DADOS (SCHEMA)
# ==============================================================
# Aqui definimos a estrutura PADRÃO. Se o arquivo json estiver vazio
# ou incompleto, usamos estes valores para preencher.

def obter_schema_padrao_usuario():
    """Retorna a estrutura inicial de um novo usuário."""
    return {
        "jogador": {
            "nome": "Gabriel",
            "energia": 100, # 0 a 100
            "experiencia": 0, # XP Total Acumulado (substitui xp_total da gamificação se quiser unificar)
            "aura_coins": 0,
            "missoes_concluidas": 0,
            "nivel": 1,
            "status_atual": {
                "humor": "neutro",
                "ultima_atualizacao": ""
            },
            "metas": {
                "peso_alvo": 80,
                "objetivo": "ganho de massa muscular",
                "frequencia_treino": "6x por semana"
            },
            "preferencias": {
                "horario_treino": "manhã",
                "sono_medio": "7h" # String simples para display
            }
        },
        "dados_fisiologicos": {
            # Padronização: Sempre usaremos dicionários com 'valor' e 'unidade' ou detalhes
            "frequencia_cardiaca": 72, 
            "hrv": {"valor": 50, "status": "neutro"}, # Unificando HRV aqui
            "sono": {"horas": 7.0, "qualidade": "regular"},
            "energia": {"nivel": 80, "status": "bom"},
            "treino": {"intensidade": 0, "duracao_min": 0, "tipo": "descanso"},
            "passos_diarios": 0,
            "ultima_sincronizacao": ""
        },
        "gamificacao": {
            "xp_total": 0, # Mantemos aqui para compatibilidade com seu código antigo
            "nivel": 1,
            "xp_para_prox_nivel": 100,
            "missoes_ativas": [],
            "ultima_geracao_missoes": ""
        },
        "homeostase": { # Fase 19
            "score": 50,
            "estado": "Calculando...",
            "componentes": {"corpo": 50, "mente": 50, "energia": 50}
        },
        "historico": [],
        "logs": [],
        "integracoes": {"apple": False, "garmin": False, "strava": False}
    }

def obter_schema_padrao_global():
    """Retorna a estrutura inicial da Memória Global (IA)."""
    return {
        "personalidade": {
            "nome": "Mestre da AURA",
            "versao": "Base44-1.0",
            "descricao": "Mentor de alta performance."
        },
        "afinidade": {
            "score": 50,
            "min": 0,
            "max": 100,
            "ultima_atualizacao": ""
        },
        "interacoes": [],
        "estatisticas": {
            "positivas": 0, "negativas": 0, "neutras": 0, "total": 0
        },
        # Gamificação Global (Backup/Registro Mestre)
        "gamificacao": {
            "missoes_diarias_historico": [],
            "ranking_global": [] 
        },
        "equilibrio": {
             "harmonia": 50,
             "ultima_atualizacao": ""
        },
        "ultima_atualizacao_global": str(datetime.now())
    }