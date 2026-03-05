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
# 🛠️ FERRAMENTAS DO MESTRE (DIETAS E TREINOS ROBUSTOS)
# ======================================================

SCHEMA_EXERCICIO = {
    "type": "object",
    "properties": {
        "exercicio": {"type": "string", "description": "Nome do exercício ou atividade (Ex: Supino Reto, Corrida na Esteira, Natação)"},
        "tipo": {"type": "string", "enum": ["forca", "cardio", "endurance", "flexibilidade"]},
        "periodo": {"type": "string", "enum": ["unico", "manha", "tarde", "noite"]},
        "series": {"type": "string", "description": "Número de séries (Ex: 4)"},
        "reps": {"type": "string", "description": "Repetições ou tempo (Ex: 10-12 ou 45 seg)"},
        "distancia": {"type": "string", "description": "Para cardios (Ex: 5, 500, 2.5)"},
        "unidade": {"type": "string", "enum": ["km", "m", "min", "reps"], "description": "Unidade da distância ou volume"},
        "detalhes": {"type": "string", "description": "Dicas técnicas, cadência ou carga sugerida"}
    },
    "required": ["exercicio", "tipo", "periodo"]
}

TOOLS_AURA = [
    {
        "type": "function",
        "function": {
            "name": "salvar_nova_dieta",
            "description": "ESTRUTURA e SALVA um plano alimentar detalhado. Use sempre que o usuário pedir orientações nutricionais.",
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
            "description": "CRIA um cronograma SEMANAL ROBUSTO. DEVE conter de 5 a 10 itens por dia de treino. Deve integrar Musculação com os esportes favoritos do atleta (Corrida, Ciclismo, etc).",
            "parameters": {
                "type": "object",
                "properties": {
                    "foco_atual": {"type": "string", "description": "Ex: Hipertrofia com foco em Endurance"},
                    "dicas_tecnicas": {"type": "string", "description": "Conselhos gerais para a semana"},
                    "segunda": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "terca": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "quarta": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "quinta": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "sexta": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "sabado": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "domingo": {"type": "array", "items": SCHEMA_EXERCICIO}
                },
                "required": ["foco_atual", "segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
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

    # Mapeamento de dados do Perfil
    nome_atleta = memoria.get("nome", "Iniciado")
    nivel_atleta = memoria.get("nivel", 1)
    xp_atleta = memoria.get("xp_total", 0)
    objetivo_atleta = memoria.get("objetivo", "Performance Geral")
    esportes_atleta = memoria.get("esportes_favoritos", ["Musculação"])
    
    # Busca bio-status processado
    homeostase = memoria.get("homeostase", {})
    estado_bio = homeostase.get('estado', 'Estável')
    score_bio = homeostase.get('score', 50)
    
    # 2. Prompt do Sistema (Personalidade Evoluída do Mestre da Aura)
    prompt_sistema = {
        "role": "system", 
        "content": (
            f"Você é o MESTRE DA AURA. Treinador de elite, técnico e analítico.\n"
            f"Atleta: {nome_atleta} | Nível: {nivel_atleta}\n"
            f"Objetivo: {objetivo_atleta} | Esportes Favoritos: {', '.join(esportes_atleta)}\n"
            f"Estado Bio: {estado_bio} (Score: {score_bio})\n\n"
            f"DIRETRIZES TÉCNICAS:\n"
            f"1. TREINOS: Devem ser complexos e variados. Cada dia de treino deve ter entre 5 e 10 exercícios.\n"
            f"2. HIBRIDISMO: Se o atleta pratica Corrida, Ciclismo ou Natação, integre isso na planilha semanal de forma inteligente (Ex: Treino de perna + 20min de bike).\n"
            f"3. TOOLS: Use obrigatoriamente as TOOLS para Dietas e Treinos. NUNCA liste os exercícios no chat.\n"
            f"4. RESPOSTA PÓS-TOOL: Responda exatamente: 'Treino estruturado! Confira a seção 'Treinos' logo acima.' ou 'Dieta estruturada! Confira a seção 'Dieta' logo acima.'.\n"
            f"5. TOM: Se score bio < 40, reduza o volume e aumente o descanso. Se > 80, prescreva alta intensidade."
        )
    }

    # 3. Histórico e Mensagem Atual
    historico = _buscar_historico(user_id, limite=6)
    mensagens = [prompt_sistema] + historico + [{"role": "user", "content": mensagem}]

    # 4. Execução OpenAI
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

    # 5. Salva Interação
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
                if salvar_plano(user_id, "dieta", args):
                    respostas.append("Dieta estruturada! Confira a seção 'Dieta' logo acima.")
            
            elif nome_func == "salvar_novo_treino":
                if salvar_plano(user_id, "treino", args):
                    respostas.append("Treino estruturado! Confira a seção 'Treinos' logo acima.")
        except Exception as e:
            logger.error(f"Erro ao executar Tool {tool.function.name}: {e}")
            
    return "\n".join(respostas) if respostas else "⚠️ Falha ao registrar o protocolo. Tente novamente."

def _buscar_historico(user_id: str, limite: int) -> List[Dict]:
    if mongo_db is None: return []
    try:
        cursor = mongo_db["chats"].find({"user_id": str(user_id)}).sort("timestamp", DESCENDING).limit(limite)
        msgs = [{"role": doc["role"], "content": doc["content"]} for doc in cursor]
        return msgs[::-1]
    except Exception as e:
        logger.error(f"Erro ao buscar histórico: {e}")
        return []

def _salvar_chat(user_id: str, role: str, content: str):
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