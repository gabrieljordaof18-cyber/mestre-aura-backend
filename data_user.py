import logging
from typing import Dict, Any, Optional
from datetime import datetime
from bson.objectid import ObjectId # Importação vital para converter strings de ID

# Importações do Data Manager (MongoDB)
# [AURA FIX] Garantindo que as funções de banco utilizem a coleção 'usuarios' correta
from data_manager import buscar_usuario_por_id, atualizar_usuario
from schema import obter_schema_padrao_usuario

# Configuração de Logs
logger = logging.getLogger("AURA_DATA_USER")

# ==============================================================
# 👤 CAMADA DE SERVIÇO DO USUÁRIO (LÓGICA DE MEMÓRIA)
# ==============================================================

def carregar_memoria(user_id: str) -> Dict[str, Any]:
    """
    Carrega o perfil completo do usuário pelo ID do MongoDB.
    Garante que o retorno seja um dicionário compatível com o Schema 3.1.0 (App Store Ready).
    """
    if not user_id:
        logger.warning("⚠️ Tentativa de carregar memória sem user_id.")
        return {}

    # [AURA FIX] Limpeza rigorosa de strings para evitar erros no Render/Atlas
    clean_user_id = str(user_id).strip().replace('"', '').replace("'", "")

    try:
        # Tenta carregar o usuário via Data Manager (Coleção: usuarios)
        usuario = buscar_usuario_por_id(clean_user_id)
        
        if usuario:
            # [AURA FIX] Redundância: garante que o _id seja string para o Frontend
            usuario["_id"] = str(usuario["_id"])
            
            # [AURA ROBUST] Inicialização de campos vitais para o novo fluxo de IA Híbrida
            if "xp_total" not in usuario: usuario["xp_total"] = 0
            if "moedas" not in usuario: usuario["moedas"] = usuario["xp_total"]
            if "saldo_cristais" not in usuario: usuario["saldo_cristais"] = 0
            if "nivel" not in usuario: usuario["nivel"] = 1
            if "nome" not in usuario: usuario["nome"] = "Atleta"
            
            # [AURA FIX] Campos essenciais para a nova tela de Editar Perfil e Onboarding
            if "esportes_favoritos" not in usuario: usuario["esportes_favoritos"] = ["Musculação"]
            if "idade" not in usuario: usuario["idade"] = 25
            if "tipo_perfil" not in usuario: usuario["tipo_perfil"] = "atleta"
            
            # [AURA NATIVE READY] Blindagem de campos de Assinatura e Autenticação
            # Essencial para evitar KeyError no rotas_api.py ao lidar com usuários antigos
            if "plano" not in usuario: 
                usuario["plano"] = "free"
            if "status_assinatura" not in usuario: 
                usuario["status_assinatura"] = "inativo"
            if "data_vencimento" not in usuario: 
                usuario["data_vencimento"] = ""
            if "provedor_auth" not in usuario: 
                usuario["provedor_auth"] = "email"

            # Garantia de estrutura para o rastreio de Planos IA
            if "planos" not in usuario:
                usuario["planos"] = {
                    "treino_ativo": False,
                    "dieta_ativa": False,
                    "ultima_atualizacao_ia": datetime.now().isoformat()
                }
            # Campos de ofensiva (streak)
            if "ofensiva_atual" not in usuario:
                usuario["ofensiva_atual"] = 0
            if "ultima_missao_data" not in usuario:
                usuario["ultima_missao_data"] = ""
            if "seguro_expira_em" not in usuario:
                usuario["seguro_expira_em"] = ""
            
            return usuario
        else:
            logger.error(f"❌ Usuário {clean_user_id} não encontrado no banco Atlas.")
            return {}
            
    except Exception as e:
        logger.error(f"❌ Erro ao processar busca de usuário {clean_user_id}: {e}")
        return {}

def salvar_memoria(user_id: str, dados: Dict[str, Any]) -> bool:
    """
    Salva ou atualiza os dados do perfil do jogador no MongoDB.
    Protege contra a imutabilidade do campo _id e mantém integridade financeira.
    """
    if not user_id or not dados:
        logger.warning(f"⚠️ Falha ao salvar: dados ou user_id ausentes.")
        return False

    try:
        clean_user_id = str(user_id).strip().replace('"', '').replace("'", "")
        
        # Clonamos os dados para não modificar o objeto original em memória
        dados_para_salvar = dados.copy()
        
        # Proteção Crítica: O MongoDB proíbe atualizar o campo _id
        if "_id" in dados_para_salvar:
            del dados_para_salvar["_id"]

        # XP é histórico fixo (nunca decresce). Moedas é saldo gastável independente.
        # A sincronização 1:1 foi removida — use gastar_moedas() para descontar Moedas.

        # Adiciona carimbo de tempo da última modificação
        dados_para_salvar["updated_at"] = datetime.now().isoformat()

        # Executa a atualização via Data Manager
        return atualizar_usuario(clean_user_id, dados_para_salvar)
        
    except Exception as e:
        logger.error(f"❌ Erro crítico ao salvar memória do usuário {user_id}: {e}")
        return False

# ==============================================================
# 🛠️ FUNÇÕES DE UTILIDADE E BIO-STATUS
# ==============================================================

def redefinir_metas_usuario(user_id: str) -> bool:
    """
    Reseta apenas as metas e preferências do usuário para os valores padrão.
    Útil para o reset de ciclo ou mudança drástica de objetivo.
    """
    logger.info(f"🔄 Redefinindo biometria e metas do usuário {user_id}...")
    
    memoria = carregar_memoria(user_id)
    if not memoria: 
        return False

    # Template limpo baseado no Schema 3.1.0
    padrao = obter_schema_padrao_usuario(
        email=memoria.get("email", ""), 
        nome=memoria.get("nome", "Atleta")
    )
    
    # Atualiza especificamente os blocos biográficos sem apagar os saldos financeiros
    atualizacao = {
        "objetivo": "Performance Máxima",
        "idade": 25,
        "esportes_favoritos": ["Musculação"],
        "planos": {
            "treino_ativo": False,
            "dieta_ativa": False,
            "ultima_atualizacao_ia": datetime.now().isoformat()
        },
        "updated_at": datetime.now().isoformat()
    }
    
    return salvar_memoria(user_id, atualizacao)

def obter_status_fisiologico(user_id: str) -> Dict[str, Any]:
    """
    Retorna exclusivamente o bloco de dados fisiológicos para o Dashboard/Chat.
    """
    memoria = carregar_memoria(user_id)
    # [AURA FIX] Campo 'status_atual' mapeado diretamente do Atlas
    return memoria.get("status_atual", {
        "fadiga": 0,
        "recuperacao": 100,
        "prontidao": 100,
        "estado_bio": "Sincronizando..."
    })

def atualizar_preferencia_esportiva(user_id: str, esportes: list) -> bool:
    """
    Atualiza a lista de esportes favoritos para refinar a geração de treinos híbridos.
    """
    if not isinstance(esportes, list): return False
    return salvar_memoria(user_id, {"esportes_favoritos": esportes})


# ==============================================================
# 💰 ECONOMIA NATIVA — XP vs MOEDAS
# ==============================================================
# XP  → Histórico cumulativo de progressão. Nunca diminui.
#         Gerenciado exclusivamente por logic_gamificacao.aplicar_xp().
# Moedas → Saldo gastável. Inicia igual ao XP mas pode ser debitado
#           quando o usuário compra itens no Marketplace.

def gastar_moedas(user_id: str, quantidade: int) -> dict:
    """
    Debita Moedas do saldo do usuário.
    Retorna {'sucesso': True, 'saldo_novo': N} ou {'sucesso': False, 'erro': '...'}.
    XP não é afetado — apenas o saldo de Moedas é reduzido.
    """
    if quantidade <= 0:
        return {"sucesso": False, "erro": "Quantidade deve ser positiva"}

    memoria = carregar_memoria(user_id)
    if not memoria:
        return {"sucesso": False, "erro": "Usuário não encontrado"}

    saldo_atual = int(memoria.get("moedas", 0))

    if saldo_atual < quantidade:
        return {
            "sucesso": False,
            "erro": f"Saldo insuficiente. Você tem {saldo_atual} Moedas."
        }

    novo_saldo = saldo_atual - quantidade
    sucesso = salvar_memoria(user_id, {"moedas": novo_saldo})

    if sucesso:
        logger.info(f"💸 {quantidade} Moedas debitadas de {user_id}. Saldo novo: {novo_saldo}")
        return {"sucesso": True, "saldo_novo": novo_saldo}
    else:
        return {"sucesso": False, "erro": "Falha ao salvar débito de Moedas"}