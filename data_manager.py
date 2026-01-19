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

# Carrega variáveis de ambiente
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

    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    # Força um comando para testar a conexão
    mongo_client.server_info()
    
    # Define o Banco de Dados Principal
    mongo_db = mongo_client["mestre_aura_db"]
    logger.info("✅ [DATA] Conectado ao MongoDB Atlas (Nuvem) com sucesso.")
    
except Exception as e:
    logger.critical(f"❌ [DATA] ERRO CRÍTICO DE CONEXÃO: {e}")
    mongo_client = None
    mongo_db = None

# ==============================================================
# 👤 GERENCIAMENTO DE USUÁRIOS (USER CORE)
# ==============================================================

def buscar_usuario_por_id(user_id: str):
    """Retorna o documento do usuário pelo ID do MongoDB."""
    if mongo_db is None: return None
    try:
        return mongo_db["users"].find_one({"_id": ObjectId(user_id)})
    except Exception as e:
        logger.error(f"Erro ao buscar usuário ID {user_id}: {e}")
        return None

def buscar_usuario_por_email(email: str):
    """Busca usuário por email (Login)."""
    if mongo_db is None: return None
    return mongo_db["users"].find_one({"email": email})

def criar_novo_usuario(email: str, nome: str, auth_provider="email"):
    """
    Cria um novo usuário usando o SCHEMA PADRÃO oficial.
    Retorna o documento criado.
    """
    if mongo_db is None: return None
    
    # 1. Gera estrutura padrão
    novo_user = obter_schema_padrao_usuario(email=email, nome=nome)
    novo_user["auth_provider"] = auth_provider
    
    try:
        # 2. Insere no banco
        resultado = mongo_db["users"].insert_one(novo_user)
        novo_user["_id"] = str(resultado.inserted_id)
        logger.info(f"🆕 Novo usuário criado: {email} (ID: {novo_user['_id']})")
        return novo_user
    except Exception as e:
        logger.error(f"Erro ao criar usuário: {e}")
        return None

def atualizar_usuario(user_id: str, dados_atualizacao: dict):
    """
    Atualiza campos específicos do usuário.
    Ex: dados_atualizacao = {"jogador.saldo_coins": 500}
    """
    if mongo_db is None: return False
    try:
        dados_atualizacao["updated_at"] = str(datetime.now())
        mongo_db["users"].update_one(
            {"_id": ObjectId(user_id)},
            {"$set": dados_atualizacao}
        )
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar usuário {user_id}: {e}")
        return False

# ==============================================================
# 🏃 INTEGRAÇÃO STRAVA (MULTI-TENANT)
# ==============================================================

def salvar_conexao_strava(dados_atleta: dict, tokens: dict):
    """
    Chamado pelo callback do Strava.
    Lógica:
    1. Procura se já existe um usuário com esse strava_id.
    2. Se existir, atualiza tokens.
    3. Se não, CRIA um novo usuário via Strava.
    """
    if mongo_db is None: return False

    strava_id = dados_atleta.get('id')
    email_strava = dados_atleta.get('email') # Nem sempre vem, mas tentamos
    nome = dados_atleta.get('firstname', 'Atleta')
    foto = dados_atleta.get('profile', '')

    try:
        colecao_users = mongo_db["users"]
        
        # 1. Tenta achar pelo ID do Strava
        usuario_existente = colecao_users.find_one({"integracoes.strava.atleta_id": strava_id})

        if usuario_existente:
            # Atualiza tokens e foto
            colecao_users.update_one(
                {"_id": usuario_existente["_id"]},
                {"$set": {
                    "integracoes.strava.conectado": True,
                    "integracoes.strava.tokens": tokens,
                    "profile_picture_url": foto, # Atualiza foto com a do Strava
                    "updated_at": str(datetime.now())
                }}
            )
            logger.info(f"🔄 Tokens Strava atualizados para usuário existente: {usuario_existente.get('email')}")
            return True
        else:
            # 2. Novo Usuário via Strava
            # Primeiro, verificamos se o email já existe (para não duplicar contas)
            if email_strava:
                user_por_email = colecao_users.find_one({"email": email_strava})
                if user_por_email:
                    # Vincula Strava à conta de email existente
                    colecao_users.update_one(
                        {"_id": user_por_email["_id"]},
                        {"$set": {
                            "integracoes.strava.atleta_id": strava_id,
                            "integracoes.strava.conectado": True,
                            "integracoes.strava.tokens": tokens,
                            "updated_at": str(datetime.now())
                        }}
                    )
                    return True

            # 3. Criação Zero (Usuário novo mesmo)
            novo_doc = obter_schema_padrao_usuario(email=f"strava_{strava_id}@aura.app", nome=nome)
            novo_doc["auth_provider"] = "strava"
            novo_doc["profile_picture_url"] = foto
            novo_doc["integracoes"]["strava"] = {
                "conectado": True,
                "atleta_id": strava_id,
                "tokens": tokens
            }
            
            colecao_users.insert_one(novo_doc)
            logger.info(f"🆕 Usuário criado via Strava ID: {strava_id}")
            return True

    except Exception as e:
        logger.error(f"❌ Erro integração Strava: {e}")
        return False

def salvar_atividade_strava(user_id: str, dados_atividade: dict):
    """Salva a atividade crua na coleção 'activities' para histórico."""
    if mongo_db is None: return
    try:
        dados_atividade["user_id"] = str(user_id) # Foreign Key
        dados_atividade["created_at"] = datetime.now()
        mongo_db["activities"].insert_one(dados_atividade)
    except Exception as e:
        logger.error(f"Erro ao salvar atividade: {e}")

# ==============================================================
# 🏆 RANKING GLOBAL (FILTRADO)
# ==============================================================

def obter_ranking_global(limite=50):
    """
    Retorna Top Jogadores por XP.
    Filtra usuários deletados ou bots.
    """
    if mongo_db is None: return []
    
    try:
        colecao = mongo_db["users"]
        cursor = colecao.find(
            {"plano": {"$ne": "banned"}}, # Exemplo de filtro
            {
                "jogador.nome": 1, 
                "profile_picture_url": 1, 
                "jogador.experiencia": 1, 
                "jogador.nivel": 1, 
                "jogador.titulo_atual": 1,
                "_id": 0
            }
        ).sort("jogador.experiencia", DESCENDING).limit(limite)
        
        ranking = []
        for i, doc in enumerate(cursor):
            jogador = doc.get("jogador", {})
            ranking.append({
                "posicao": i + 1,
                "nome": jogador.get("nome", "Anônimo"),
                "foto": doc.get("profile_picture_url") or "",
                "xp_total": jogador.get("experiencia", 0),
                "nivel": jogador.get("nivel", 1),
                "titulo": jogador.get("titulo_atual", "Iniciado")
            })
            
        return ranking
    except Exception as e:
        logger.error(f"❌ Erro no ranking: {e}")
        return []

# ==============================================================
# 🧠 PLANOS MESTRE (DIETA E TREINO)
# ==============================================================

def salvar_plano(user_id: str, tipo: str, conteudo: dict):
    """
    Salva dieta ou treino na coleção 'plans'.
    tipo: 'dieta' ou 'treino'
    """
    if mongo_db is None: return False
    try:
        colecao_plans = mongo_db["plans"]
        
        # Upsert: Atualiza o plano existente daquele tipo para aquele usuário
        filtro = {"user_id": str(user_id), "tipo": tipo}
        dados = {
            "user_id": str(user_id),
            "tipo": tipo,
            "conteudo": conteudo,
            "updated_at": datetime.now()
        }
        
        colecao_plans.update_one(filtro, {"$set": dados}, upsert=True)
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar plano {tipo}: {e}")
        return False

def ler_plano(user_id: str, tipo: str):
    """Recupera o plano atual do usuário."""
    if mongo_db is None: return {}
    try:
        doc = mongo_db["plans"].find_one({"user_id": str(user_id), "tipo": tipo})
        return doc.get("conteudo", {}) if doc else {}
    except Exception as e:
        logger.error(f"Erro ao ler plano {tipo}: {e}")
        return {}