from datetime import datetime
from typing import Dict, Any

# ==============================================================
# 📘 DICIONÁRIO OFICIAL DE DADOS (SCHEMA)
# ==============================================================
# Define a estrutura PADRÃO para novos arquivos ou reset de sistema.

def obter_schema_padrao_usuario() -> Dict[str, Any]:
    """Retorna a estrutura inicial de um novo usuário (memoria.json)."""
    return {
        "_system_updated_at": str(datetime.now()),
        "jogador": {
            "nome": "Atleta", 
            "nivel": 1,
            "experiencia": 0, 
            "saldo_coins": 0,      # Moeda Comum (Aura Coins)
            "saldo_cristais": 0,   # NOVA MOEDA PREMIUM (Cristais Aura)
            "avatar_frame_id": None, # NOVO: Para molduras cosméticas
            "energia": 100,
            "missoes_concluidas": 0,
            "status_atual": {
                "humor": "neutro",
                "ultima_atualizacao": ""
            },
            "metas": {
                "peso_alvo": 70,
                "objetivo": "saúde",
                "frequencia_treino": "3x por semana"
            },
            "preferencias": {
                "horario_treino": "manhã",
                "sono_medio": "7h"
            }
        },
        "dados_fisiologicos": {
            "frequencia_cardiaca": 70, 
            "variabilidade_hrv": 50,
            "passos_diarios": 0,
            "calorias_gastas": 0,
            "ultima_sincronizacao": "",
            "hrv": {"valor": 50, "status": "neutro"},
            "sono": {"horas": 7.0, "qualidade": "regular"},
            "energia": {"nivel": 80, "status": "bom"},
            "treino": {"intensidade": 0, "duracao_min": 0, "tipo": "descanso"}
        },
        "gamificacao": {
            "xp_total": 0, 
            "nivel": 1,
            "xp_para_prox_nivel": 1000,
            "missoes_ativas": [],
            "ultima_geracao_missoes": ""
        },
        "homeostase": {
            "score": 50,
            "estado": "Calculando...",
            "componentes": {"corpo": 50, "mente": 50, "energia": 50}
        },
        "historico": [
            {"role": "system", "content": "Sistema iniciado. Bem-vindo ao AURA."}
        ],
        "logs": [],
        "integracoes": {"apple": False, "garmin": False, "strava": False},
        "configuracoes_sistema": {
            "versao_mestre_aura": "20.0",
            "modo_treinamento": "ativo",
            "auto_update_sensores": True
        }
    }

def obter_schema_padrao_global() -> Dict[str, Any]:
    """Retorna a estrutura inicial da Memória Global (IA) - memoria_global.json."""
    return {
        "_system_updated_at": str(datetime.now()),
        "personalidade": {
            "nome": "Mestre da AURA",
            "versao": "20.0 (Base44)",
            "descricao": "Mentor de alta performance. Técnico e motivador."
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
        "gamificacao": {
            "missoes_diarias_historico": [],
            "ranking_global": [] 
        },
        "homeostase": { 
             "score_harmonia": 50,
             "estado": "Neutro",
             "componentes": {"corpo": 50, "mente": 50, "energia": 50},
             "ultima_atualizacao": ""
        },
        "ultima_atualizacao_global": str(datetime.now())
    }

# NOVO: Schema para Produtos do Mercado (Padronização)
def obter_schema_padrao_produto() -> Dict[str, Any]:
    """Define a estrutura de um item no mercado."""
    return {
        "id": "",
        "nome": "",
        "marca": "",
        "preco_cheio": 0.0,
        "desconto_percentual": 12, # Novo padrão: 12%
        "preco_final": 0.0,
        "custo_aura_coins": 0,
        "cashback_cristais": 0,    # Novo: Cashback em Cristais
        "nivel_minimo": 1,         # Novo: Trava de Nível (Ex: 30 para Black Edition)
        "imagem_url": "",
        "categoria": "suplementos",
        "estoque": True
    }