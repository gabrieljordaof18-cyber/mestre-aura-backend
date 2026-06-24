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

        # --- [AURA NEW] PERFIL DE SAÚDE (persistente, único por usuário, nunca apagado) ---
        # peso_kg/altura_cm também existem soltos na raiz do doc por compatibilidade com
        # EditarPerfil.jsx — toda escrita nos dois lugares é sincronizada (ver rotas_api.py).
        # Os 4 campos abaixo são subdocumentos com valor + fonte + sincronizado_em para
        # que a IA saiba distinguir dado automático (Apple Health) de dado manual.
        "perfil_saude": {
            "peso_kg":            None,
            "altura_cm":          None,
            "percentual_gordura": None,
            "atualizado_em":      agora_iso,
            "fc_repouso":      {"valor": None, "fonte": None, "sincronizado_em": None},
            "passos_diarios":  {"valor": None, "fonte": None, "sincronizado_em": None},
            "calorias_ativas": {"valor": None, "fonte": None, "sincronizado_em": None},
            "sono_horas":      {"valor": None, "fonte": None, "sincronizado_em": None},
        },

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
        # --- [AURA NEW] OFENSIVA (STREAKS) ---
        "ofensiva_atual": 0,
        "ultima_missao_data": "",
        "seguro_expira_em": "",

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

# ==============================================================
# 🏋️ SCHEMAS DE PERFORMANCE (Marketplace de Profissionais)
# ==============================================================

def obter_schema_padrao_profissional(user_id: str = "") -> Dict[str, Any]:
    """
    Estrutura de perfil profissional (personal, nutricionista, médico…).
    Profissional cadastrado recebe 3 meses de período gratuito.
    Após isso paga R$49,90/mês. Verificação de credenciais custa R$99,90.
    """
    from datetime import timedelta
    agora = datetime.now()
    plano_expira = (agora + timedelta(days=90)).isoformat()
    return {
        "user_id":             user_id,
        "tipo_profissional":   "personal",        # personal|nutricionista|medico|fisioterapeuta|coach|nutrologo|endocrino
        "bio":                 "",
        "especialidades":      [],
        "foto_perfil_url":     "",
        "cref_crn_crm":        "",
        "status_verificacao":  "pendente",        # pendente|verificado|rejeitado
        "verificacao_paga":    False,
        "plano_ativo":         True,
        "trial_ativo":         True,   # False quando primeira IAP aura_profissional_mensal é confirmada
        "plano_inicio":        agora.isoformat(),
        "plano_expira":        plano_expira,
        "total_alunos":        0,
        "avaliacao_media":     0.0,
        "total_avaliacoes":    0,
        "criado_em":           agora.isoformat(),
        "updated_at":          agora.isoformat(),
    }


def obter_schema_padrao_desafio(profissional_id: str = "") -> Dict[str, Any]:
    """
    Estrutura de desafio pago criado por um profissional.
    AURA fica com 20%; profissional recebe 80%.
    """
    agora = datetime.now().isoformat()
    return {
        "profissional_id":    profissional_id,
        "titulo":             "",
        "descricao":          "",
        "tipo":               "emagrecimento",    # emagrecimento|hipertrofia|saude|performance|reabilitacao
        "duracao_dias":       30,
        "preco":              0.0,
        "vagas_total":        0,                  # 0 = ilimitado
        "vagas_ocupadas":     0,
        "data_inicio":        "",
        "status":             "rascunho",         # ativo|encerrado|rascunho
        "imagem_capa_url":    "",
        "o_que_inclui":       [],
        "protocolo": {
            "treinos":            [],
            "alimentacao":        "",
            "suplementacao":      [],
            "frequencia_semanal": 3,
        },
        "total_inscritos":    0,
        "avaliacao_media":    0.0,
        "total_avaliacoes":   0,
        "criado_em":          agora,
        "updated_at":         agora,
        "aura_comissao_pct":  20,
        "profissional_pct":   80,
    }


def obter_schema_padrao_inscricao(desafio_id: str = "", user_id: str = "", profissional_id: str = "") -> Dict[str, Any]:
    """Inscrição de usuário em um desafio pago."""
    agora = datetime.now().isoformat()
    return {
        "desafio_id":          desafio_id,
        "user_id":             user_id,
        "profissional_id":     profissional_id,
        "asaas_id":            "",
        "status_pagamento":    "PENDING",         # PENDING|PAGO|CANCELADO
        "status_desafio":      "em_andamento",    # em_andamento|concluido|abandonado
        "data_inscricao":      agora,
        "data_inicio":         "",
        "progresso": {
            "dias_completos":  0,
            "percentual":      0.0,
            "ultimo_registro": "",
        },
        "avaliacao":           None,
        "comentario":          "",
        "valor_total":         0.0,
        "valor_aura":          0.0,
        "valor_profissional":  0.0,
        # --- [AURA NEW] Consentimento de acesso a dados de saúde ---
        # Aceito explicitamente na tela de pagamento antes de inscrever_desafio().
        # Vira a base do grant em "grants_saude" quando o pagamento é confirmado.
        "consentimento": {
            "aceito":       False,
            "versao_termo": "",
            "aceito_em":    "",
            "escopo":       [],
        },
    }


def obter_schema_padrao_mensagem_desafio(desafio_id: str = "", remetente_id: str = "") -> Dict[str, Any]:
    """Mensagem no chat de um desafio (grupo ou privado)."""
    return {
        "canal":          "grupo",    # "grupo" | "privado"
        "desafio_id":     desafio_id,
        "dupla_id":       None,       # apenas para canal="privado": "<min_id>_<max_id>"
        "remetente_id":   remetente_id,
        "remetente_nome": "",
        "remetente_tipo": "aluno",    # "profissional" | "aluno"
        "texto":          "",
        "lida":           False,
        "enviada_em":     datetime.now().isoformat(),
    }


def obter_schema_padrao_grant_saude(profissional_id: str = "", aluno_id: str = "",
                                     desafio_id: str = "", inscricao_id: str = "") -> Dict[str, Any]:
    """
    Grant de acesso temporário do profissional aos dados de saúde de um aluno.
    Criado quando o pagamento do desafio é confirmado (webhook Asaas); expira
    junto com o desafio. Nunca é deletado — apenas marcado expirado/revogado,
    e o perfil de saúde do aluno permanece intacto.
    """
    agora = datetime.now().isoformat()
    return {
        "profissional_id": profissional_id,
        "aluno_id":        aluno_id,
        "desafio_id":      desafio_id,
        "inscricao_id":    inscricao_id,
        "data_concessao":  agora,
        "data_expiracao":  "",          # data_inicio do desafio + duracao_dias, congelado na criação
        "status":          "ativo",     # ativo|expirado|revogado
        "consentimento": {
            "aceito":       False,
            "versao_termo": "",
            "aceito_em":    "",
            "escopo":       [],
        },
        "criado_em":     agora,
        "atualizado_em": agora,
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