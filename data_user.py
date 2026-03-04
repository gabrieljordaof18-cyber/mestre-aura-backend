import logging
from typing import Dict, Any, Optional
from datetime import datetime
from bson.objectid import ObjectId # Importação vital para converter strings de ID

# Importações do Data Manager (MongoDB)
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
    Garante que o retorno seja um dicionário compatível com o Schema 2.0.
    """
    if not user_id:
        logger.warning("⚠️ Tentativa de carregar memória sem user_id.")
        return {}

    # [AURA FIX] Limpeza de espaços em branco que podem vir do token/frontend
    clean_user_id = str(user_id).strip()

    try:
        # Tenta carregar o usuário via Data Manager
        usuario = buscar_usuario_por_id(clean_user_id)
        
        if usuario:
            # A conversão de _id para string garante compatibilidade com JSON/Frontend
            usuario["_id"] = str(usuario["_id"])
            return usuario
        else:
            logger.error(f"❌ Usuário {clean_user_id} não encontrado no banco.")
            return {}
            
    except Exception as e:
        logger.error(f"❌ Erro ao processar busca de usuário {clean_user_id}: {e}")
        return {}

def salvar_memoria(user_id: str, dados: Dict[str, Any]) -> bool:
    """
    Salva ou atualiza os dados do perfil do jogador no MongoDB.
    Protege contra a imutabilidade do campo _id.
    """
    if not user_id or not dados:
        logger.warning(f"⚠️ Falha ao salvar: dados ou user_id ausentes para {user_id}")
        return False

    try:
        # [AURA FIX] Garantir ID limpo para atualização
        clean_user_id = str(user_id).strip()
        
        # Clonamos os dados para não modificar o objeto original em memória
        dados_para_salvar = dados.copy()
        
        # Proteção Crítica: O MongoDB proíbe atualizar o campo _id
        if "_id" in dados_para_salvar:
            del dados_para_salvar["_id"]

        # Adiciona carimbo de tempo da última modificação
        dados_para_salvar["updated_at"] = datetime.now().isoformat()

        # Executa a atualização via Data Manager
        return atualizar_usuario(clean_user_id, dados_para_salvar)
        
    except Exception as e:
        logger.error(f"❌ Erro crítico ao salvar memória do usuário {user_id}: {e}")
        return False

# ==============================================================
# 🛠️ FUNÇÕES DE UTILIDADE E RESET
# ==============================================================

def redefinir_metas_usuario(user_id: str) -> bool:
    """
    Reseta apenas as metas e preferências do usuário para os valores padrão.
    Útil para quando o usuário deseja recomeçar sua jornada de treino/dieta.
    """
    logger.info(f"🔄 Redefinindo metas do usuário {user_id}...")
    
    memoria = carregar_memoria(user_id)
    if not memoria: 
        return False

    # Obtém um template limpo do Schema 2.0
    # Ajustado para usar campos diretos conforme o seu MongoDB atual
    padrao = obter_schema_padrao_usuario(
        email=memoria.get("email", ""), 
        nome=memoria.get("nome", "Atleta")
    )
    
    # Atualiza especificamente os blocos de metas e preferências
    atualizacao = {
        "objetivo": "Performance Máxima",
        "bio_performance": padrao.get("bio_performance", {})
    }
    
    return salvar_memoria(user_id, atualizacao)

def obter_status_fisiologico(user_id: str) -> Dict[str, Any]:
    """
    Retorna exclusivamente o bloco de dados fisiológicos (FC, Sono, Energia).
    """
    memoria = carregar_memoria(user_id)
    return memoria.get("status_atual", {}) # Ajustado para o campo correto no seu banco