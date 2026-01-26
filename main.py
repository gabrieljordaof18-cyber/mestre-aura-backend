import os
import logging
import json
from datetime import datetime
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from apscheduler.schedulers.background import BackgroundScheduler

# Carrega ambiente
load_dotenv()

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AURA_MAIN")

# Configurações de API
MONGO_URI = os.getenv("MONGO_URI")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client_openai = OpenAI(api_key=OPENAI_API_KEY)
mongo_client = None
db = None

# --- SCHEDULER ---
def job_rotina_diaria_global():
    logger.info("🕛 [SCHEDULER] Executando rotina diária...")

scheduler = BackgroundScheduler()

# --- LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global mongo_client, db
    if not MONGO_URI:
        logger.error("❌ MONGO_URI ausente!")
    else:
        try:
            mongo_client = AsyncIOMotorClient(MONGO_URI)
            db = mongo_client.get_database("aura_db")
            logger.info("✅ Conectado ao MongoDB!")
        except Exception as e:
            logger.error(f"❌ Erro Mongo: {e}")

    scheduler.add_job(job_rotina_diaria_global, 'cron', hour=0, minute=0)
    scheduler.start()
    yield
    if mongo_client: mongo_client.close()
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELOS ---
class ComandoRequest(BaseModel):
    comando: str

class ChatMessage(BaseModel):
    cla_id: str
    user_id: str
    user_name: str
    message: str
    created_at: Optional[str] = None

# --- PROMPT ---
SYSTEM_PROMPT = """
Você é o Mestre da Aura.
1. Se pedir TREINO: {"tipo": "CRIAR_TREINO", "dados": {...}}
2. Se pedir DIETA: {"tipo": "CRIAR_DIETA", "dados": {...}}
3. Senão: Texto curto e estoico.
"""

# --- ROTAS ---

@app.get("/")
def read_root():
    return {"status": "online", "db": "OK" if db is not None else "OFF"}

# 1. STATUS DO USUÁRIO (REAL)
@app.get("/api/usuario/status")
async def get_status(request: Request):
    """Retorna Nível e XP reais do usuário logado"""
    if db is None: return {"nivel": 1, "xp_total": 0, "xp_por_nivel": 1000}
    
    # Tenta pegar ID do header Authorization (Bearer <id>)
    auth_header = request.headers.get('Authorization')
    user_id = auth_header.split(" ")[1] if auth_header else None

    if user_id:
        # Busca no banco base44 (simulado via collection 'users' se existir, ou cria padrão)
        # Nota: Como o auth é externo (Base44), aqui assumimos que se o ID existe, retornamos dados
        # Para MVP, vamos buscar na coleção 'users_gamification' que criaremos agora
        user_stats = await db.users_gamification.find_one({"user_id": user_id})
        
        if user_stats:
            return {
                "nivel": user_stats.get("nivel", 1),
                "xp_total": user_stats.get("xp_total", 0),
                "xp_por_nivel": 1000,
                "saldo_coins": user_stats.get("saldo_coins", 0),
                "saldo_cristais": user_stats.get("saldo_cristais", 0)
            }
    
    # Padrão para novos usuários
    return {"nivel": 1, "xp_total": 0, "xp_por_nivel": 1000, "saldo_coins": 0, "saldo_cristais": 0}

# 2. MISSÕES DIÁRIAS (FIXAS POR ENQUANTO)
@app.get("/api/missoes")
def get_missoes():
    return {"missoes": [
        {"id": 1, "descricao": "Registrar Atividade Física", "xp": 100, "concluida": False},
        {"id": 2, "descricao": "Beber 2L de Água", "xp": 50, "concluida": False},
        {"id": 3, "descricao": "Ler 10 Páginas", "xp": 75, "concluida": False}
    ]}

# 3. RANKING GLOBAL (REAL)
@app.get("/api/cla/ranking")
async def get_ranking():
    """Retorna Top 50 usuários ordenados por XP"""
    if db is None: return {"ranking": []}
    
    # Busca usuários com XP > 0
    cursor = db.users_gamification.find().sort("xp_total", -1).limit(50)
    ranking = await cursor.to_list(length=50)
    
    # Formata para o frontend
    ranking_formatado = []
    for r in ranking:
        ranking_formatado.append({
            "id": r["user_id"],
            "nome": r.get("nome", "Viajante"),
            "xp_total": r.get("xp_total", 0),
            "nivel": r.get("nivel", 1)
        })
        
    return {"ranking": ranking_formatado}

# 4. CHAT DO CLÃ (COM LIMITE 100)
@app.get("/api/cla/{cla_id}/chat")
async def get_chat_history(cla_id: str):
    if db is None: return []
    cursor = db.chat_messages.find({"cla_id": cla_id}).sort("created_at", 1).limit(100)
    messages = await cursor.to_list(length=100)
    for msg in messages:
        msg["id"] = str(msg["_id"])
        del msg["_id"]
    return messages

@app.post("/api/cla/chat")
async def save_chat_message(msg: ChatMessage):
    if db is None: raise HTTPException(status_code=503)
    
    nova_msg = msg.dict()
    if not nova_msg.get("created_at"): nova_msg["created_at"] = datetime.utcnow().isoformat()
    
    await db.chat_messages.insert_one(nova_msg)
    
    # Limpeza > 100
    total = await db.chat_messages.count_documents({"cla_id": msg.cla_id})
    if total > 100:
        oldest = db.chat_messages.find({"cla_id": msg.cla_id}).sort("created_at", 1).limit(total - 100)
        async for old in oldest:
            await db.chat_messages.delete_one({"_id": old["_id"]})

    return {"status": "ok"}

# 5. CHAT MESTRE (IA)
@app.post("/api/comando")
async def processar_comando(request: ComandoRequest):
    if not OPENAI_API_KEY: raise HTTPException(status_code=500)
    try:
        response = client_openai.chat.completions.create(
            model="gpt-4o", 
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": request.comando}],
            max_tokens=800
        )
        content = response.choices[0].message.content.strip()
        
        # Salva Treino/Dieta se for JSON
        if content.startswith("{") and db:
            try:
                data = json.loads(content)
                if data.get("tipo") == "CRIAR_TREINO":
                    await db.treinos.update_one({"tipo": "ativo"}, {"$set": data["dados"]}, upsert=True)
                    return {"resposta": "Treino criado! Veja na aba Treino.", "refresh_data": True}
                if data.get("tipo") == "CRIAR_DIETA":
                    await db.dietas.update_one({"tipo": "ativo"}, {"$set": data["dados"]}, upsert=True)
                    return {"resposta": "Dieta criada! Veja na aba Dieta.", "refresh_data": True}
            except: pass
            
        return {"resposta": content, "refresh_data": False}
    except Exception as e:
        logger.error(f"Erro IA: {e}")
        return {"resposta": "Erro de conexão neural.", "refresh_data": False}

# Rotas de Leitura Treino/Dieta
@app.get("/api/treino")
async def get_treino():
    if db is None: return {}
    return await db.treinos.find_one({"tipo": "ativo"}, {"_id": 0}) or {}

@app.get("/api/dieta")
async def get_dieta():
    if db is None: return {}
    return await db.dietas.find_one({"tipo": "ativo"}, {"_id": 0}) or {}

# Rotas Fisiologia (Mock por enquanto)
@app.get("/api/status_fisiologico")
def get_fisio(): return {"energia": {"nivel": 85}, "sono": {"horas": 7.5}, "hrv": {"valor": 65}, "treino": {"intensidade": 90}}
@app.get("/api/equilibrio")
def get_equilibrio(): return {"score": 88, "estado": "Equilibrado", "componentes": {"corpo": 90, "mente": 85}}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))