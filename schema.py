from datetime import datetime
from typing import Dict, Any

# ==============================================================
# 📘 DICIONÁRIO OFICIAL DE DADOS (SCHEMA 3.3.0 - NATIVE READY)
# ==============================================================

def obter_schema_padrao_usuario(email: str = "", nome: str = "Atleta") -> Dict[str, Any]:
    """
    Retorna a estrutura base de um novo usuário para o MongoDB.
    [AURA NATIVE] Atualizado para suporte a In-App Purchases e Apple Auth.
    - Aura Coins (moedas) = XP (1:1)
    - Cristais (saldo_cristais) = XP / 10
    """
    agora_iso = datetime.now().isoformat()
    
    return {
        # --- 1. IDENTIFICAÇÃO E PERFIL ---
        "nome": nome,
        "email": email.strip().lower() if email else "",
        "idade": 25,                    
        "tipo_perfil": "atleta",        
        "esportes_favoritos": ["Musculação"], 
        "auth_provider": "email",       # email, apple, google ou strava
        "created_at": agora_iso,
        "updated_at": agora_iso,
        "foto_perfil": "", 
        
        # --- [AURA NEW] ASSINATURA NATIVA ---
        "plano": "free",                # free, plus, pro
        "status_assinatura": "inativo", # ativo, inativo, expirado
        "data_vencimento": "",          # Data ISO da expiração IAP
        "objetivo": "Performance Máxima", 
        "cla_atual_id": None,           
        
        # --- 2. PROGRESSÃO E ECONOMIA ---
        "nivel": 1,
        "xp_total": 0,         
        "moedas": 0,           
        "saldo_cristais": 0,   
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
            "historico_recente_esportes": [] 
        },

        # --- 4. HOMEOSTASE (INTELIGÊNCIA DE CARGA) ---
        "homeostase": {
            "score": 100,
            "estado": "Plena Harmonia 🌟",
            "componentes": {"corpo": 100, "mente": 100, "energia": 100},
            "ultima_analise": agora_iso
        },

        # --- 5. PLANOS IA (Sincronizado com Mestre Aura) ---
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

        # --- 7. INVENTÁRIO ---
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
            "apple_health": {
                "conectado": False,
                "updated_at": agora_iso
            }
        },
        
        # --- 9. SISTEMA ---
        "configuracoes_sistema": {
            "onboarding_completo": False,
            "versao_schema": "3.3.0-Native", # Atualizado para nova arquitetura Apple
            "notificacoes_push": True
        }
    }

def obter_schema_padrao_global() -> Dict[str, Any]:
    """Estrutura da Memória Global (Analytics v3.3.0)."""
    return {
        "_id": "global_state", 
        "versao_ia_ativa": "3.3.0-Native",
        "temporada_atual": 1,
        "sistema": {
            "versao_api": "3.3.0",
            "status": "online",
            "manutencao": False
        },
        "analytics": {
            "total_usuarios": 0,
            "total_planos_gerados": 0, 
            "total_treinos_realizados": 0, 
            "mensagens_trocadas": 0
        },
        "ranking_global_cache": {
            "top_100": [],
            "ultima_atualizacao": ""
        },
        "ultima_atualizacao": datetime.now().isoformat()
    }

def obter_schema_padrao_produto() -> Dict[str, Any]:
    """
    Estrutura de item no Marketplace.
    [AURA LOGISTICS] Sincronizado com Melhor Envio.
    """
    return {
        "id": "",
        "nome": "",
        "marca": "",
        "preco_aura": 0.0,        # Preço oficial de venda
        "preco_original": 0.0,    # Para exibir descontos
        "custo_moedas": 0, 
        "nivel_minimo": 1,
        "imagem_url": "",
        "categoria": "Suplementos",
        "estoque": True,
        # --- CAMPOS DE LOGÍSTICA ---
        "peso_kg": 0.5,           
        "largura_cm": 15,         
        "altura_cm": 10,
        "comprimento_cm": 20,
        "cep_origem": "74000000"  
    }

def obter_schema_padrao_pedido() -> Dict[str, Any]:
    """
    Estrutura de pedido para Marketplace Físico.
    """
    agora_iso = datetime.now().isoformat()
    return {
        "user_id": "",
        "asaas_id": "",           
        "customer_id": "",        
        "status": "PENDING",      
        "valor_produtos": 0.0,
        "valor_frete": 0.0,       
        "valor_total": 0.0,       
        "metodo": "pix",
        "transportadora": "",     
        "servico_logistico": "",  
        "codigo_rastreio": "",
        "endereco_entrega": {
            "cep": "",
            "rua": "",
            "numero": "",
            "bairro": "",
            "cidade": "",
            "estado": ""
        },
        "itens": [],              
        "created_at": agora_iso,
        "updated_at": agora_iso,
        "versao_os": "3.3.0-Native"
    }