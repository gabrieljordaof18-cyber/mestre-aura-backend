import os
import json
import logging
from typing import List, Dict, Any
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

# Importações da Nova Arquitetura
from data_user import carregar_memoria
# [AURA FIX] Importação explícita para garantir sincronização com Render/Atlas
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
        # [AURA FIX] Inicialização robusta do cliente OpenAI
        client = OpenAI(api_key=api_key)
        logger.info("✅ Mestre da Aura inicializado via OpenAI com sucesso.")
    except Exception as e:
        logger.error(f"⚠️ Falha crítica ao iniciar Mestre da Aura: {e}")
else:
    logger.warning("⚠️ OPENAI_API_KEY ausente no .env do Render. O chat ficará offline.")

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
            "description": "ESTRUTURA e SALVA um plano alimentar completo no banco de dados. Use sempre que o usuário pedir para montar, sugerir ou alterar uma dieta.",
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
            "description": "ESTRUTURA e SALVA uma rotina de exercícios semanal no banco de dados. Use sempre que o usuário pedir para montar, sugerir ou organizar um treino.",
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
    if not user_id: return "⚠️ Erro de identificação do atleta."

    # 1. Carrega Contexto Real do MongoDB (Sincronizado com Render/Base44)
    memoria = carregar_memoria(user_id)
    if not memoria:
        return "⚠️ Não encontrei seu perfil. Certifique-se de estar logado corretamente."

    # [AURA FIX] Ajustado para ler campos da raiz conforme seu documento manual no Atlas
    nome_atleta = memoria.get("nome", "Iniciado")
    nivel_atleta = memoria.get("nivel", 1)
    xp_atleta = memoria.get("xp_total", 0)
    objetivo_atleta = memoria.get("objetivo", "Performance Geral")
    
    # Busca bio-status processado
    homeostase = memoria.get("homeostase", {})
    estado_bio = homeostase.get('estado', 'Estável')
    score_bio = homeostase.get('score', 50)
    
    # 2. Prompt do Sistema (Personalidade do Mestre da Aura)
    prompt_sistema = {
        "role": "system", 
        "content": (
            f"Você é o MESTRE DA AURA. Treinador técnico, estoico e direto.\n"
            f"Atleta: {nome_atleta} | Nível: {nivel_atleta} (XP: {xp_atleta})\n"
            f"Objetivo Declarado: {objetivo_atleta}\n"
            f"Estado Biofísico: {estado_bio} (Score: {score_bio})\n\n"
            f"DIRETRIZES DE RESPOSTA:\n"
            f"1. Para montar Dietas ou Treinos, você DEVE usar obrigatoriamente as TOOLS. Não escreva o plano no chat.\n"
            f"2. Após usar uma TOOL, sua resposta de texto deve ser EXATAMENTE: 'Treino estruturado! Confira a seção 'Treinos' logo acima.' ou 'Dieta estruturada! Confira a seção 'Dieta' logo acima.'.\n"
            f"3. Adapte o tom: Se o score biofísico for baixo (<40), seja protetor. Se alto (>80), seja motivador técnico.\n"
            f"4. Respostas curtas (máximo 3 parágrafos).\n"
            f"5. Você mantém o contexto da conversa anterior."
        )
    }

    # 3. Histórico e Mensagem Atual (Sincronização de contexto)
    historico = _buscar_historico(user_id, limite=6)
    mensagens = [prompt_sistema] + historico + [{"role": "user", "content": mensagem}]

    # 4. Execução OpenAI (Geração de resposta ou chamada de função)
    try:
        if client is None: return "⚠️ O Mestre está em meditação profunda (Sistema Offline)."
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=mensagens,
            tools=TOOLS_AURA,
            tool_choice="auto",
            temperature=0.6
        )
        
        msg_ia = response.choices[0].message

        # Lógica de Ferramentas (Actions)
        if msg_ia.tool_calls:
            texto_resposta = _executar_ferramentas(user_id, msg_ia.tool_calls)
        else:
            texto_resposta = msg_ia.content.strip()

    except Exception as e:
        logger.error(f"Erro OpenAI para o user {user_id}: {e}")
        texto_resposta = "⚠️ O Mestre teve uma interrupção na conexão neural. Tente novamente."

    # 5. Salva Interação (Persistência na coleção 'chats' do MongoDB Atlas)
    _salvar_chat(user_id, "user", mensagem)
    _salvar_chat(user_id, "assistant", texto_resposta)
    
    return texto_resposta

# --- Funções Internas de Apoio ---

def _executar_ferramentas(user_id: str, tool_calls: list) -> str:
    """Traduz as decisões da IA em ações reais no banco de dados."""
    respostas = []
    for tool in tool_calls:
        try:
            nome_func = tool.function.name
            args = json.loads(tool.function.arguments)
            
            if nome_func == "salvar_nova_dieta":
                # Salva o plano estruturado na coleção 'plans' via data_manager
                if salvar_plano(user_id, "dieta", args):
                    # [AURA FIX] Retorno padronizado para o Chat
                    respostas.append("Dieta estruturada! Confira a seção 'Dieta' logo acima.")
            
            elif nome_func == "salvar_novo_treino":
                if salvar_plano(user_id, "treino", args):
                    # [AURA FIX] Retorno padronizado para o Chat
                    respostas.append("Treino estruturado! Confira a seção 'Treinos' logo acima.")
        except Exception as e:
            logger.error(f"Erro ao executar Tool {tool.function.name}: {e}")
            
    return "\n".join(respostas) if respostas else "⚠️ Falha ao registrar o protocolo. Tente novamente."

def _buscar_historico(user_id: str, limite: int) -> List[Dict]:
    """Recupera as últimas mensagens da coleção 'chats' para dar contexto à IA."""
    if mongo_db is None: return []
    try:
        cursor = mongo_db["chats"].find({"user_id": str(user_id)}).sort("timestamp", DESCENDING).limit(limite)
        msgs = [{"role": doc["role"], "content": doc["content"]} for doc in cursor]
        return msgs[::-1]
    except Exception as e:
        logger.error(f"Erro ao buscar histórico: {e}")
        return []

def _salvar_chat(user_id: str, role: str, content: str):
    """Persiste a conversa no MongoDB para memória de longo prazo."""
    if mongo_db is not None:
        try:
            mongo_db["chats"].insert_one({
                "user_id": str(user_id),
                "role": role,
                "content": content,
                "timestamp": datetime.now()
            })
        except Exception as e:
            logger.error(f"Erro ao salvar mensagem no chat: {e}")