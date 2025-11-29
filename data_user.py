import logging
from typing import Dict, Any
from data_manager import carregar_json, salvar_json
from schema import obter_schema_padrao_usuario

# Configuração de Logs
logger = logging.getLogger("AURA_DATA_USER")

# Caminho fixo da memória local
CAMINHO_MEMORIA = "memoria.json"

def carregar_memoria() -> Dict[str, Any]:
    """
    Carrega perfil do jogador usando o Guardião e o Schema.
    Retorna sempre um dicionário válido.
    """
    padrao = obter_schema_padrao_usuario()
    return carregar_json(CAMINHO_MEMORIA, schema_padrao=padrao)

def salvar_memoria(dados: Dict[str, Any]) -> bool:
    """
    Salva perfil do jogador de forma segura.
    """
    try:
        resultado = salvar_json(CAMINHO_MEMORIA, dados)
        return resultado
    except Exception as e:
        logger.error(f"❌ Erro crítico ao salvar memória do usuário: {e}")
        return False

# --- Funções Utilitárias ---

def redefinir_metas_usuario() -> bool:
    """Reseta as metas do usuário para o padrão do schema."""
    logger.info("🔄 Redefinindo metas do usuário para o padrão.")
    memoria = carregar_memoria()
    padrao = obter_schema_padrao_usuario()
    
    # Atualiza apenas a chave de metas
    if "jogador" in memoria and "metas" in padrao["jogador"]:
        memoria["jogador"]["metas"] = padrao["jogador"]["metas"]
        return salvar_memoria(memoria)
    return False

def obter_status_fisiologico() -> Dict[str, Any]:
    """Retorna apenas o bloco de dados fisiológicos."""
    memoria = carregar_memoria()
    return memoria.get("dados_fisiologicos", {})