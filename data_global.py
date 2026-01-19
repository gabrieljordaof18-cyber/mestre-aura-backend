import logging
from datetime import datetime
from typing import Dict, Any

# Importações da Nova Arquitetura
from data_manager import mongo_db
from schema import obter_schema_padrao_global

# Configuração de Logs
logger = logging.getLogger("AURA_DATA_GLOBAL")

# Constantes do Banco
COLECAO_CONFIGS = "configs"
ID_GLOBAL = "global_state"

# ==============================================================
# 🌍 GERENCIADOR DE ESTADO GLOBAL (SINGLETON)
# ==============================================================

def carregar_memoria_global() -> Dict[str, Any]:
    """
    Busca o documento único de configuração global no MongoDB.
    Se não existir, cria um novo padrão.
    """
    if mongo_db is None:
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
    Atualiza o documento global.
    """
    if mongo_db is None: return False
    
    try:
        dados["ultima_atualizacao"] = str(datetime.now())
        # Proteção para não tentar alterar o _id imutável
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
# 📊 ANALYTICS & MONITORAMENTO (SEM DADOS SENSÍVEIS)
# ==============================================================

def registrar_interacao_global(sentimento: str = "neutro") -> bool:
    """
    Incrementa os contadores de uso do sistema.
    NÃO SALVA MAIS O TEXTO DA MENSAGEM (Privacidade + Performance).
    """
    if mongo_db is None: return False

    try:
        # Mapeamento para o campo correto no Schema
        campo_stats = "neutras"
        if sentimento == "positivo": campo_stats = "positivas"
        elif sentimento == "negativo": campo_stats = "negativas"

        # Operação Atômica ($inc) - Seguro para concorrência
        mongo_db[COLECAO_CONFIGS].update_one(
            {"_id": ID_GLOBAL},
            {
                "$inc": {
                    f"analytics.mensagens_trocadas": 1,
                    # Se você quiser manter contagem por sentimento no futuro:
                    # f"analytics.sentimentos.{campo_stats}": 1 
                },
                "$set": {"ultima_atualizacao": str(datetime.now())}
            }
        )
        return True
    except Exception as e:
        logger.error(f"⚠️ Erro ao registrar analytics: {e}")
        return False

def atualizar_cache_ranking(lista_ranking: list):
    """
    Salva o Top 100 calculado no documento global para acesso rápido.
    Evita ter que calcular o ranking toda vez que alguém abre o app.
    """
    if mongo_db is None: return False
    
    try:
        mongo_db[COLECAO_CONFIGS].update_one(
            {"_id": ID_GLOBAL},
            {
                "$set": {
                    "ranking_global_cache.top_100": lista_ranking,
                    "ranking_global_cache.ultima_atualizacao": str(datetime.now())
                }
            }
        )
        logger.info("🏆 Cache de Ranking Global atualizado.")
        return True
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar cache ranking: {e}")
        return False