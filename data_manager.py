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
    # [AURA FIX] Timeout aumentado para 15s para evitar falhas em cold starts do Render/Atlas
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=15000, retryWrites=True)
    mongo_client.server_info()
    
    mongo_db = mongo_client["mestre_aura_db"]
    logger.info("✅ [DATA] Conectado ao MongoDB Atlas com sucesso.")
    
except Exception as e:
    logger.critical(f"❌ [DATA] ERRO CRÍTICO DE CONEXÃO: {e}")
    mongo_client = None
    mongo_db = None

# ==============================================================
# 👤 GERENCIAMENTO DE USUÁRIOS (NATIVE & IAP READY)
# ==============================================================

def buscar_usuario_por_id(user_id: str):
    """
    Busca o usuário por _id (ObjectId nativo) OU por base44_id (string legada).
    Garante compatibilidade durante a migração do Base44 para autenticação nativa.
    """
    if mongo_db is None:
        logger.error("❌ MongoDB inacessível em buscar_usuario_por_id")
        return None
    try:
        clean_id = str(user_id).strip().replace('"', '').replace("'", "")

        doc = None

        # 1. Tenta como ObjectId nativo do MongoDB
        if ObjectId.is_valid(clean_id):
            doc = mongo_db["usuarios"].find_one({"_id": ObjectId(clean_id)})

        # 2. Fallback: busca pelo campo base44_id (IDs legados do Base44)
        if not doc:
            doc = mongo_db["usuarios"].find_one({"base44_id": clean_id})
            if doc:
                logger.info(f"✅ Usuário encontrado via base44_id: {clean_id}")

        if doc:
            doc["_id"] = str(doc["_id"])
            if "plano" not in doc: doc["plano"] = "free"
            if "status_assinatura" not in doc: doc["status_assinatura"] = "inativo"
        else:
            logger.warning(f"⚠️ Usuário não encontrado por _id nem base44_id: {clean_id}")

        return doc
    except Exception as e:
        logger.error(f"Erro ao buscar usuário ID {user_id}: {e}")
        return None

def buscar_usuario_por_email(email: str):
    if mongo_db is None: return None
    try:
        doc = mongo_db["usuarios"].find_one({"email": email.strip().lower()})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc
    except Exception as e:
        logger.error(f"Erro ao buscar email {email}: {e}")
        return None

def criar_novo_usuario(email: str, nome: str, auth_provider="email"):
    """
    Cria um novo usuário já com os campos exigidos pela App Store.
    Garante que novos cadastros via Apple Sign-in funcionem instantaneamente.
    """
    if mongo_db is None: return None
    
    # Obtém o template base do schema.py
    novo_user = obter_schema_padrao_usuario(email=email.strip().lower(), nome=nome)
    
    # [AURA NEW] Campos obrigatórios para o fluxo nativo 3.3.0
    novo_user["auth_provider"] = auth_provider
    novo_user["plano"] = "free"
    novo_user["status_assinatura"] = "inativo"
    novo_user["data_vencimento"] = ""
    novo_user["created_at"] = datetime.now().isoformat()
    novo_user["updated_at"] = datetime.now().isoformat()
    
    try:
        resultado = mongo_db["usuarios"].insert_one(novo_user)
        novo_user["_id"] = str(resultado.inserted_id)
        logger.info(f"🆕 Novo usuário {nome} ({auth_provider}) criado no Atlas.")
        return novo_user
    except Exception as e:
        logger.error(f"Erro ao criar usuário: {e}")
        return None

def atualizar_usuario(user_id: str, dados_atualizacao: dict):
    if mongo_db is None: return False
    try:
        clean_id = str(user_id).strip().replace('"', '').replace("'", "")
        
        # Proteção contra ID inválido
        if not ObjectId.is_valid(clean_id): return False

        # Removemos o _id se ele vier nos dados para não dar erro de imutabilidade
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
                "foto_perfil": foto 
            })
            return True
        else:
            if email_strava:
                user_por_email = colecao_users.find_one({"email": email_strava.strip().lower()})
                if user_por_email:
                    atualizar_usuario(str(user_por_email["_id"]), {
                        "integracoes.strava.atleta_id": strava_id,
                        "integracoes.strava.conectado": True,
                        "integracoes.strava.tokens": tokens
                    })
                    return True

            # Cria como 'strava' provider
            novo_doc = criar_novo_usuario(
                email=f"strava_{strava_id}@aura.app", 
                nome=nome, 
                auth_provider="strava"
            )
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
        # [AURA FIX] Busca baseada em xp_total, refletindo o saldo oficial de moedas (1:1)
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
            "titulo": "Atleta Elite"
        } for i, doc in enumerate(cursor)]
    except Exception as e:
        logger.error(f"❌ Erro no ranking: {e}")
        return []

# ==============================================================
# 🧠 PLANOS MESTRE (ROBUSTEZ DE TREINOS HÍBRIDOS)
# ==============================================================

def salvar_plano(user_id: str, tipo: str, conteudo: dict):
    """
    Salva ou atualiza um plano estruturado (treino ou dieta).
    """
    if mongo_db is None: return False
    try:
        clean_user_id = str(user_id).strip().replace('"', '').replace("'", "")
        if not ObjectId.is_valid(clean_user_id): return False
        
        # [AURA ROBUST] Inserimos uma cópia no histórico antes de atualizar o plano ativo
        mongo_db["plan_history"].insert_one({
            "user_id": clean_user_id,
            "tipo": tipo,
            "conteudo": conteudo,
            "archived_at": datetime.now().isoformat()
        })

        # Atualizamos o plano ativo na coleção principal 'plans'
        mongo_db["plans"].update_one(
            {"user_id": clean_user_id, "tipo": tipo},
            {"$set": {
                "user_id": clean_user_id,
                "tipo": tipo,
                "conteudo": conteudo,
                "updated_at": datetime.now().isoformat(),
                "versao_ia": "3.3.0-Native" 
            }},
            upsert=True
        )
        
        # Atualizamos o documento do usuário para avisar que há um plano novo
        mongo_db["usuarios"].update_one(
            {"_id": ObjectId(clean_user_id)},
            {"$set": {f"planos.{tipo}_ativo": True, "updated_at": datetime.now().isoformat()}}
        )

        logger.info(f"✅ Plano de {tipo} salvo para {clean_user_id}")
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar plano robusto {tipo} para {user_id}: {e}")
        return False

def ler_plano(user_id: str, tipo: str):
    if mongo_db is None: return {}
    try:
        clean_user_id = str(user_id).strip().replace('"', '').replace("'", "")
        if not ObjectId.is_valid(clean_user_id): return {}

        doc = mongo_db["plans"].find_one({"user_id": clean_user_id, "tipo": tipo})
        if doc:
            return doc.get("conteudo", {})
        return {}
    except Exception as e:
        logger.error(f"Erro ao ler plano robusto {tipo} para {user_id}: {e}")
        return {}

# ==============================================================
# ⚡ OTIMIZAÇÃO DE PERFORMANCE (ÍNDICES)
# ==============================================================
if mongo_db is not None:
    try:
        colecao_usuarios = mongo_db["usuarios"]
        indices_atuais = colecao_usuarios.index_information()
        
        if "email_1" not in indices_atuais:
            colecao_usuarios.create_index("email", unique=True, sparse=True)
            
        if "integracoes.strava.atleta_id_1" not in indices_atuais:
            colecao_usuarios.create_index("integracoes.strava.atleta_id", sparse=True)

        if "base44_id_1" not in indices_atuais:
            colecao_usuarios.create_index("base44_id", sparse=True)
            
        if "xp_total_-1" not in indices_atuais:
            colecao_usuarios.create_index([("xp_total", -1)])
            
        # Índice para busca rápida de planos
        mongo_db["plans"].create_index([("user_id", 1), ("tipo", 1)])
        
        # Novo índice para o histórico de evolução
        mongo_db["plan_history"].create_index([("user_id", 1), ("archived_at", -1)])
            
        logger.info("⚡ Índices robustos validados no MongoDB Atlas.")
    except Exception as e:
        logger.warning(f"⚠️ Aviso ao gerenciar índices: {e}")