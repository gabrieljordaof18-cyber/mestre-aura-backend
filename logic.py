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
# 🛠️ DEFINIÇÃO DAS FERRAMENTAS (ESTRUTURA AURA PRO)
# ======================================================

SCHEMA_EXERCICIO = {
    "type": "object",
    "properties": {
        "exercicio": {"type": "string", "description": "Nome DETALHADO do exercício. Para Cardio: especifique o tipo (ex: Corrida Intervalada, Longão, Natação Técnica)."},
        "series": {"type": "string", "description": "Ex: 4x (Deixe vazio apenas se for cardio contínuo)"},
        "reps": {"type": "string", "description": "Ex: 10-12, Falha, 15 (Deixe vazio se for cardio)"},
        "duracao": {"type": "string", "description": "Tempo, distância ou cadência. Ex: 45min, 5km, Tiro 400m"}
    },
    "required": ["exercicio"]
}

TOOLS_AURA = [
    {
        "type": "function",
        "function": {
            "name": "salvar_nova_dieta",
            "description": "Salva o plano alimentar detalhado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resumo_objetivo": {"type": "string", "description": "Ex: Cutting, 2000kcal"},
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
            "description": "Salva a rotina de treinos estruturada em tabela (Exercício, Séries, Reps, Duração).",
            "parameters": {
                "type": "object",
                "properties": {
                    "foco_atual": {"type": "string", "description": "Ex: Hipertrofia, Maratona, Híbrido"},
                    "dicas_tecnicas": {"type": "string", "description": "Dica técnica sobre execução ou intensidade"},
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
    """
    Recebe o texto do usuário, decide se usa resposta rápida ou IA,
    gera a resposta e salva no histórico.
    """
    # 1. Carrega dados atualizados (Contexto)
    memoria = carregar_memoria()
    jogador = memoria.get("jogador", {})
    historico_bruto = memoria.get("historico", [])
    dados_fisiologicos = obter_status_fisiologico()
    
    # Dados de Gamificação e Economia
    xp = jogador.get("experiencia", 0)
    nivel = jogador.get("nivel", 1)
    coins = jogador.get("saldo_coins", 0)

    # 2. Monta o Prompt de Sistema (A Personalidade)
    prompt_sistema = {
        "role": "system", 
        "content": (
            f"Você é o Mestre da AURA, treinador de elite.\n"
            f"Atleta: {jogador.get('nome', 'Atleta')} | Nível {nivel}\n\n"
            f"REGRAS CRÍTICAS PARA CRIAÇÃO DE TREINO:\n"
            f"1. VOLUME ADAPTÁVEL: O número de exercícios deve seguir o pedido do usuário. Se ele pedir 'rápido', use 3-4. Se pedir 'pesado' ou 'fullbody', use 8-10. Se não especificar, use o padrão 5-7.\n"
            f"2. CARDIO INTELIGENTE: Nunca use apenas 'Corrida'. Especifique: 'Corrida Leve (Z2)', 'Tiros de 400m', 'Fartlek'. Use a coluna 'Duração' para tempo/distância.\n"
            f"3. ESTRUTURA: Preencha Séries e Reps para musculação. Preencha Duração para Cardio.\n"
            f"4. ATLETA MISTO: Se o usuário for híbrido, inclua musculação E cardio no mesmo dia conforme necessário.\n"
            f"5. DIETA: Calcule as calorias de cada refeição ao criar dietas.\n"
        )
    }

    # 3. Prepara Histórico (Limpo e Sanitizado)
    mensagens_para_enviar = [prompt_sistema] + _sanitizar_historico(historico_bruto, limite=4)
    mensagens_para_enviar.append({"role": "user", "content": mensagem})

    # 4. Lógica de Resposta
    texto_resposta = "..."
    msg_lower = mensagem.lower()

    # --- COMANDOS RÁPIDOS (Hardcoded para velocidade) ---
    if "missões" in msg_lower or "missoes" in msg_lower:
        missoes = memoria.get("gamificacao", {}).get("missoes_ativas", [])
        pendentes = [m['descricao'] for m in missoes if not m['concluida']]
        if pendentes:
            texto_resposta = f"🎯 Missões pendentes: {', '.join(pendentes)}."
        else:
            texto_resposta = "🏆 Todas as missões de hoje foram concluídas!"
            
    elif "xp" in msg_lower or "nível" in msg_lower:
        texto_resposta = f"📊 Você está no Nível {nivel} com {xp} XP acumulado."
        
    elif "moedas" in msg_lower or "coins" in msg_lower or "saldo" in msg_lower:
        texto_resposta = f"💰 Seu saldo atual é de {coins} Aura Coins. Visite o Mercado!"

    # --- COMANDO PARA IA (OpenAI + Function Calling) ---
    else:
        try:
            if client:
                # 1ª Chamada: IA pensa e decide se usa ferramenta
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=mensagens_para_enviar,
                    tools=TOOLS_AURA,
                    tool_choice="auto",
                    max_tokens=2000, # Aumentei para suportar treinos longos (Fullbody)
                    temperature=0.7
                )
                
                msg_ia = response.choices[0].message

                # Verificação: A IA decidiu chamar uma função?
                if msg_ia.tool_calls:
                    mensagens_para_enviar.append(msg_ia) # Adiciona a intenção ao histórico temporário
                    
                    for tool_call in msg_ia.tool_calls:
                        func_name = tool_call.function.name
                        args = json.loads(tool_call.function.arguments)
                        
                        resultado_tool = "Erro ao salvar."
                        
                        # Executa a função real no Backend
                        if func_name == "salvar_nova_dieta":
                            if atualizar_plano_mestre("dieta", args):
                                resultado_tool = "✅ Dieta (com Kcal) salva! Avise o usuário para ver o card de Dieta."
                            else:
                                resultado_tool = "Erro ao gravar no banco."
                                
                        elif func_name == "salvar_novo_treino":
                            if atualizar_plano_mestre("treino", args):
                                resultado_tool = "✅ Treino (Tabela Aura Grid) salvo! Avise o usuário para ver o card de Treino."
                            else:
                                resultado_tool = "Erro ao gravar no banco."

                        # Devolve o resultado para a IA formular a resposta final
                        mensagens_para_enviar.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": func_name,
                            "content": resultado_tool
                        })

                    # 2ª Chamada: IA gera o texto final para o usuário
                    final_response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=mensagens_para_enviar
                    )
                    texto_resposta = final_response.choices[0].message.content.strip()
                
                else:
                    # Se não houve chamada de função, apenas responde texto normal
                    texto_resposta = msg_ia.content.strip()

            else:
                texto_resposta = "⚠️ Modo Offline: IA não configurada."
        except Exception as e:
            logger.error(f"Erro OpenAI: {e}")
            texto_resposta = "⚠️ Estou recalibrando meus sistemas. Tente novamente."

    # 5. Salva no Histórico
    _atualizar_historico(memoria, mensagem, texto_resposta)

    return texto_resposta

# ======================================================
# ⚙️ FUNÇÕES AUXILIARES INTERNAS
# ======================================================

def _sanitizar_historico(historico: List[Dict], limite: int = 4) -> List[Dict]:
    """
    Converte formatos antigos de histórico para o padrão OpenAI e limita o tamanho.
    """
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
    """Adiciona nova interação e salva, mantendo o limite de tamanho."""
    if "historico" not in memoria:
        memoria["historico"] = []
        
    memoria["historico"].append({"role": "user", "content": usuario_msg})
    memoria["historico"].append({"role": "assistant", "content": ia_msg})
    
    if len(memoria["historico"]) > 20:
        memoria["historico"] = memoria["historico"][-20:]
        
    salvar_memoria(memoria)