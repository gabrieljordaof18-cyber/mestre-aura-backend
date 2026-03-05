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
    Garante que o retorno seja um dicionário compatível com o Schema 2.0.
    """
    if not user_id:
        logger.warning("⚠️ Tentativa de carregar memória sem user_id.")
        return {}

    # [AURA FIX] Limpeza rigorosa de strings. 
    # O Base44 pode enviar o ID com caracteres de escape ou espaços invisíveis.
    clean_user_id = str(user_id).strip().replace('"', '').replace("'", "")

    try:
        # Tenta carregar o usuário via Data Manager
        usuario = buscar_usuario_por_id(clean_user_id)
        
        if usuario:
            # [AURA FIX] Redundância: garante que o _id seja string para o Frontend
            usuario["_id"] = str(usuario["_id"])
            
            # [AURA FIX] Preenchimento de campos obrigatórios para evitar erro na UI do Base44
            # Se o campo não existe no banco, inicializamos com o valor padrão do Schema
            if "xp_total" not in usuario: usuario["xp_total"] = 0
            if "nivel" not in usuario: usuario["nivel"] = 1
            if "nome" not in usuario: usuario["nome"] = "Atleta"
            
            return usuario
        else:
            logger.error(f"❌ Usuário {clean_user_id} não encontrado no banco (Coleção: usuarios).")
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
        # [AURA FIX] Garantir ID limpo para atualização consistente no Render
        clean_user_id = str(user_id).strip().replace('"', '').replace("'", "")
        
        # Clonamos os dados para não modificar o objeto original em memória
        dados_para_salvar = dados.copy()
        
        # Proteção Crítica: O MongoDB proíbe atualizar o campo _id
        if "_id" in dados_para_salvar:
            del dados_para_salvar["_id"]

        # Adiciona carimbo de tempo da última modificação
        dados_para_salvar["updated_at"] = datetime.now().isoformat()

        # Executa a atualização via Data Manager (que usa a coleção 'usuarios')
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
    
    # [AURA FIX] Atualiza especificamente os blocos que existem no seu documento manual
    atualizacao = {
        "objetivo": "Performance Máxima",
        "bio_performance": padrao.get("bio_performance", {}),
        "xp_total": 0, # Opcional: define se o reset também zera o progresso
        "nivel": 1
    }
    
    return salvar_memoria(user_id, atualizacao)

def obter_status_fisiologico(user_id: str) -> Dict[str, Any]:
    """
    Retorna exclusivamente o bloco de dados fisiológicos (FC, Sono, Energia).
    """
    memoria = carregar_memoria(user_id)
    # [AURA FIX] Ajustado para o campo 'status_atual' que você criou no MongoDB
    return memoria.get("status_atual", {})