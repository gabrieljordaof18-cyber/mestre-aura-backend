import os
import logging
import json
from datetime import datetime
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient # Motor do MongoDB
from apscheduler.schedulers.background import BackgroundScheduler

# Carrega ambiente
load_dotenv()

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("AURA_MAIN")

# Configurações de API
MONGO_URI = os.getenv("MONGO_URI")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client_openai = OpenAI(api_key=OPENAI_API_KEY)
mongo_client = None
db = None

# ==============================================================
# 🔄 SCHEDULER (Tarefas Agendadas)
# ==============================================================
def job_rotina_diaria_global():
    logger.info("🕛 [SCHEDULER] Executando rotina diária...")
    # Futuro: Resetar missões diárias no MongoDB aqui

scheduler = BackgroundScheduler()

# ==============================================================
# 🔌 CICLO DE VIDA (Conexão com Banco)
# ==============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Iniciar Banco de Dados
    global mongo_client, db
    if not MONGO_URI:
        logger.error("❌ MONGO_URI não encontrada nas variáveis de ambiente! O App não salvará dados.")
    else:
        try:
            mongo_client = AsyncIOMotorClient(MONGO_URI)
            db = mongo_client.get_database("aura_db") # Nome do seu banco
            logger.info("✅ Conectado ao MongoDB Atlas com sucesso!")
        except Exception as e:
            logger.error(f"❌ Erro ao conectar no MongoDB: {e}")

    # 2. Iniciar Scheduler
    scheduler.add_job(job_rotina_diaria_global, 'cron', hour=0, minute=0)
    scheduler.start()
    
    yield
    
    # 3. Fechar conexões ao desligar
    if mongo_client:
        mongo_client.close()
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

# CORS (Permite conexão do App)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================
# 📦 MODELOS DE DADOS (Pydantic)
# ==============================================================
class ComandoRequest(BaseModel):
    comando: str

class ChatMessage(BaseModel):
    cla_id: str
    user_id: str
    user_name: str
    message: str
    created_at: Optional[str] = None

# ==============================================================
# 🧠 PROMPT DO SISTEMA
# ==============================================================
SYSTEM_PROMPT = """
Você é o Mestre da Aura, um treinador de elite e biohacker.
Sua missão é conversar com o usuário OU executar comandos de criação.

IMPORTANTE:
1. Se o usuário pedir para CRIAR UM TREINO, não responda texto. Retorne APENAS um JSON estrito:
{"tipo": "CRIAR_TREINO", "dados": {"titulo": "...", "descricao": "...", "exercicios": [{"nome": "...", "series": "3", "reps": "12"}]}}

2. Se o usuário pedir para CRIAR UMA DIETA, não responda texto. Retorne APENAS um JSON estrito:
{"tipo": "CRIAR_DIETA", "dados": {"titulo": "...", "calorias": 2500, "refeicoes": [{"nome": "...", "alimentos": "..."}]}}

3. Caso contrário, responda curto e motivador em texto puro.
"""

# ==============================================================
# 🛣️ ROTAS DA API
# ==============================================================

@app.get("/")
def read_root():
    status_db = "Online 🟢" if db is not None else "Offline 🔴"
    return {"status": "online", "banco_dados": status_db, "mensagem": "AURA API v2.0 (Mongo Edition)"}

# --- 1. ROTA INTELIGENTE DO CHAT (Mestre da Aura) ---
@app.post("/api/comando")
async def processar_comando(request: ComandoRequest):
    logger.info(f"📩 Comando recebido: {request.comando}")
    
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="API Key OpenAI ausente.")

    try:
        response = client_openai.chat.completions.create(
            model="gpt-4o", 
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": request.comando}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        conteudo_ia = response.choices[0].message.content.strip()
        
        # Detecta se é JSON (Comando de Criação)
        if conteudo_ia.startswith("{") and conteudo_ia.endswith("}"):
            try:
                comando_json = json.loads(conteudo_ia)
                
                # Salva TREINO no MongoDB
                if comando_json.get("tipo") == "CRIAR_TREINO" and db is not None:
                    await db.treinos.update_one(
                        {"tipo": "ativo"}, # Sobrescreve o treino 'ativo'
                        {"$set": comando_json["dados"]},
                        upsert=True
                    )
                    return {"resposta": f"Criei seu treino '{comando_json['dados']['titulo']}'. Acesse a aba TREINO.", "refresh_data": True}

                # Salva DIETA no MongoDB
                elif comando_json.get("tipo") == "CRIAR_DIETA" and db is not None:
                    await db.dietas.update_one(
                        {"tipo": "ativo"},
                        {"$set": comando_json["dados"]},
                        upsert=True
                    )
                    return {"resposta": f"Dieta '{comando_json['dados']['titulo']}' gerada. Acesse a aba DIETA.", "refresh_data": True}
            
            except json.JSONDecodeError:
                pass 
        
        # Se não for comando, retorna texto normal
        return {"resposta": conteudo_ia, "refresh_data": False}

    except Exception as e:
        logger.error(f"❌ Erro: {e}")
        return {"resposta": "Erro interno no servidor.", "refresh_data": False}

# --- 2. ROTAS DE DADOS (Lendo do MongoDB) ---

@app.get("/api/treino")
async def get_treino_atual():
    if db is None: return {}
    treino = await db.treinos.find_one({"tipo": "ativo"}, {"_id": 0})
    return treino or {}

@app.get("/api/dieta")
async def get_dieta_atual():
    if db is None: return {}
    dieta = await db.dietas.find_one({"tipo": "ativo"}, {"_id": 0})
    return dieta or {}

# --- 3. ROTAS DO CLÃ (COM LIMITE DE 100 MENSAGENS) ---

@app.get("/api/cla/{cla_id}/chat")
async def get_chat_history(cla_id: str):
    """Busca as últimas 100 mensagens do clã no MongoDB"""
    if db is None: return []
    
    # Busca ordenado por data (crescente)
    cursor = db.chat_messages.find({"cla_id": cla_id}).sort("created_at", 1).limit(100)
    messages = await cursor.to_list(length=100)
    
    # Formata ID para string
    for msg in messages:
        msg["id"] = str(msg["_id"])
        del msg["_id"]
        
    return messages

@app.post("/api/cla/chat")
async def save_chat_message(msg: ChatMessage):
    """
    Salva mensagem e mantém apenas as últimas 100.
    Lógica FIFO (First In, First Out).
    """
    if db is None:
        raise HTTPException(status_code=503, detail="Banco de dados desconectado")
    
    nova_msg = msg.dict()
    if not nova_msg.get("created_at"):
        nova_msg["created_at"] = datetime.utcnow().isoformat()
        
    # 1. Insere a nova mensagem
    result = await db.chat_messages.insert_one(nova_msg)
    
    # 2. Verifica a contagem total de mensagens deste clã
    total_msgs = await db.chat_messages.count_documents({"cla_id": msg.cla_id})
    
    # 3. Lógica de Limpeza (Se passar de 100)
    if total_msgs > 100:
        qtd_para_remover = total_msgs - 100
        
        # Encontra as mensagens mais antigas (ordenadas por data crescente)
        cursor_antigas = db.chat_messages.find({"cla_id": msg.cla_id}).sort("created_at", 1).limit(qtd_para_remover)
        
        # Remove uma por uma (seguro) ou delete_many (se tiver logica de ID)
        async for msg_antiga in cursor_antigas:
            await db.chat_messages.delete_one({"_id": msg_antiga["_id"]})
            logger.info(f"🧹 Limpeza Automática: Mensagem antiga {msg_antiga['_id']} removida do Clã {msg.cla_id}")

    return {"status": "ok", "id": str(result.inserted_id)}

# --- MOCKS (Mantidos para compatibilidade visual) ---
@app.get("/api/missoes")
def get_missoes():
    return {"missoes": [{"id": 1, "descricao": "Treino de Força", "xp": 100, "concluida": False}]}

@app.get("/api/usuario/status")
def get_status():
    return {"nivel": 5, "xp_total": 2450, "xp_por_nivel": 3000, "saldo_coins": 120, "saldo_cristais": 15}

@app.get("/api/status_fisiologico")
def get_fisio():
    return {"energia": {"nivel": 85}, "sono": {"horas": 7.5}, "hrv": {"valor": 65}, "treino": {"intensidade": 90}}

@app.get("/api/equilibrio")
def get_equilibrio():
    return {"score": 88, "estado": "Equilibrado", "componentes": {"corpo": 90, "mente": 85}}

# ENTRY POINT
if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)