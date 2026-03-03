import os
import json
import logging
from typing import List, Dict, Any
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

# Importações da Nova Arquitetura
from data_user import carregar_memoria
from data_manager import mongo_db, DESCENDING, salvar_plano

# Carrega variáveis do .env
load_dotenv()

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AURA_BRAIN")

# Configuração da OpenAI
client = None
api_key = os.getenv("OPENAI_API_KEY")

if api_key:
    try:
        client = OpenAI(api_key=api_key)
        logger.info("✅ Mestre da Aura inicializado via OpenAI.")
    except Exception as e:
        logger.error(f"⚠️ Falha ao iniciar Mestre da Aura: {e}")
else:
    logger.warning("⚠️ OPENAI_API_KEY ausente no .env")

# ======================================================
# 🛠️ FERRAMENTAS DO MESTRE (DIETAS E TREINOS)
# ======================================================

SCHEMA_EXERCICIO = {
    "type": "object",
    "properties": {
        "exercicio": {"type": "string", "description": "Ex: Supino Reto"},
        "tipo": {"type": "string", "enum": ["forca", "cardio"]},
        "periodo": {"type": "string", "enum": ["unico", "manha", "tarde"]},
        "series": {"type": "string"},
        "reps": {"type": "string"},
        "detalhes": {"type": "string"}
    },
    "required": ["exercicio", "tipo", "periodo"]
}

TOOLS_AURA = [
    {
        "type": "function",
        "function": {
            "name": "salvar_nova_dieta",
            "description": "Salva o plano alimentar estruturado no perfil do atleta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resumo_objetivo": {"type": "string"},
                    "kcal_total": {"type": "string"},
                    "cafe_da_manha": {"type": "string"},
                    "almoco": {"type": "string"},
                    "lanche": {"type": "string"},
                    "jantar": {"type": "string"},
                    "suplementacao": {"type": "string"}
                },
                "required": ["resumo_objetivo", "cafe_da_manha", "almoco", "jantar"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "salvar_novo_treino",
            "description": "Cria e salva uma rotina de exercícios semanal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "foco_atual": {"type": "string"},
                    "segunda": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "terca": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "quarta": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "quinta": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "sexta": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "sabado": {"type": "array", "items": SCHEMA_EXERCICIO}
                },
                "required": ["foco_atual", "segunda", "terca", "quarta"]
            }
        }
    }
]

# ======================================================
# 💬 PROCESSAMENTO DE COMANDOS (IA CORE)
# ======================================================

def processar_comando(user_id: str, mensagem: str) -> str:
    """
    Interface principal de chat do Aura.
    Analisa contexto fisiológico e decide entre falar ou agir (tools).
    """
    if not user_id: return "⚠️ Erro de identificação."

    # 1. Carrega Contexto (Multijogador)
    memoria = carregar_memoria(user_id)
    jogador = memoria.get("jogador", {})
    homeostase = memoria.get("homeostase", {})
    
    # 2. Prompt do Sistema (Personalidade do Mestre)
    prompt_sistema = {
        "role": "system", 
        "content": (
            f"Você é o MESTRE DA AURA. Treinador técnico, estoico e direto.\n"
            f"Atleta: {jogador.get('nome', 'Iniciado')} | Nível: {jogador.get('nivel', 1)}\n"
            f"Estado Biofísico: {homeostase.get('estado', 'Estável')} (Score: {homeostase.get('score', 50)})\n\n"
            f"REGRAS:\n"
            f"1. Para Dietas/Treinos, use obrigatoriamente as TOOLS.\n"
            f"2. Adapte o tom ao estado biofísico: Se o score for baixo, seja mais protetor. Se alto, desafie o atleta.\n"
            f"3. Mantenha respostas curtas (máximo 3 parágrafos).\n"
        )
    }

    # 3. Histórico e Mensagem Atual
    historico = _buscar_historico(user_id, limite=5)
    mensagens = [prompt_sistema] + historico + [{"role": "user", "content": mensagem}]

    # 4. Execução OpenAI
    try:
        if not client: return "⚠️ Sistema de IA Offline."
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=mensagens,
            tools=TOOLS_AURA,
            tool_choice="auto",
            temperature=0.6
        )
        
        msg_ia = response.choices[0].message

        # Lógica de Ferramentas
        if msg_ia.tool_calls:
            texto_resposta = _executar_ferramentas(user_id, msg_ia.tool_calls)
        else:
            texto_resposta = msg_ia.content.strip()

    except Exception as e:
        logger.error(f"Erro OpenAI: {e}")
        texto_resposta = "⚠️ Falha na conexão com o Mestre. Tente em instantes."

    # 5. Salva Interação (Coleção 'chats')
    _salvar_chat(user_id, "user", mensagem)
    _salvar_chat(user_id, "assistant", texto_resposta)
    
    return texto_resposta

# --- Funções Internas de Apoio ---

def _executar_ferramentas(user_id: str, tool_calls: list) -> str:
    """Traduz as decisões da IA em ações no banco de dados."""
    respostas = []
    for tool in tool_calls:
        try:
            nome_func = tool.function.name
            args = json.loads(tool.function.arguments)
            
            if nome_func == "salvar_nova_dieta":
                if salvar_plano(user_id, "dieta", args):
                    respostas.append("🥗 Protocolo nutricional atualizado com sucesso.")
            
            elif nome_func == "salvar_novo_treino":
                if salvar_plano(user_id, "treino", args):
                    respostas.append("⚔️ Cronograma de treinos registrado no seu perfil.")
        except Exception as e:
            logger.error(f"Erro Tool {tool.function.name}: {e}")
            
    return "\n".join(respostas) if respostas else "⚠️ Não consegui salvar o protocolo agora."

def _buscar_historico(user_id: str, limite: int) -> List[Dict]:
    if not mongo_db: return []
    cursor = mongo_db["chats"].find({"user_id": str(user_id)}).sort("timestamp", DESCENDING).limit(limite)
    msgs = [{"role": doc["role"], "content": doc["content"]} for doc in cursor]
    return msgs[::-1]

def _salvar_chat(user_id: str, role: str, content: str):
    if mongo_db:
        mongo_db["chats"].insert_one({
            "user_id": str(user_id),
            "role": role,
            "content": content,
            "timestamp": datetime.now()
        })