import json
import os
import shutil
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Tenta conectar ao MongoDB
MONGO_URI = os.getenv("MONGODB_URI")
mongo_client = None
mongo_db = None

if MONGO_URI:
    try:
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # Testa conexão
        mongo_client.server_info()
        mongo_db = mongo_client["mestre_aura_db"]
        print("✅ [DATA] Conectado ao MongoDB Atlas (Nuvem)")
    except Exception as e:
        print(f"⚠️ [DATA] Erro conexão Mongo: {e}. Usando modo local.")
        mongo_client = None
        mongo_db = None

# ==============================================================
# 🛡️ O GUARDIÃO HÍBRIDO (ARQUIVO + MONGODB)
# ==============================================================

def carregar_json(caminho_arquivo, schema_padrao=None):
    """
    Carrega dados. Prioridade: MongoDB -> Arquivo Local -> Schema Padrão.
    """
    dados = {}
    nome_colecao = _definir_colecao(caminho_arquivo)
    
    # 1. Tenta ler do MongoDB
    if mongo_db is not None:
        try:
            colecao = mongo_db[nome_colecao]
            doc = colecao.find_one({"_id": "main_data"})
            if doc:
                del doc["_id"]
                dados = doc
                _salvar_arquivo_local(caminho_arquivo, dados)
                return _garantir_schema(dados, schema_padrao)
        except Exception as e:
            print(f"⚠️ Erro leitura Mongo ({nome_colecao}): {e}")

    # 2. Se falhou, tenta Arquivo Local
    if os.path.exists(caminho_arquivo):
        try:
            with open(caminho_arquivo, 'r', encoding='utf-8') as f:
                dados = json.load(f)
        except Exception:
            dados = {}
    
    # 3. Se tudo falhou, Schema Padrão
    if not dados and schema_padrao:
        dados = schema_padrao

    return _garantir_schema(dados, schema_padrao)


def salvar_json(caminho_arquivo, dados):
    """
    Salva dados no MongoDB E no Arquivo Local.
    """
    sucesso_local = _salvar_arquivo_local(caminho_arquivo, dados)
    sucesso_nuvem = False

    # Tenta salvar na nuvem
    if mongo_db is not None:
        try:
            nome_colecao = _definir_colecao(caminho_arquivo)
            colecao = mongo_db[nome_colecao]
            
            if isinstance(dados, dict):
                dados["_system_updated_at"] = str(datetime.now())
            
            dados_para_salvar = dados.copy()
            colecao.update_one(
                {"_id": "main_data"}, 
                {"$set": dados_para_salvar}, 
                upsert=True
            )
            sucesso_nuvem = True
        except Exception as e:
            print(f"⚠️ Erro gravação Mongo: {e}")

    return sucesso_local or sucesso_nuvem

# ==============================================================
# 🏃 INTEGRAÇÃO STRAVA (NOVO)
# ==============================================================

def salvar_conexao_strava(dados_atleta, tokens):
    """
    Salva os dados de autenticação do Strava em uma coleção dedicada 'usuarios'.
    """
    if mongo_db is None:
        print("⚠️ [DATA] MongoDB não conectado. Impossível salvar Strava.")
        return False

    try:
        # Usa uma coleção específica para usuários (separado da memória global do jogo)
        colecao = mongo_db["usuarios"]
        
        strava_id = dados_atleta.get('id')
        
        dados_para_salvar = {
            "strava_id": strava_id,
            "nome": dados_atleta.get('firstname'),
            "sobrenome": dados_atleta.get('lastname'),
            "foto_perfil": dados_atleta.get('profile'),
            "tokens": {
                "access_token": tokens.get('access_token'),
                "refresh_token": tokens.get('refresh_token'),
                "expires_at": tokens.get('expires_at')
            },
            "ultima_atualizacao": datetime.now()
        }

        # Upsert: Atualiza se existir, cria se não existir
        colecao.update_one(
            {"strava_id": strava_id},
            {"$set": dados_para_salvar},
            upsert=True
        )
        
        print(f"✅ [DATA] Usuário Strava ID {strava_id} salvo com sucesso.")
        return True
        
    except Exception as e:
        print(f"❌ [DATA] Erro ao salvar dados Strava: {e}")
        return False


# ==============================================================
# ⚙️ FUNÇÕES AUXILIARES INTERNAS
# ==============================================================

def _salvar_arquivo_local(caminho, dados):
    caminho_temp = caminho + ".tmp"
    dir_pai = os.path.dirname(caminho)
    if dir_pai and not os.path.exists(dir_pai):
        os.makedirs(dir_pai, exist_ok=True)

    try:
        with open(caminho_temp, 'w', encoding='utf-8') as f:
            json.dump(dados, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(caminho_temp, caminho)
        return True
    except Exception:
        return False

def _garantir_schema(dados, schema):
    if schema:
        return _mesclar_dicionarios(schema.copy(), dados)
    return dados

def _mesclar_dicionarios(padrao, atual):
    for chave, valor_padrao in padrao.items():
        if chave not in atual:
            atual[chave] = valor_padrao
        elif isinstance(valor_padrao, dict) and isinstance(atual[chave], dict):
            _mesclar_dicionarios(valor_padrao, atual[chave])
    return atual

def _definir_colecao(caminho):
    if "memoria_global" in caminho: return "global_memory"
    if "banco_de_missoes" in caminho: return "missions_db"
    return "user_memory"