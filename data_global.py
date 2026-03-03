import logging
from datetime import datetime
from typing import Dict, Any

# Importações da Nova Arquitetura
# Certifique-se que data_manager.py exporta 'mongo_db'
from data_manager import mongo_db
from schema import obter_schema_padrao_global

# Configuração de Logs
logger = logging.getLogger("AURA_DATA_GLOBAL")

# Constantes do Banco (Coleção dedicada a configurações do sistema)
COLECAO_CONFIGS = "configs"
ID_GLOBAL = "global_state"

# ==============================================================
# 🌍 GERENCIADOR DE ESTADO GLOBAL (SINGLETON)
# ==============================================================

def carregar_memoria_global() -> Dict[str, Any]:
    """
    Busca o documento único de configuração global no MongoDB.
    Se não existir, cria um novo baseado no Schema 2.0.
    """
    if mongo_db is None:
        logger.error("❌ MongoDB não inicializado em data_global.")
        return obter_schema_padrao_global()

    try:
        colecao = mongo_db[COLECAO_CONFIGS]
        doc = colecao.find_one({"_id": ID_GLOBAL})
        
        if not doc:
            logger.warning("🌍 Estado Global não encontrado. Criando novo seed...")
            novo_global = obter_schema_padrao_global()
            novo_global["_id"] = ID_GLOBAL
            colecao.insert_one(novo_global)
            return novo_global
            
        return doc
    except Exception as e:
        logger.error(f"❌ Erro ao carregar global: {e}")
        return obter_schema_padrao_global()

def salvar_memoria_global(dados: Dict[str, Any]) -> bool:
    """
    Atualiza o documento global de forma segura.
    """
    if mongo_db is None: return False
    
    try:
        # Usamos ISO format para padronizar datas no MongoDB
        dados["ultima_atualizacao"] = datetime.now().isoformat()
        
        # Proteção: O _id do MongoDB é imutável, removemos antes do $set
        dados_salvar = dados.copy()
        if "_id" in dados_salvar:
            del dados_salvar["_id"]

        mongo_db[COLECAO_CONFIGS].update_one(
            {"_id": ID_GLOBAL},
            {"$set": dados_salvar},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"❌ Erro ao salvar global: {e}")
        return False

# ==============================================================
# 📊 ANALYTICS & RANKING (ALTA PERFORMANCE)
# ==============================================================

def registrar_interacao_global(sentimento: str = "neutro") -> bool:
    """
    Incrementa os contadores de uso do sistema sem expor dados de usuários.
    """
    if mongo_db is None: return False

    try:
        # Incremento atômico: Essencial para o ambiente multijogador do Aura
        mongo_db[COLECAO_CONFIGS].update_one(
            {"_id": ID_GLOBAL},
            {
                "$inc": {
                    "analytics.mensagens_trocadas": 1
                },
                "$set": {"ultima_atualizacao": datetime.now().isoformat()}
            }
        )
        return True
    except Exception as e:
        logger.error(f"⚠️ Erro ao registrar analytics: {e}")
        return False

def atualizar_cache_ranking(lista_ranking: list) -> bool:
    """
    Salva o Top 100 calculado para que o app carregue o Ranking instantaneamente.
    """
    if mongo_db is None: return False
    
    try:
        mongo_db[COLECAO_CONFIGS].update_one(
            {"_id": ID_GLOBAL},
            {
                "$set": {
                    "ranking_global_cache.top_100": lista_ranking,
                    "ranking_global_cache.ultima_atualizacao": datetime.now().isoformat()
                }
            }
        )
        logger.info(f"🏆 Cache de Ranking Global atualizado com {len(lista_ranking)} jogadores.")
        return True
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar cache ranking: {e}")
        return False