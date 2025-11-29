import logging
from typing import Dict, Any, Optional
from data_user import carregar_memoria

# Configuração de Logs
logger = logging.getLogger("AURA_LOGIC_FEEDBACK")

# ======================================================
# 🧭 FUNÇÃO — Gerar Feedback Emocional Inteligente
# ======================================================

def gerar_feedback_emocional(memoria: Optional[Dict[str, Any]] = None) -> str:
    """
    Gera uma mensagem curta, empática e acionável com base na energia,
    sono, HRV e humor do jogador. Não altera histórico.
    """
    if memoria is None:
        memoria = carregar_memoria()
    
    dados_fisio = memoria.get("dados_fisiologicos", {})

    # 1. Extração Higienizada dos Dados (Padrão Sênior)
    energia = _extrair_valor(dados_fisio, "energia", "nivel", 50)
    sono = _extrair_valor(dados_fisio, "sono", "horas", 7.0)
    hrv = _extrair_valor(dados_fisio, "hrv", "valor", 0)

    partes = []

    # 2. Análise de Energia
    if energia >= 90:
        partes.append("Energia ótima — aproveite para um treino técnico e pesado hoje.")
    elif energia >= 75:
        partes.append("Boa energia — foque em qualidade de execução.")
    elif energia >= 60:
        partes.append("Energia moderada — priorize movimentos compostos controlados.")
    else:
        partes.append("Baixa energia — considere recuperação ativa e sono extra.")

    # 3. Análise de Sono
    if sono >= 8:
        partes.append("Sono restaurador — recuperação muscular favorecida.")
    elif sono >= 7:
        partes.append("Sono aceitável — mantenha hidratação e proteína pós-treino.")
    else:
        partes.append("Sono abaixo do ideal — evite treinos extremamente intensos hoje.")

    # 4. Análise de HRV (Indicador de Stress)
    if hrv > 0: # Só comenta se tiver dados
        if hrv >= 80:
            partes.append("HRV alta — estado de recuperação excelente.")
        elif hrv >= 60:
            partes.append("HRV estável — tendência neutra/positiva.")
        else:
            partes.append("HRV baixa — sistema nervoso sob stress, cuidado com sobrecarga.")

    # 5. Síntese da Resposta
    mensagem = " ".join(partes[:3])
    
    # Corte de segurança para UI (Mobile)
    if len(mensagem) > 220:
        mensagem = mensagem[:217] + "..."

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