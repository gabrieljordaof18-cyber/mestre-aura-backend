import os
import logging
import json
from datetime import datetime
from contextlib import asynccontextmanager

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

# ==============================================================
# 💾 BANCO DE DADOS EM MEMÓRIA (MOCK PARA MVP)
# Aqui é onde os treinos e dietas criados pela IA ficarão salvos
# temporariamente para que as telas 'treino_view' e 'dieta_view' possam ler.
# ==============================================================
DB_TREINO = {
    "titulo": "Treino Full Body (Iniciante)",
    "descricao": "Treino padrão do sistema para adaptação.",
    "exercicios": [
        {"nome": "Agachamento Livre", "series": "3", "reps": "12"},
        {"nome": "Flexão de Braço", "series": "3", "reps": "10"},
        {"nome": "Puxada Alta", "series": "3", "reps": "12"}
    ]
}

DB_DIETA = {
    "titulo": "Dieta Equilibrada (Padrão)",
    "calorias": 2200,
    "refeicoes": [
        {"nome": "Café da Manhã", "alimentos": "Ovos mexidos, Pão integral, Café"},
        {"nome": "Almoço", "alimentos": "Frango grelhado, Arroz, Feijão, Salada"},
        {"nome": "Jantar", "alimentos": "Peixe, Legumes cozidos"}
    ]
}

# --- SCHEDULER ---
def job_rotina_diaria_global():
    logger.info("🕛 [SCHEDULER] Executando rotina diária...")

scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(job_rotina_diaria_global, 'cron', hour=0, minute=0)
    scheduler.start()
    logger.info("⏰ [SISTEMA] Scheduler iniciado.")
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ComandoRequest(BaseModel):
    comando: str

# ==============================================================
# 🧠 PROMPT DO SISTEMA (A MÁGICA ACONTECE AQUI)
# ==============================================================
SYSTEM_PROMPT = """
Você é o Mestre da Aura, um treinador de elite e biohacker.
Sua missão é conversar com o usuário OU executar comandos de criação.

IMPORTANTE:
1. Se o usuário pedir para CRIAR UM TREINO, não responda texto. Retorne APENAS um JSON estrito neste formato:
{
  "tipo": "CRIAR_TREINO",
  "dados": {
      "titulo": "Nome do Treino",
      "descricao": "Breve descrição",
      "exercicios": [
          {"nome": "Exercicio", "series": "3", "reps": "12"}
      ]
  }
}

2. Se o usuário pedir para CRIAR UMA DIETA, não responda texto. Retorne APENAS um JSON estrito neste formato:
{
  "tipo": "CRIAR_DIETA",
  "dados": {
      "titulo": "Nome da Dieta",
      "calorias": 2500,
      "refeicoes": [
          {"nome": "Café", "alimentos": "Item 1, Item 2"},
          {"nome": "Almoço", "alimentos": "Item 1, Item 2"}
      ]
  }
}

3. Se for apenas uma conversa, dúvida ou motivação, responda normalmente em TEXTO (sem JSON). Seja curto, estoico e motivador.
"""

# ==============================================================
# 🛣️ ROTAS
# ==============================================================

@app.get("/")
def read_root():
    return {"status": "online", "mensagem": "AURA API Operante 🔱"}

# --- ROTA INTELIGENTE DO CHAT ---
@app.post("/api/comando")
async def processar_comando(request: ComandoRequest):
    logger.info(f"📩 Comando recebido: {request.comando}")
    global DB_TREINO, DB_DIETA # Acessa o banco em memória
    
    if not api_key:
        raise HTTPException(status_code=500, detail="API Key OpenAI ausente.")

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": request.comando}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        conteudo_ia = response.choices[0].message.content.strip()
        
        # Tenta detectar se a IA mandou um JSON (Comando) ou Texto (Conversa)
        if conteudo_ia.startswith("{") and conteudo_ia.endswith("}"):
            try:
                comando_json = json.loads(conteudo_ia)
                
                # --- AÇÃO: CRIAR TREINO ---
                if comando_json.get("tipo") == "CRIAR_TREINO":
                    DB_TREINO = comando_json["dados"] # Salva no "Banco"
                    logger.info("🏋️ Novo treino salvo no sistema!")
                    return {
                        "resposta": f"Entendido. Criei seu novo treino '{DB_TREINO['titulo']}'. Acesse a aba TREINO para ver os detalhes.",
                        "refresh_data": True
                    }

                # --- AÇÃO: CRIAR DIETA ---
                elif comando_json.get("tipo") == "CRIAR_DIETA":
                    DB_DIETA = comando_json["dados"] # Salva no "Banco"
                    logger.info("🍎 Nova dieta salva no sistema!")
                    return {
                        "resposta": f"Feito. Protocolo nutricional '{DB_DIETA['titulo']}' gerado. Acesse a aba DIETA para seguir o plano.",
                        "refresh_data": True
                    }
            except json.JSONDecodeError:
                # Se falhar o parse, trata como texto normal
                logger.warning("Falha ao parsear JSON da IA. Retornando como texto.")
        
        # Se não for JSON, é conversa normal
        return {"resposta": conteudo_ia, "refresh_data": False}

    except Exception as e:
        logger.error(f"❌ Erro OpenAI: {e}")
        return {"resposta": "O Mestre está meditando (Erro interno). Tente novamente.", "refresh_data": False}

# --- ROTAS PARA O FRONTEND LER OS DADOS ---

@app.get("/api/treino")
def get_treino_atual():
    # O Frontend vai chamar essa rota na tela 'treino_view'
    return DB_TREINO

@app.get("/api/dieta")
def get_dieta_atual():
    # O Frontend vai chamar essa rota na tela 'dieta_view'
    return DB_DIETA

# --- MOCKS DE DADOS GERAIS ---
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