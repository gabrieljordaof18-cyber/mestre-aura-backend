from datetime import datetime
from typing import Dict, Any

# ==============================================================
# 📘 DICIONÁRIO OFICIAL DE DADOS (SCHEMA 2.0 - AURA PERFORMANCE)
# ==============================================================

def obter_schema_padrao_usuario(email: str = "", nome: str = "Atleta") -> Dict[str, Any]:
    """
    Retorna a estrutura base de um novo usuário para o MongoDB.
    Sincronizado com a lógica de Gamificação e Biohacking.
    """
    agora_iso = datetime.now().isoformat()
    
    return {
        # --- 1. IDENTIFICAÇÃO E ACESSO ---
        "email": email,
        "auth_provider": "email", 
        "created_at": agora_iso,
        "updated_at": agora_iso,
        "profile_picture_url": None,
        "plano": "free",          # free, plus, pro
        "cla_atual_id": None,     
        
        # --- 2. PERFIL DO JOGADOR (GAMIFICAÇÃO CORE) ---
        "jogador": {
            "nome": nome,
            "nivel": 1,
            "experiencia": 0,
            "saldo_coins": 0,      # Aura Coins (Moeda de jogo)
            "saldo_cristais": 0,   # Cristais (Moeda Premium)
            "avatar_frame_id": "default",
            "titulo_atual": "Iniciado",
            "missoes_concluidas": 0,
            "metas": {
                "peso_alvo": 70.0,
                "objetivo": "saúde", 
                "frequencia_treino": "3x"
            },
            "preferencias": {
                "horario_treino": "manhã",
                "notificacoes": True
            }
        },

        # --- 3. DADOS FISIOLÓGICOS (MÉTRICAS DE SAÚDE) ---
        "dados_fisiologicos": {
            "ultima_sincronizacao": "",
            "frequencia_cardiaca": {"valor": 0, "repouso": 0},
            "hrv": {"valor": 0, "status": "sem_dados"},
            "sono": {"horas": 0.0, "qualidade": "desconhecida"},
            "energia": {"nivel": 100, "status": "estavel"},
            "passos_hoje": 0,
            "calorias_hoje": 0
        },

        # --- 4. AFINIDADE COM A IA (MESTRE DA AURA) ---
        "afinidade_ia": {
            "score": 50,          
            "nivel": "neutro",    # hostil, neutro, aliado, devoto
            "humor_atual": "focado",
            "ultima_interacao": ""
        },

        # --- 5. HOMEOSTASE (SAÚDE SISTÊMICA) ---
        "homeostase": {
            "score": 50,
            "estado": "Aguardando dados...",
            "componentes": {"corpo": 50, "mente": 50, "energia": 50},
            "ultima_analise": ""
        },

        # --- 6. PROGRESSÃO DIÁRIA ---
        "gamificacao": {
            "xp_acumulado_hoje": 0,
            "missoes_ativas": [],       
            "missoes_concluidas_hoje": [],
            "ultima_geracao_missoes": ""
        },

        # --- 7. INTEGRAÇÕES ---
        "integracoes": {
            "strava": {
                "conectado": False,
                "atleta_id": None,
                "tokens": {} 
            },
            "apple_health": {"conectado": False},
            "garmin": {"conectado": False}
        },
        
        # --- 8. SISTEMA ---
        "configuracoes_sistema": {
            "onboarding_completo": False,
            "versao_schema": "2.0"
        }
    }

def obter_schema_padrao_global() -> Dict[str, Any]:
    """Estrutura da Memória Global (Analytics e Cache de Ranking)."""
    return {
        "_id": "global_state", 
        "sistema": {
            "versao_api": "2.0.1",
            "status": "online",
            "manutencao": False
        },
        "analytics": {
            "total_usuarios": 0,
            "treinos_processados": 0,
            "mensagens_trocadas": 0
        },
        "ranking_global_cache": {
            "top_100": [],
            "ultima_atualizacao": ""
        },
        "ultima_atualizacao": datetime.now().isoformat()
    }

def obter_schema_padrao_produto() -> Dict[str, Any]:
    """Define a estrutura de um item na loja do Aura."""
    return {
        "id": "",
        "nome": "",
        "marca": "",
        "preco_cheio": 0.0,
        "desconto_percentual": 0,
        "preco_final": 0.0,
        "custo_aura_coins": 0,
        "cashback_cristais": 0,
        "nivel_minimo": 1,
        "imagem_url": "",
        "categoria": "suplementos",
        "estoque": True
    }