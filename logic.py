# logic.py
import os
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv # Importante para ler o arquivo .env

# Carrega as variáveis do arquivo .env
load_dotenv()

# IMPORTAÇÕES DA FASE 2
from data_user import carregar_memoria, salvar_memoria, obter_status_fisiologico
from logic_gamificacao import gerar_missoes_diarias
from logic_feedback import gerar_feedback_emocional

# Configuração da OpenAI
client = None
api_key = os.getenv("OPENAI_API_KEY") # Pega do .env de forma segura

if api_key:
    try:
        client = OpenAI(api_key=api_key)
    except Exception as e:
        print(f"⚠️ Erro ao iniciar cliente OpenAI: {e}")
        client = None

# ======================================================
# 💬 CÉREBRO DA IA (PROCESSAMENTO DE COMANDO)
# ======================================================
def processar_comando(mensagem):
    # 1. Carrega dados atualizados
    memoria = carregar_memoria()
    jogador = memoria.get("jogador", {})
    
    # Pega o histórico bruto (pode conter formatos antigos misturados com novos)
    historico_bruto = memoria.get("historico", [])
    
    # Pega dados fisiológicos
    dados_fisiologicos = obter_status_fisiologico()

    # 2. Monta o Contexto (System Prompt)
    mensagens_para_enviar = [
        {"role": "system", "content": "Você é o Mestre da AURA — núcleo de consciência da IA esportiva AURA Performance."},
        {"role": "system", "content": f"O jogador se chama {jogador.get('nome', 'Atleta')}."},
        {"role": "system", "content": f"Dados atuais: {dados_fisiologicos}"},
        {"role": "system", "content": "Seja breve (max 2 frases), técnico e motivador."}
    ]

    # 3. TRADUTOR DE HISTÓRICO (A Correção do Erro 400)
    # Pegamos as últimas 4 mensagens e garantimos que estão no formato certo
    for item in historico_bruto[-4:]:
        # Se for formato novo (já tem role)
        if "role" in item and "content" in item:
            mensagens_para_enviar.append({
                "role": item["role"], 
                "content": item["content"]
            })
        # Se for formato antigo (tem mensagem/resposta)
        elif "mensagem" in item and "resposta" in item:
            mensagens_para_enviar.append({"role": "user", "content": item["mensagem"]})
            mensagens_para_enviar.append({"role": "assistant", "content": item["resposta"]})

    # Adiciona a mensagem atual do usuário
    mensagens_para_enviar.append({"role": "user", "content": mensagem})

    # 4. Lógica de Resposta (Comandos Locais ou OpenAI)
    texto_resposta = "..."
    msg_lower = mensagem.lower()

    # --- COMANDOS RÁPIDOS (Sem gastar IA) ---
    if "missões" in msg_lower or "missoes" in msg_lower:
        missoes = memoria.get("gamificacao", {}).get("missoes_ativas", [])
        pendentes = [m['descricao'] for m in missoes if not m['concluida']]
        if pendentes:
            texto_resposta = f"Missões pendentes: {', '.join(pendentes)}."
        else:
            texto_resposta = "Todas as missões concluídas!"
            
    elif "xp" in msg_lower or "nível" in msg_lower:
        xp = jogador.get("experiencia", 0)
        nv = jogador.get("nivel", 1)
        texto_resposta = f"Nível {nv} | {xp} XP."

    # --- COMANDO PARA IA ---
    else:
        try:
            if client:
                resp = client.chat.completions.create(
                    model="gpt-4o-mini", # ou gpt-3.5-turbo
                    messages=mensagens_para_enviar,
                    max_tokens=150
                )
                texto_resposta = resp.choices[0].message.content.strip()
            else:
                texto_resposta = "Modo Offline: Verifique sua chave API no .env"
        except Exception as e:
            print(f"Erro OpenAI Detalhado: {e}")
            texto_resposta = "Estou offline. (Verifique o terminal para detalhes do erro)"

    # 5. Salva no Histórico (Já no formato NOVO para não dar erro futuro)
    # Nota: Salvamos user e assistant separados para facilitar a leitura futura
    memoria["historico"].append({"role": "user", "content": mensagem})
    memoria["historico"].append({"role": "assistant", "content": texto_resposta})
    
    # Limita histórico para não crescer infinitamente
    if len(memoria["historico"]) > 20:
        memoria["historico"] = memoria["historico"][-20:]
        
    salvar_memoria(memoria)

    return texto_resposta