import os
import logging
import json
from datetime import datetime
from contextlib import asynccontextmanager

# [MUDANÇA] Usamos FastAPI para performance com IA e correção de CORS
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
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

# Configuração OpenAI
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# --- SCHEDULER (Mantido da sua versão) ---
def job_rotina_diaria_global():
    logger.info("🕛 [SCHEDULER] Executando rotina diária...")
    # Lógica de reset de missões aqui futuramente

scheduler = BackgroundScheduler()

# Ciclo de Vida do App
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicia Scheduler
    scheduler.add_job(job_rotina_diaria_global, 'cron', hour=0, minute=0)
    scheduler.start()
    logger.info("⏰ [SISTEMA] Scheduler iniciado.")
    yield
    # Desliga Scheduler
    scheduler.shutdown()

# Inicializa App
app = FastAPI(lifespan=lifespan)

# [CRÍTICO] Configuração de CORS (Resolve o erro de conexão)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Permite conexão de qualquer lugar (Frontend)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelo de dados para o Chat
class ComandoRequest(BaseModel):
    comando: str

# ==============================================================
# 🛣️ ROTAS DA API
# ==============================================================

@app.get("/")
def read_root():
    return {"status": "online", "mensagem": "AURA API Operante 🔱"}

# --- 1. ROTA DO CHAT (IA) ---
@app.post("/api/comando")
async def processar_comando(request: ComandoRequest):
    logger.info(f"📩 Comando recebido: {request.comando}")
    
    if not api_key:
        raise HTTPException(status_code=500, detail="API Key da OpenAI não configurada no Backend.")

    try:
        # Usa o modelo barato e rápido que configuramos
        response = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[
                {"role": "system", "content": "Você é o Mestre da Aura. Responda curto e motivador."},
                {"role": "user", "content": request.comando}
            ],
            max_tokens=300
        )
        texto_ia = response.choices[0].message.content
        return {"resposta": texto_ia, "refresh_data": False}

    except Exception as e:
        logger.error(f"❌ Erro OpenAI: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- 2. ROTAS DE DADOS (Para a Home e Perfil funcionarem) ---

@app.get("/api/missoes")
def get_missoes():
    # Retorna missões reais ou padrão para destravar a Home
    return {
        "missoes": [
            {"id": 1, "descricao": "Treino de Força", "xp": 100, "concluida": False},
            {"id": 2, "descricao": "Beber 3L de Água", "xp": 50, "concluida": True},
            {"id": 3, "descricao": "Meditação 5min", "xp": 75, "concluida": False}
        ]
    }

@app.get("/api/usuario/status")
def get_status():
    return {
        "nivel": 5,
        "xp_total": 2450,
        "xp_por_nivel": 3000,
        "saldo_coins": 120,
        "saldo_cristais": 15
    }

@app.get("/api/status_fisiologico")
def get_fisio():
    return {"energia": {"nivel": 85}, "sono": {"horas": 7.5}, "hrv": {"valor": 65}, "treino": {"intensidade": 90}}

@app.get("/api/equilibrio")
def get_equilibrio():
    return {"score": 88, "estado": "Equilibrado", "componentes": {"corpo": 90, "mente": 85}}

# ==============================================================
# 🚀 ENTRY POINT
# ==============================================================
if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get("PORT", 10000)) # Porta padrão do Render
    logger.info(f"🔱 INICIANDO SERVIDOR NA PORTA {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)