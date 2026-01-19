from datetime import datetime
from typing import Dict, Any

# ==============================================================
# 📘 DICIONÁRIO OFICIAL DE DADOS (SCHEMA 2.0 - MONGODB)
# ==============================================================

def obter_schema_padrao_usuario(email: str = "", nome: str = "Atleta") -> Dict[str, Any]:
    """
    Retorna a estrutura base de um novo usuário para o MongoDB.
    Agora sincronizado com o Frontend (Base44).
    """
    return {
        # --- 1. Identificação e Acesso (CRÍTICO PARA FRONTEND) ---
        "email": email,
        "auth_provider": "email", # ou "strava"
        "created_at": str(datetime.now()),
        "updated_at": str(datetime.now()),
        "profile_picture_url": None,
        "plano": "free",          # free, plus, pro
        "cla_atual_id": None,     # ID do Clã se estiver em um
        
        # --- 2. Perfil do Jogador (Gamificação) ---
        "jogador": {
            "nome": nome,
            "nivel": 1,
            "experiencia": 0,
            "saldo_coins": 0,      # Moeda Comum (Aura Coins)
            "saldo_cristais": 0,   # Moeda Premium
            "avatar_frame_id": "default",
            "titulo_atual": "Iniciado",
            "missoes_concluidas": 0,
            # Metas e Preferências
            "metas": {
                "peso_alvo": 70.0,
                "objetivo": "saúde", # hipertrofia, resistencia, saude
                "frequencia_treino": "3x"
            },
            "preferencias": {
                "horario_treino": "manhã",
                "notificacoes": True
            }
        },

        # --- 3. Dados Fisiológicos (Limpo e Unificado) ---
        "dados_fisiologicos": {
            "ultima_sincronizacao": "",
            # Métricas principais (Fonte da verdade)
            "frequencia_cardiaca": {"valor": 0, "repouso": 0},
            "hrv": {"valor": 0, "status": "sem_dados"},
            "sono": {"horas": 0.0, "qualidade": "desconhecida"},
            "energia": {"nivel": 100, "status": "estavel"},
            "passos_hoje": 0,
            "calorias_hoje": 0
        },

        # --- 4. Relacionamento com a IA (Migrado do Global) ---
        "afinidade_ia": {
            "score": 50,          # 0 a 100
            "nivel": "neutro",    # hostil, neutro, aliado, devoto
            "humor_atual": "focado",
            "ultima_interacao": ""
        },

        # --- 5. Saúde Sistêmica (Homeostase) ---
        "homeostase": {
            "score": 50,
            "estado": "Aguardando dados...",
            "componentes": {"corpo": 50, "mente": 50, "energia": 50},
            "ultima_analise": ""
        },

        # --- 6. Sistema de Missões e Gamificação ---
        "gamificacao": {
            "xp_acumulado_hoje": 0,
            "missoes_ativas": [],       # Lista de objetos missão
            "missoes_concluidas_hoje": [],
            "ultima_geracao_missoes": ""
        },

        # --- 7. Integrações e Tokens ---
        "integracoes": {
            "strava": {
                "conectado": False,
                "atleta_id": None,
                "tokens": {} # Access e Refresh tokens ficam aqui
            },
            "apple_health": {"conectado": False},
            "garmin": {"conectado": False}
        },
        
        # --- 8. Configurações Internas ---
        "configuracoes_sistema": {
            "onboarding_completo": False,
            "versao_schema": "2.0"
        }
        
        # NOTA: O campo 'historico' (chat) foi REMOVIDO. 
        # Será salvo na coleção 'chats' para performance.
    }

def obter_schema_padrao_global() -> Dict[str, Any]:
    """
    Estrutura da Memória Global (Apenas Configurações e Analytics).
    Não guarda mais dados pessoais.
    """
    return {
        "_id": "global_state", # ID Fixo para facilitar busca (Singleton)
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
        "ultima_atualizacao": str(datetime.now())
    }

def obter_schema_padrao_produto() -> Dict[str, Any]:
    """Define a estrutura de um item no mercado."""
    return {
        "id": "",
        "nome": "",
        "marca": "",
        "preco_cheio": 0.0,
        "desconto_percentual": 12,
        "preco_final": 0.0,
        "custo_aura_coins": 0,
        "cashback_cristais": 0,
        "nivel_minimo": 1,
        "imagem_url": "",
        "categoria": "suplementos", # suplementos, equipamentos, digital
        "estoque": True
    }