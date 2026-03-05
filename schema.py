from datetime import datetime
from typing import Dict, Any

# ==============================================================
# 📘 DICIONÁRIO OFICIAL DE DADOS (SCHEMA 2.0 - AURA PERFORMANCE)
# ==============================================================

def obter_schema_padrao_usuario(email: str = "", nome: str = "Atleta") -> Dict[str, Any]:
    """
    Retorna a estrutura base de um novo usuário para o MongoDB.
    [AURA FIX] Sincronizado para a Nova Economia:
    - Aura Coins (moedas) = XP (1:1)
    - Cristais (saldo_cristais) = XP / 10
    """
    agora_iso = datetime.now().isoformat()
    
    return {
        # --- 1. IDENTIFICAÇÃO E ACESSO ---
        "nome": nome,
        "email": email,
        "auth_provider": "email", 
        "created_at": agora_iso,
        "updated_at": agora_iso,
        "foto_perfil": "", 
        "plano": "free",
        "objetivo": "Performance Máxima", 
        
        # --- 2. PROGRESSÃO (CAMPOS NA RAIZ PARA SINCRONIZAÇÃO ATLAS) ---
        # [AURA FIX] Estrutura unificada para evitar moedas fantasmas
        "nivel": 1,
        "xp_total": 0,         # XP Acumulado
        "moedas": 0,           # Aura Coins Oficiais (Sincronizado 1:1 com XP)
        "saldo_cristais": 0,   # Moeda Premium (Sincronizado 10:1 com XP)
        "titulo_atual": "Iniciado",
        
        # --- 3. STATUS ATUAL (BIO-MÉTRICAS) ---
        "status_atual": {
            "ultima_sincronizacao": agora_iso,
            "fadiga": 0,
            "recuperacao": 100,
            "prontidao": 100,
            "passos_hoje": 0,
            "fc_repouso": 0,
            "hrv_valor": 0,
            "sono_horas": 0.0
        },

        # --- 4. HOMEOSTASE (SAÚDE SISTÊMICA) ---
        "homeostase": {
            "score": 100,
            "estado": "Plena Harmonia 🌟",
            "componentes": {"corpo": 100, "mente": 100, "energy": 100},
            "ultima_analise": agora_iso
        },

        # --- 5. GAMIFICAÇÃO ---
        "gamificacao": {
            "missoes_ativas": [],       
            "ultima_geracao_missoes": agora_iso
        },

        # --- 6. INTEGRAÇÕES ---
        "integracoes": {
            "strava": {
                "conectado": False,
                "atleta_id": None,
                "tokens": {} 
            },
            "apple_health": {"conectado": False}
        },
        
        # --- 7. SISTEMA ---
        "configuracoes_sistema": {
            "onboarding_completo": False,
            "versao_schema": "2.0.2" # Incremento de versão para controle de deploy
        }
    }

def obter_schema_padrao_global() -> Dict[str, Any]:
    """Estrutura da Memória Global (Analytics e Cache de Ranking)."""
    return {
        "_id": "global_state", 
        "sistema": {
            "versao_api": "2.0.2",
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
        "preco_final": 0.0,
        "custo_moedas": 0, # [AURA FIX] Sincronizado com o campo 'moedas' raiz
        "nivel_minimo": 1,
        "imagem_url": "",
        "categoria": "suplementos",
        "estoque": True
    }