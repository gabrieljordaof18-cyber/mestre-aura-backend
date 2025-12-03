import os
import logging
from typing import List, Dict, Any
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

# Carrega variáveis
load_dotenv()

# Importações internas
from data_user import carregar_memoria, salvar_memoria, obter_status_fisiologico
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
    
    # Dados de Gamificação e Economia (Novos)
    xp = jogador.get("experiencia", 0)
    nivel = jogador.get("nivel", 1)
    coins = jogador.get("saldo_coins", 0) # Assumindo que salvamos aqui ou no mongo

    # 2. Monta o Prompt de Sistema (A Personalidade)
    prompt_sistema = {
        "role": "system", 
        "content": (
            f"Você é o Mestre da AURA, uma IA de alta performance esportiva.\n"
            f"Atleta: {jogador.get('nome', 'Atleta')}\n"
            f"Status: Nível {nivel} | {xp} XP | 💎 {coins} Aura Coins\n"
            f"Biometria Atual: {dados_fisiologicos}\n"
            f"Diretriz: Seja breve (max 2 frases), técnico, motivador e use emojis com moderação."
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

    # --- COMANDO PARA IA (OpenAI) ---
    else:
        try:
            if client:
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=mensagens_para_enviar,
                    max_tokens=1000,
                    temperature=0.7
                )
                texto_resposta = resp.choices[0].message.content.strip()
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
    # Pega apenas os últimos 'limite' itens
    recortes = historico[-limite:] if len(historico) >= limite else historico
    
    for item in recortes:
        # Formato Novo
        if "role" in item and "content" in item:
            historico_limpo.append({"role": item["role"], "content": item["content"]})
        # Formato Antigo (Legado)
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
    
    # Mantém apenas os últimos 20 turnos para economizar espaço
    if len(memoria["historico"]) > 20:
        memoria["historico"] = memoria["historico"][-20:]
        
    salvar_memoria(memoria)