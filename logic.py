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
from data_manager import atualizar_plano_mestre # <--- NOVA IMPORTAÇÃO
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
# 🛠️ DEFINIÇÃO DAS FERRAMENTAS (FUNCTION CALLING)
# ======================================================

TOOLS_AURA = [
    {
        "type": "function",
        "function": {
            "name": "salvar_nova_dieta",
            "description": "Salva ou atualiza o plano alimentar (dieta) completo do usuário no banco de dados.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resumo_objetivo": {"type": "string", "description": "Ex: Hipertrofia limpa, 2800kcal"},
                    "cafe_da_manha": {"type": "string", "description": "Itens do café da manhã"},
                    "almoco": {"type": "string", "description": "Itens do almoço"},
                    "lanche": {"type": "string", "description": "Itens do lanche da tarde/pré-treino"},
                    "jantar": {"type": "string", "description": "Itens do jantar"},
                    "ceia_ou_suplementos": {"type": "string", "description": "Última refeição ou suplementação"}
                },
                "required": ["resumo_objetivo", "cafe_da_manha", "almoco", "jantar"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "salvar_novo_treino",
            "description": "Salva ou atualiza a rotina de treinos do usuário no banco de dados.",
            "parameters": {
                "type": "object",
                "properties": {
                    "foco_atual": {"type": "string", "description": "Ex: Força, Resistência, ABC..."},
                    "segunda": {"type": "string"},
                    "terca": {"type": "string"},
                    "quarta": {"type": "string"},
                    "quinta": {"type": "string"},
                    "sexta": {"type": "string"},
                    "sabado_domingo": {"type": "string", "description": "Treino de fim de semana ou descanso"},
                    "dicas_tecnicas": {"type": "string", "description": "Dica geral para a semana"}
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
            f"Você é o Mestre da AURA, uma IA de alta performance esportiva.\n"
            f"Atleta: {jogador.get('nome', 'Atleta')}\n"
            f"Status: Nível {nivel} | {xp} XP | 💎 {coins} Aura Coins\n"
            f"Biometria Atual: {dados_fisiologicos}\n"
            f"PODER ESPECIAL: Se o usuário pedir para criar/mudar dieta ou treino, CHAME a função correspondente (salvar_nova_dieta ou salvar_novo_treino) imediatamente.\n"
            f"Diretriz: Seja breve, técnico e motivador."
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
                    max_tokens=1000,
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
                                resultado_tool = "✅ Dieta salva no banco de dados com sucesso! Avise o usuário para clicar no botão DIETA."
                            else:
                                resultado_tool = "Erro ao gravar no banco."
                                
                        elif func_name == "salvar_novo_treino":
                            if atualizar_plano_mestre("treino", args):
                                resultado_tool = "✅ Treino salvo no banco de dados com sucesso! Avise o usuário para clicar no botão TREINO."
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