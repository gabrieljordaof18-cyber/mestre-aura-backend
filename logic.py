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
            "description": "Nome do exercício ou Bloco do treino. Ex: 'Supino Reto' ou 'Natação - Série Principal'."
        },
        "tipo": {
            "type": "string", 
            "enum": ["forca", "cardio", "hibrido"],
            "description": "Define se é força (musculação/calistenia) ou cardio (corrida/bike/natação)."
        },
        "series": {
            "type": "string", 
            "description": "Ex: '4x'. Se for cardio, use para blocos (Ex: '10x'). Deixe vazio se for contínuo."
        },
        "reps": {
            "type": "string", 
            "description": "Ex: '10-12'. Se for cardio, use para distâncias parciais (Ex: '50m')."
        },
        "duracao": {
            "type": "string", 
            "description": "Tempo total ou distância total. Ex: '45min', '5km', 'Ate a falha'."
        },
        "detalhes": {
            "type": "string", 
            "description": "CAMPO CRÍTICO PARA CARDIO. Descreva a estrutura técnica. Ex: 'Aquecimento: 200m leve + Educativo. Principal: 10x50m forte c/ 30s descanso.'"
        },
        "periodo": {
            "type": "string", 
            "enum": ["unico", "manha", "tarde", "noite"],
            "description": "Use para treinos híbridos (dois turnos)."
        }
    },
    "required": ["exercicio", "tipo"]
}

TOOLS_AURA = [
    {
        "type": "function",
        "function": {
            "name": "salvar_nova_dieta",
            "description": "Salva o plano alimentar detalhado com macros calculados.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resumo_objetivo": {"type": "string", "description": "Ex: Cutting Agressivo, 1800kcal"},
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
            "description": "Salva a rotina de treinos estruturada (Híbrida, Musculação ou Cardio).",
            "parameters": {
                "type": "object",
                "properties": {
                    "foco_atual": {"type": "string", "description": "Ex: Triathlon Short, Hipertrofia + Corrida, Fullbody"},
                    "dicas_tecnicas": {"type": "string", "description": "Dica técnica global sobre intensidade e recuperação."},
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

    # 2. Prompt de Sistema (AURA COACH PRO)
    prompt_sistema = {
        "role": "system", 
        "content": (
            f"Você é o Mestre da AURA, treinador de elite especialista em periodização híbrida.\n"
            f"Atleta: {jogador.get('nome', 'Atleta')} | Nível {nivel}\n\n"
            f"DIRETRIZES DE TREINO (IMPORTANTE):\n"
            f"1. CLASSIFICAÇÃO: Para cada exercício, defina 'tipo': 'forca' (musculação) ou 'cardio' (corrida/natação/bike).\n"
            f"2. CARDIO COMPLEXO: Não use apenas 'Corrida 30min'. Quebre o treino. Use o campo 'detalhes' para explicar o protocolo (Ex: '10 min aquecimento Z1 + 5x 1km forte Z4 + Desaquecimento').\n"
            f"3. TREINO HÍBRIDO (DOIS TURNOS): Se o usuário pedir 'manhã corrida e tarde musculação', crie DOIS itens na lista do dia. Marque 'periodo': 'manha' no primeiro e 'periodo': 'tarde' no segundo.\n"
            f"4. MUSCULAÇÃO: Mantenha o padrão Séries x Reps. Se for 'Fullbody', gere 8-10 exercícios variados.\n"
            f"5. VOLUME: Se o usuário não especificar, use 5-7 exercícios para força e 1 bloco detalhado para cardio.\n"
        )
    }

    # 3. Histórico Sanitizado
    mensagens_para_enviar = [prompt_sistema] + _sanitizar_historico(historico_bruto, limite=6)
    mensagens_para_enviar.append({"role": "user", "content": mensagem})

    # 4. Lógica de Resposta
    texto_resposta = "..."
    msg_lower = mensagem.lower()

    # Atalhos Rápidos
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
                    max_tokens=2500, # Aumentado para suportar detalhes técnicos
                    temperature=0.7
                )
                
                msg_ia = response.choices[0].message

                if msg_ia.tool_calls:
                    mensagens_para_enviar.append(msg_ia) 
                    
                    for tool_call in msg_ia.tool_calls:
                        func_name = tool_call.function.name
                        args = json.loads(tool_call.function.arguments)
                        
                        resultado_tool = "Erro ao processar."
                        
                        if func_name == "salvar_nova_dieta":
                            if atualizar_plano_mestre("dieta", args):
                                resultado_tool = "✅ Dieta salva! Peça para o usuário clicar em 'Minha Dieta'."
                            else:
                                resultado_tool = "Erro de banco de dados."
                                
                        elif func_name == "salvar_novo_treino":
                            if atualizar_plano_mestre("treino", args):
                                resultado_tool = "✅ Treino Híbrido Salvo! Peça para o usuário clicar em 'Meu Treino' para ver os detalhes técnicos."
                            else:
                                resultado_tool = "Erro de banco de dados."

                        mensagens_para_enviar.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": func_name,
                            "content": resultado_tool
                        })

                    final_response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=mensagens_para_enviar
                    )
                    texto_resposta = final_response.choices[0].message.content.strip()
                
                else:
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