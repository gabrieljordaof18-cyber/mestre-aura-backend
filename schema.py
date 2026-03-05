from datetime import datetime
from typing import Dict, Any

# ==============================================================
# 📘 DICIONÁRIO OFICIAL DE DADOS (SCHEMA 3.0 - HYBRID ROBUST)
# ==============================================================

def obter_schema_padrao_usuario(email: str = "", nome: str = "Atleta") -> Dict[str, Any]:
    """
    Retorna a estrutura base de um novo usuário para o MongoDB.
    [AURA ROBUST] Sincronizado para Treinos Híbridos e Nova Economia:
    - Aura Coins (moedas) = XP (1:1)
    - Cristais (saldo_cristais) = XP / 10
    """
    agora_iso = datetime.now().isoformat()
    
    return {
        # --- 1. IDENTIFICAÇÃO E PERFIL ---
        "nome": nome,
        "email": email,
        "idade": 25,                    # Vital para cálculos metabólicos da IA
        "tipo_perfil": "atleta",        # atleta ou professor
        "esportes_favoritos": ["Musculação"], # Define a prioridade do treino híbrido
        "auth_provider": "email", 
        "created_at": agora_iso,
        "updated_at": agora_iso,
        "foto_perfil": "", 
        "plano": "free",
        "objetivo": "Performance Máxima", 
        "cla_atual_id": None,           # Âncora para sistema social
        
        # --- 2. PROGRESSÃO E ECONOMIA ---
        "nivel": 1,
        "xp_total": 0,         
        "moedas": 0,           # Sincronizado 1:1 com XP
        "saldo_cristais": 0,   # Sincronizado 10:1 com XP
        "titulo_atual": "Iniciado",
        
        # --- 3. STATUS ATUAL (BIO-SINALIZAÇÃO) ---
        "status_atual": {
            "ultima_sincronizacao": agora_iso,
            "fadiga": 20.0,
            "recuperacao": 100.0,
            "prontidao": 100,
            "passos_hoje": 0,
            "fc_repouso": 0,
            "hrv_valor": 0,
            "sono_horas": 0.0,
            "historico_recente_esportes": [] # Contexto para o Mestre Aura
        },

        # --- 4. HOMEOSTASE (INTELIGÊNCIA DE CARGA) ---
        "homeostase": {
            "score": 100,
            "estado": "Plena Harmonia 🌟",
            "componentes": {"corpo": 100, "mente": 100, "energia": 100},
            "ultima_analise": agora_iso
        },

        # --- 5. PLANOS IA (NOVO) ---
        "planos": {
            "treino_ativo": False,
            "dieta_ativa": False,
            "ultima_atualizacao_ia": agora_iso
        },

        # --- 6. GAMIFICAÇÃO ---
        "gamificacao": {
            "missoes_ativas": [],       
            "ultima_geracao_missoes": agora_iso,
            "estatisticas": {
                "missoes_completadas": 0,
                "total_atividades": 0,
                "dias_seguidos": 0
            }
        },

        # --- 7. INVENTÁRIO (Sincronizado com Mercado) ---
        "inventario": {
            "vouchers": [],
            "itens_consumiveis": [],
            "cupons_ativos": []
        },

        # --- 8. INTEGRAÇÕES ---
        "integracoes": {
            "strava": {
                "conectado": False,
                "atleta_id": None,
                "tokens": {} 
            },
            "apple_health": {"conectado": False}
        },
        
        # --- 9. SISTEMA ---
        "configuracoes_sistema": {
            "onboarding_completo": False,
            "versao_schema": "3.0.0-Hybrid" # Era dos planos robustos
        }
    }

def obter_schema_padrao_global() -> Dict[str, Any]:
    """Estrutura da Memória Global (Analytics de Alta Performance)."""
    return {
        "_id": "global_state", 
        "versao_ia_ativa": "3.0.0-Hybrid",
        "temporada_atual": 1,
        "sistema": {
            "versao_api": "3.0.0",
            "status": "ativa_robust",
            "manutencao": False
        },
        "analytics": {
            "total_usuarios": 0,
            "total_planos_gerados": 0, # Novo
            "total_treinos_realizados": 0, # Novo
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
        "custo_moedas": 0, 
        "nivel_minimo": 1,
        "imagem_url": "",
        "categoria": "destaque",
        "estoque": True
    }