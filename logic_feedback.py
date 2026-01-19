import logging
from typing import Dict, Any, Optional
from data_user import carregar_memoria

# Configuração de Logs
logger = logging.getLogger("AURA_LOGIC_FEEDBACK")

# ======================================================
# 🧭 FUNÇÃO — Gerar Feedback Emocional (Contexto User)
# ======================================================

def gerar_feedback_emocional(user_id: str) -> str:
    """
    Gera uma mensagem curta, empática e acionável com base na energia,
    sono e HRV do jogador específico.
    """
    if not user_id:
        return "Aguardando identificação do atleta..."

    memoria = carregar_memoria(user_id)
    if not memoria:
        return "Iniciando protocolos de monitoramento..."
    
    dados_fisio = memoria.get("dados_fisiologicos", {})

    # 1. Extração Higienizada dos Dados
    # Usamos 0 como padrão para detectar se há dados reais
    energia = _extrair_valor(dados_fisio, "energia", "nivel", 0)
    sono = _extrair_valor(dados_fisio, "sono", "horas", 0)
    hrv = _extrair_valor(dados_fisio, "hrv", "valor", 0)

    # 2. Verificação de "Cold Start" (Usuário Novo sem dados)
    # Se tudo for zero, não adianta dar feedback.
    if energia == 0 and sono == 0:
        return "Sincronize seus dispositivos ou registre seu dia para receber insights."

    partes = []

    # 3. Análise de Energia (Se disponível)
    if energia > 0:
        if energia >= 90:
            partes.append("Energia ótima — aproveite para um treino técnico e pesado.")
        elif energia >= 75:
            partes.append("Boa energia — foque em qualidade de execução.")
        elif energia >= 60:
            partes.append("Energia moderada — priorize movimentos controlados.")
        else:
            partes.append("Baixa energia — considere recuperação ativa e sono extra.")

    # 4. Análise de Sono (Se disponível)
    if sono > 0:
        if sono >= 8:
            partes.append("Sono restaurador — recuperação muscular favorecida.")
        elif sono >= 7:
            partes.append("Sono aceitável — mantenha a hidratação.")
        else:
            partes.append("Sono abaixo do ideal — evite treinos extremos hoje.")

    # 5. Análise de HRV (Indicador de Stress)
    if hrv > 0:
        if hrv >= 80:
            partes.append("HRV alta — recuperação excelente.")
        elif hrv >= 60:
            partes.append("HRV estável — tendência positiva.")
        else:
            partes.append("HRV baixa — sistema nervoso sob stress, cuidado com a carga.")

    # 6. Síntese da Resposta
    if not partes:
        return "Monitorando seus sinais vitais..."

    mensagem = " ".join(partes[:2]) # Pega as 2 dicas mais importantes
    
    # Corte de segurança para UI (Mobile não quebrar layout)
    if len(mensagem) > 180:
        mensagem = mensagem[:177] + "..."

    return mensagem

# --- Função Auxiliar Local ---
def _extrair_valor(dados: dict, chave: str, subchave: str, padrao: float) -> float:
    """Extrai valor numérico lidando com dicionários ou valores diretos."""
    raw = dados.get(chave, padrao)
    try:
        if isinstance(raw, dict):
            return float(raw.get(subchave, padrao))
        return float(raw)
    except (ValueError, TypeError):
        return float(padrao)