import logging
from typing import Dict, Any, Optional

# Importações do novo Data Manager (MongoDB)
from data_manager import buscar_usuario_por_id, atualizar_usuario
from schema import obter_schema_padrao_usuario

# Configuração de Logs
logger = logging.getLogger("AURA_DATA_USER")

# ==============================================================
# 👤 CAMADA DE SERVIÇO DO USUÁRIO
# ==============================================================

def carregar_memoria(user_id: str) -> Dict[str, Any]:
    """
    Carrega o perfil completo do usuário pelo ID do MongoDB.
    """
    if not user_id:
        logger.warning("⚠️ Tentativa de carregar memória sem user_id.")
        return {}

    usuario = buscar_usuario_por_id(user_id)
    
    if usuario:
        # Converte _id para string para facilitar manipulação no Python/Frontend
        usuario["_id"] = str(usuario["_id"])
        return usuario
    else:
        logger.error(f"❌ Usuário {user_id} não encontrado no banco.")
        return {}

def salvar_memoria(user_id: str, dados: Dict[str, Any]) -> bool:
    """
    Salva/Atualiza os dados do perfil do jogador no MongoDB.
    """
    if not user_id:
        return False

    try:
        # Proteção: Remove _id dos dados para evitar erro de imutabilidade do Mongo
        dados_para_salvar = dados.copy()
        if "_id" in dados_para_salvar:
            del dados_para_salvar["_id"]

        # Chama o Data Manager para fazer o update
        # O MongoDB é inteligente: se passarmos o objeto inteiro, ele atualiza os campos.
        sucesso = atualizar_usuario(user_id, dados_para_salvar)
        return sucesso
        
    except Exception as e:
        logger.error(f"❌ Erro crítico ao salvar memória do usuário {user_id}: {e}")
        return False

# ==============================================================
# 🛠️ FUNÇÕES UTILITÁRIAS
# ==============================================================

def redefinir_metas_usuario(user_id: str) -> bool:
    """
    Reseta as metas do usuário específico para o padrão do schema.
    """
    logger.info(f"🔄 Redefinindo metas do usuário {user_id}...")
    
    memoria = carregar_memoria(user_id)
    if not memoria: return False

    padrao = obter_schema_padrao_usuario()
    
    # Atualiza apenas a chave de metas e preferências
    if "jogador" in memoria:
        memoria["jogador"]["metas"] = padrao["jogador"]["metas"]
        memoria["jogador"]["preferencias"] = padrao["jogador"]["preferencias"]
        return salvar_memoria(user_id, memoria)
    
    return False

def obter_status_fisiologico(user_id: str) -> Dict[str, Any]:
    """
    Retorna apenas o bloco de dados fisiológicos para sensores/frontend.
    """
    memoria = carregar_memoria(user_id)
    return memoria.get("dados_fisiologicos", {})