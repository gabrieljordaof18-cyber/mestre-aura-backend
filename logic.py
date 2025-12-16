import os
import json
import logging
from typing import List, Dict, Any
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

# Carrega variáveis
load_dotenv()

# Importações internas
from data_user import carregar_memoria, salvar_memoria, obter_status_fisiologico
from data_manager import atualizar_plano_mestre
from logic_gamificacao import gerar_missoes_diarias
from logic_feedback import gerar_feedback_emocional

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
# 🛠️ DEFINIÇÃO DAS FERRAMENTAS (ESTRUTURA AURA HYBRID)
# ======================================================

SCHEMA_EXERCICIO = {
    "type": "object",
    "properties": {
        "exercicio": {
            "type": "string", 
            "description": "Nome do exercício ou Bloco. Ex: 'Supino' ou 'Natação - Série A'."
        },
        "tipo": {
            "type": "string", 
            "enum": ["forca", "cardio"],
            "description": "Selecione 'forca' para musculação/calistenia ou 'cardio' para corrida/bike/natação."
        },
        "periodo": {
            "type": "string", 
            "enum": ["unico", "manha", "tarde"],
            "description": "CRÍTICO PARA HÍBRIDOS: Use 'manha' ou 'tarde' para dividir dois treinos no mesmo dia. Use 'unico' se for apenas um."
        },
        "series": {
            "type": "string", 
            "description": "Ex: '4x' (Use apenas para força)."
        },
        "reps": {
            "type": "string", 
            "description": "Ex: '10-12' (Use apenas para força)."
        },
        "duracao": {
            "type": "string", 
            "description": "Tempo/Distância. Ex: '45min', '5km', 'Até a falha'."
        },
        "detalhes": {
            "type": "string", 
            "description": "OBRIGATÓRIO PARA CARDIO: Descreva aquecimento, série principal e desaquecimento aqui. Seja técnico."
        }
    },
    "required": ["exercicio", "tipo", "periodo"]
}

TOOLS_AURA = [
    {
        "type": "function",
        "function": {
            "name": "salvar_nova_dieta",
            "description": "Salva o plano alimentar.",
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
            "description": "Salva a rotina de treinos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "foco_atual": {"type": "string", "description": "Ex: Híbrido (Maratona + Força)"},
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
# 💬 CÉREBRO DA IA (PROCESSAMENTO DE COMANDO)
# ======================================================

def processar_comando(mensagem: str) -> str:
    # 1. Carrega dados (Contexto)
    memoria = carregar_memoria()
    jogador = memoria.get("jogador", {})
    historico_bruto = memoria.get("historico", [])
    
    xp = jogador.get("experiencia", 0)
    nivel = jogador.get("nivel", 1)
    coins = jogador.get("saldo_coins", 0)

    # 2. Prompt de Sistema (AURA COACH - MODO EFICIÊNCIA)
    prompt_sistema = {
        "role": "system", 
        "content": (
            f"Você é o Mestre da AURA, treinador de elite.\n"
            f"Atleta: {jogador.get('nome', 'Atleta')} | Nível {nivel}\n\n"
            f"REGRA DE OURO (ECONOMIA DE TOKENS):\n"
            f"Se o usuário pedir um treino ou dieta, VOCÊ DEVE USAR A FERRAMENTA IMEDIATAMENTE.\n"
            f"NÃO escreva o treino no chat. O aplicativo mostrará a tabela visualmente.\n"
            f"Sua prioridade é montar a estrutura JSON perfeita na ferramenta.\n\n"
            f"DIRETRIZES TÉCNICAS:\n"
            f"1. HÍBRIDOS: Se pedir dois treinos no dia, crie DOIS itens na lista: um com 'periodo': 'manha' e outro 'tarde'.\n"
            f"2. CARDIO: Use o campo 'detalhes' para explicar a série (Aquecimento, Tiros, etc).\n"
            f"3. FORÇA: Use séries e reps.\n"
        )
    }

    # 3. Histórico Sanitizado
    mensagens_para_enviar = [prompt_sistema] + _sanitizar_historico(historico_bruto, limite=6)
    mensagens_para_enviar.append({"role": "user", "content": mensagem})

    # 4. Lógica de Resposta
    texto_resposta = "..."
    msg_lower = mensagem.lower()

    # Atalhos Rápidos (Economia de API)
    if "missões" in msg_lower or "missoes" in msg_lower:
        missoes = memoria.get("gamificacao", {}).get("missoes_ativas", [])
        pendentes = [m['descricao'] for m in missoes if not m['concluida']]
        if pendentes:
            texto_resposta = f"🎯 Pendentes: {', '.join(pendentes)}."
        else:
            texto_resposta = "🏆 Tudo concluído por hoje!"
            
    elif "xp" in msg_lower:
        texto_resposta = f"📊 Nível {nivel} | {xp} XP."

    # IA (OpenAI)
    else:
        try:
            if client:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=mensagens_para_enviar,
                    tools=TOOLS_AURA,
                    tool_choice="auto",
                    max_tokens=3000, # Aumentado para garantir JSON Híbrido completo
                    temperature=0.7
                )
                
                msg_ia = response.choices[0].message

                # SE A IA CHAMAR UMA FUNÇÃO (FERRAMENTA)
                if msg_ia.tool_calls:
                    sucesso_total = False
                    
                    for tool_call in msg_ia.tool_calls:
                        func_name = tool_call.function.name
                        try:
                            args = json.loads(tool_call.function.arguments)
                            
                            if func_name == "salvar_nova_dieta":
                                if atualizar_plano_mestre("dieta", args):
                                    sucesso_total = True
                                    texto_resposta = "🥗 Dieta montada e salva com sucesso!\n\n👉 Acesse o botão **'Minha Dieta'** no menu para ver seu plano alimentar completo."
                                    
                            elif func_name == "salvar_novo_treino":
                                if atualizar_plano_mestre("treino", args):
                                    sucesso_total = True
                                    texto_resposta = "💪 Treino Estruturado Criado!\n\n👉 Acesse o botão **'Meu Treino'** na tela inicial para visualizar sua nova rotina detalhada."
                        
                        except Exception as e:
                            logger.error(f"Erro ao executar tool {func_name}: {e}")
                            texto_resposta = "⚠️ Ocorreu um erro ao salvar o plano. Tente ser mais específico no pedido."

                    # TRUQUE DE MESTRE:
                    # Se salvou com sucesso, NÃO chamamos a OpenAI de novo para gerar texto.
                    # Retornamos direto a mensagem fixa. Isso economiza tokens e evita alucinação.
                    if not sucesso_total:
                        texto_resposta = "⚠️ Tive um problema ao acessar seu banco de dados. Tente novamente."
                
                else:
                    # Se for só bate-papo normal
                    texto_resposta = msg_ia.content.strip()

            else:
                texto_resposta = "⚠️ IA Offline."
        except Exception as e:
            logger.error(f"Erro OpenAI: {e}")
            texto_resposta = "⚠️ Erro de conexão neural. Tente novamente."

    _atualizar_historico(memoria, mensagem, texto_resposta)
    return texto_resposta

# ======================================================
# ⚙️ FUNÇÕES AUXILIARES
# ======================================================

def _sanitizar_historico(historico: List[Dict], limite: int = 4) -> List[Dict]:
    historico_limpo = []
    recortes = historico[-limite:] if len(historico) >= limite else historico
    for item in recortes:
        if "role" in item and "content" in item:
            historico_limpo.append({"role": item["role"], "content": item["content"]})
        elif "mensagem" in item and "resposta" in item:
            historico_limpo.append({"role": "user", "content": item["mensagem"]})
            historico_limpo.append({"role": "assistant", "content": item["resposta"]})
    return historico_limpo

def _atualizar_historico(memoria: Dict, usuario_msg: str, ia_msg: str):
    if "historico" not in memoria:
        memoria["historico"] = []
    memoria["historico"].append({"role": "user", "content": usuario_msg})
    memoria["historico"].append({"role": "assistant", "content": ia_msg})
    if len(memoria["historico"]) > 20:
        memoria["historico"] = memoria["historico"][-20:]
    salvar_memoria(memoria)