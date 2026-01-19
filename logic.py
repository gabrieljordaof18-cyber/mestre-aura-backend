import os
import json
import logging
from typing import List, Dict, Any
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

# Carrega variáveis
load_dotenv()

# Importações internas da Nova Arquitetura
from data_user import carregar_memoria, salvar_memoria
# CORREÇÃO: Removemos a importação condicional quebrada da linha 14
# Importamos apenas o necessário para o chat otimizado
from data_manager import mongo_db, DESCENDING

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AURA_BRAIN")

# Configuração da OpenAI
client = None
api_key = os.getenv("OPENAI_API_KEY")

if api_key:
    try:
        client = OpenAI(api_key=api_key)
        logger.info("✅ Cliente OpenAI inicializado.")
    except Exception as e:
        logger.error(f"⚠️ Erro ao iniciar OpenAI: {e}")
        client = None
else:
    logger.warning("⚠️ OPENAI_API_KEY não encontrada no .env")

# ======================================================
# 🛠️ DEFINIÇÃO DAS FERRAMENTAS (SCHEMA DE FUNÇÕES)
# ======================================================

SCHEMA_EXERCICIO = {
    "type": "object",
    "properties": {
        "exercicio": {"type": "string", "description": "Nome do exercício. Ex: 'Supino Reto'."},
        "tipo": {"type": "string", "enum": ["forca", "cardio"]},
        "periodo": {"type": "string", "enum": ["unico", "manha", "tarde"]},
        "series": {"type": "string"},
        "reps": {"type": "string"},
        "duracao": {"type": "string"},
        "detalhes": {"type": "string"}
    },
    "required": ["exercicio", "tipo", "periodo"]
}

TOOLS_AURA = [
    {
        "type": "function",
        "function": {
            "name": "salvar_nova_dieta",
            "description": "Salva o plano alimentar estruturado no banco de dados.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resumo_objetivo": {"type": "string"},
                    "kcal_total": {"type": "string"},
                    "cafe_da_manha": {"type": "string"},
                    "kcal_cafe_da_manha": {"type": "string"},
                    "almoco": {"type": "string"},
                    "kcal_almoco": {"type": "string"},
                    "lanche": {"type": "string"},
                    "kcal_lanche": {"type": "string"},
                    "jantar": {"type": "string"},
                    "kcal_jantar": {"type": "string"},
                    "ceia_ou_suplementos": {"type": "string"},
                    "kcal_ceia": {"type": "string"}
                },
                "required": ["resumo_objetivo", "cafe_da_manha", "almoco", "jantar"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "salvar_novo_treino",
            "description": "Salva a rotina de treinos semanal no banco de dados.",
            "parameters": {
                "type": "object",
                "properties": {
                    "foco_atual": {"type": "string"},
                    "dicas_tecnicas": {"type": "string"},
                    "segunda": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "terca": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "quarta": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "quinta": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "sexta": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "sabado_domingo": {"type": "array", "items": SCHEMA_EXERCICIO}
                },
                "required": ["foco_atual", "segunda", "terca", "quarta", "quinta", "sexta"]
            }
        }
    }
]

# ======================================================
# 💬 CÉREBRO DA IA (PROCESSAMENTO COM TEXTO + CONTEXTO)
# ======================================================

def processar_comando(user_id: str, mensagem: str) -> str:
    """
    Recebe o ID do usuário e a mensagem.
    Gerencia contexto, chama OpenAI e executa funções no banco.
    """
    if not user_id:
        return "⚠️ Erro: Usuário não identificado."

    # 1. Carrega dados do Usuário (Contexto Rico)
    memoria = carregar_memoria(user_id)
    jogador = memoria.get("jogador", {})
    
    xp = jogador.get("experiencia", 0)
    nivel = jogador.get("nivel", 1)
    nome = jogador.get("nome", "Atleta")
    
    # Busca histórico recente na coleção de Chats (Otimizado)
    historico_recente = _buscar_historico_recente(user_id, limite=6)

    # 2. Prompt de Sistema (AURA COACH - MODO HÍBRIDO)
    prompt_sistema = {
        "role": "system", 
        "content": (
            f"Você é o Mestre da AURA, treinador de elite.\n"
            f"Atleta: {nome} | Nível {nivel} | XP {xp}\n\n"
            f"DIRETRIZES:\n"
            f"1. Se o usuário pedir Dieta ou Treino, use as TOOLS (funções) imediatamente. NÃO escreva o treino no chat.\n"
            f"2. Para treinos híbridos (dois turnos), use 'periodo': 'manha' e 'periodo': 'tarde' nos exercícios.\n"
            f"3. Seja sucinto, motivador e técnico (estilo Biohacker/Estoico).\n"
        )
    }

    # 3. Montagem das Mensagens (Sistema + Histórico + Nova Msg)
    mensagens_para_enviar = [prompt_sistema] + historico_recente
    mensagens_para_enviar.append({"role": "user", "content": mensagem})

    # 4. Lógica de Resposta Rápida (Atalhos locais)
    texto_resposta = "..."
    msg_lower = mensagem.lower()

    if "missões" in msg_lower or "missoes" in msg_lower:
        # Atalho para não gastar token com leitura de missão simples
        missoes = memoria.get("gamificacao", {}).get("missoes_ativas", [])
        pendentes = [m['descricao'] for m in missoes if not m.get('concluida')]
        if pendentes:
            texto_resposta = f"🎯 Pendentes de hoje: {', '.join(pendentes)}."
        else:
            texto_resposta = "🏆 Todas as missões concluídas. Bom descanso."
            
    elif "xp" in msg_lower and len(msg_lower) < 10:
        texto_resposta = f"📊 Status Atual: Nível {nivel} ({xp} XP)."

    else:
        # 5. Chamada à OpenAI
        try:
            if client:
                response = client.chat.completions.create(
                    model="gpt-4o-mini", # Rápido e Eficiente
                    messages=mensagens_para_enviar,
                    tools=TOOLS_AURA,
                    tool_choice="auto",
                    max_tokens=1500,
                    temperature=0.7
                )
                
                msg_ia = response.choices[0].message

                # Verifica se a IA decidiu usar uma Ferramenta (Salvar Treino/Dieta)
                if msg_ia.tool_calls:
                    texto_resposta = _executar_ferramentas(user_id, msg_ia.tool_calls)
                else:
                    texto_resposta = msg_ia.content.strip()

            else:
                texto_resposta = "⚠️ IA Offline (Chave não configurada)."
        except Exception as e:
            logger.error(f"Erro OpenAI: {e}")
            texto_resposta = "⚠️ O Mestre está meditando (Erro de conexão). Tente novamente."

    # 6. Salva a interação no histórico (Coleção Chats)
    _salvar_mensagem_chat(user_id, "user", mensagem)
    _salvar_mensagem_chat(user_id, "assistant", texto_resposta)
    
    return texto_resposta

# ======================================================
# ⚙️ EXECUÇÃO DE FERRAMENTAS (BANCO DE DADOS)
# ======================================================

def _executar_ferramentas(user_id: str, tool_calls: list) -> str:
    """Executa as funções solicitadas pela IA no banco de dados."""
    # Importação tardia e correta para evitar ciclo
    from data_manager import salvar_plano 
    
    respostas = []
    
    for tool in tool_calls:
        func_name = tool.function.name
        try:
            args = json.loads(tool.function.arguments)
            
            if func_name == "salvar_nova_dieta":
                sucesso = salvar_plano(user_id, "dieta", args)
                if sucesso:
                    respostas.append("🥗 Protocolo alimentar atualizado e salvo no seu perfil.")
                else:
                    respostas.append("⚠️ Falha ao salvar dieta no banco.")

            elif func_name == "salvar_novo_treino":
                sucesso = salvar_plano(user_id, "treino", args)
                if sucesso:
                    respostas.append("💪 Novo protocolo de treino registrado no sistema.")
                else:
                    respostas.append("⚠️ Falha ao salvar treino no banco.")
                    
        except Exception as e:
            logger.error(f"Erro na tool {func_name}: {e}")
            respostas.append("⚠️ Erro ao processar solicitação estruturada.")

    return "\n".join(respostas)

# ======================================================
# 💾 GERENCIAMENTO DE CHAT (COLEÇÃO SEPARADA)
# ======================================================

def _buscar_historico_recente(user_id: str, limite: int = 6) -> List[Dict]:
    """Busca as últimas N mensagens da coleção 'chats'."""
    if mongo_db is None: return []
    
    try:
        cursor = mongo_db["chats"].find(
            {"user_id": str(user_id)}
        ).sort("timestamp", DESCENDING).limit(limite)
        
        # O banco retorna do mais novo para o mais velho, precisamos inverter para a IA ler na ordem certa
        msgs = []
        for doc in cursor:
            msgs.append({"role": doc["role"], "content": doc["content"]})
        
        return msgs[::-1] # Inverte a lista
    except Exception as e:
        logger.error(f"Erro ao ler chat: {e}")
        return []

def _salvar_mensagem_chat(user_id: str, role: str, content: str):
    """Salva uma mensagem na coleção 'chats'."""
    if mongo_db is None: return
    
    try:
        doc = {
            "user_id": str(user_id),
            "role": role,
            "content": content,
            "timestamp": datetime.now()
        }
        mongo_db["chats"].insert_one(doc)
    except Exception as e:
        logger.error(f"Erro ao salvar chat: {e}")