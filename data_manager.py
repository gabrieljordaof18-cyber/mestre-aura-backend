import os
import logging
from datetime import datetime
from pymongo import MongoClient, DESCENDING
from bson.objectid import ObjectId
from dotenv import load_dotenv

# Importação do Schema para garantir consistência
from schema import obter_schema_padrao_usuario

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AURA_DATA")

load_dotenv()

# ==============================================================
# 🔌 CONEXÃO COM O MONGODB ATLAS (SINGLETON)
# ==============================================================

MONGO_URI = os.getenv("MONGODB_URI")
mongo_client = None
mongo_db = None

try:
    if not MONGO_URI:
        raise ValueError("MONGODB_URI não encontrada no .env")

    # Adicionado retryWrites para maior estabilidade no Render/Nuvem
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, retryWrites=True)
    mongo_client.server_info()
    
    mongo_db = mongo_client["mestre_aura_db"]
    logger.info("✅ [DATA] Conectado ao MongoDB Atlas com sucesso.")
    
except Exception as e:
    logger.critical(f"❌ [DATA] ERRO CRÍTICO DE CONEXÃO: {e}")
    mongo_client = None
    mongo_db = None

# ==============================================================
# 👤 GERENCIAMENTO DE USUÁRIOS
# ==============================================================

def buscar_usuario_por_id(user_id: str):
    if mongo_db is None: return None
    try:
        # [AURA FIX] Garantir que o ID seja limpo e convertido para ObjectId
        clean_id = str(user_id).strip()
        # Buscamos na coleção correta (ajustado para 'usuarios' conforme sua estrutura)
        doc = mongo_db["usuarios"].find_one({"_id": ObjectId(clean_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc
    except Exception as e:
        logger.error(f"Erro ao buscar usuário ID {user_id}: {e}")
        return None

def buscar_usuario_por_email(email: str):
    if mongo_db is None: return None
    doc = mongo_db["usuarios"].find_one({"email": email})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc

def criar_novo_usuario(email: str, nome: str, auth_provider="email"):
    if mongo_db is None: return None
    
    novo_user = obter_schema_padrao_usuario(email=email, nome=nome)
    novo_user["auth_provider"] = auth_provider
    novo_user["created_at"] = datetime.now().isoformat()
    
    try:
        resultado = mongo_db["usuarios"].insert_one(novo_user)
        novo_user["_id"] = str(resultado.inserted_id)
        return novo_user
    except Exception as e:
        logger.error(f"Erro ao criar usuário: {e}")
        return None

def atualizar_usuario(user_id: str, dados_atualizacao: dict):
    if mongo_db is None: return False
    try:
        clean_id = str(user_id).strip()
        if "_id" in dados_atualizacao:
            del dados_atualizacao["_id"]
            
        dados_atualizacao["updated_at"] = datetime.now().isoformat()
        
        mongo_db["usuarios"].update_one(
            {"_id": ObjectId(clean_id)},
            {"$set": dados_atualizacao}
        )
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar usuário {user_id}: {e}")
        return False

# ==============================================================
# 🏃 INTEGRAÇÃO STRAVA
# ==============================================================

def salvar_conexao_strava(dados_atleta: dict, tokens: dict):
    if mongo_db is None: return False
    strava_id = str(dados_atleta.get('id'))
    email_strava = dados_atleta.get('email')
    nome = dados_atleta.get('firstname', 'Atleta')
    foto = dados_atleta.get('profile', '')

    try:
        colecao_users = mongo_db["usuarios"]
        usuario_existente = colecao_users.find_one({"integracoes.strava.atleta_id": strava_id})

        if usuario_existente:
            atualizar_usuario(str(usuario_existente["_id"]), {
                "integracoes.strava.conectado": True,
                "integracoes.strava.tokens": tokens,
                "foto_perfil": foto # Ajustado para bater com seu novo schema
            })
            return True
        else:
            if email_strava:
                user_por_email = colecao_users.find_one({"email": email_strava})
                if user_por_email:
                    atualizar_usuario(str(user_por_email["_id"]), {
                        "integracoes.strava.atleta_id": strava_id,
                        "integracoes.strava.conectado": True,
                        "integracoes.strava.tokens": tokens
                    })
                    return True

            novo_doc = criar_novo_usuario(email=f"strava_{strava_id}@aura.app", nome=nome, auth_provider="strava")
            atualizar_usuario(novo_doc["_id"], {
                "foto_perfil": foto,
                "integracoes.strava": {"conectado": True, "atleta_id": strava_id, "tokens": tokens}
            })
            return True
    except Exception as e:
        logger.error(f"❌ Erro integração Strava: {e}")
        return False

# ==============================================================
# 🏆 RANKING GLOBAL
# ==============================================================

def obter_ranking_global(limite=50):
    if mongo_db is None: return []
    try:
        # [AURA FIX] Ajustado para buscar 'xp_total' na raiz, conforme seu documento manual
        cursor = mongo_db["usuarios"].find(
            {"plano": {"$ne": "banned"}},
            {"nome": 1, "foto_perfil": 1, "xp_total": 1, "nivel": 1, "_id": 0}
        ).sort("xp_total", DESCENDING).limit(limite)
        
        return [{
            "posicao": i + 1,
            "nome": doc.get("nome", "Anônimo"),
            "foto": doc.get("foto_perfil", ""),
            "xp_total": doc.get("xp_total", 0),
            "nivel": doc.get("nivel", 1),
            "titulo": "Atleta"
        } for i, doc in enumerate(cursor)]
    except Exception as e:
        logger.error(f"❌ Erro no ranking: {e}")
        return []

# ==============================================================
# 🧠 PLANOS MESTRE
# ==============================================================

def salvar_plano(user_id: str, tipo: str, conteudo: dict):
    if mongo_db is None: return False
    try:
        mongo_db["plans"].update_one(
            {"user_id": str(user_id), "tipo": tipo},
            {"$set": {
                "user_id": str(user_id),
                "tipo": tipo,
                "conteudo": conteudo,
                "updated_at": datetime.now().isoformat()
            }},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar plano {tipo}: {e}")
        return False

def ler_plano(user_id: str, tipo: str):
    if mongo_db is None: return {}
    doc = mongo_db["plans"].find_one({"user_id": str(user_id), "tipo": tipo})
    return doc.get("conteudo", {}) if doc else {}

# ==============================================================
# ⚡ OTIMIZAÇÃO DE PERFORMANCE (ÍNDICES)
# ==============================================================
if mongo_db is not None:
    # Ajustado para a coleção 'usuarios'
    mongo_db["usuarios"].create_index("email", unique=True)
    mongo_db["usuarios"].create_index("integracoes.strava.atleta_id")
    mongo_db["usuarios"].create_index([("xp_total", -1)])
    logger.info("⚡ Índices de performance do MongoDB validados na coleção 'usuarios'.")