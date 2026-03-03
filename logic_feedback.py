import logging
from typing import Dict, Any, Optional
from datetime import datetime

# Importações da Nova Arquitetura
from data_user import carregar_memoria

# Configuração de Logs
logger = logging.getLogger("AURA_LOGIC_FEEDBACK")

# ======================================================
# 🧭 NÚCLEO NARRATIVO — Feedback Adaptativo (SaaS)
# ======================================================

def gerar_feedback_emocional(user_id: str) -> str:
    """
    Analisa os biomarcadores e o score de homeostase para gerar 
    uma resposta narrativa curta e impactante.
    """
    if not user_id:
        return "Aguardando identificação do atleta..."

    memoria = carregar_memoria(user_id)
    if not memoria:
        return "Sincronizando sistemas de análise bio-rítmica..."
    
    dados_fisio = memoria.get("dados_fisiologicos", {})
    homeostase = memoria.get("homeostase", {})
    score_geral = homeostase.get("score", 0)

    # 1. Extração Segura de Dados (Schema 2.0)
    energia = _extrair_valor(dados_fisio, "energia", "nivel", 0)
    sono = _extrair_valor(dados_fisio, "sono", "horas", 0)
    hrv = _extrair_valor(dados_fisio, "hrv", "valor", 0)

    # 2. Verificação de Dados Ausentes (Cold Start)
    if energia == 0 and sono == 0 and hrv == 0:
        return "Seus sinais vitais ainda não foram mapeados. Sincronize seus dispositivos para iniciar."

    insights = []

    # 3. Insights Baseados no Score de Homeostase (Prioridade 1)
    if score_geral >= 85:
        insights.append("Sua fisiologia está em ápice — modo de alta performance ativado.")
    elif score_geral <= 40:
        insights.append("Detectamos fadiga sistêmica. Priorize a regeneração profunda hoje.")

    # 4. Insights de Energia (Prioridade 2)
    if energia > 0 and len(insights) < 2:
        if energia >= 90:
            insights.append("Nível de glicogênio e prontidão neural excelentes.")
        elif energia < 50:
            insights.append("Reserva energética reduzida — considere um dia focado em técnica leve.")

    # 5. Insights de Sono e HRV (Prioridade 3)
    if hrv > 0 and len(insights) < 2:
        if hrv < 40:
            insights.append("HRV em declínio — seu sistema nervoso pede menos volume de carga.")
        elif hrv > 80:
            insights.append("Recuperação autonômica acelerada.")

    # 6. Fallback Caso não entre em faixas extremas
    if not insights:
        insights.append("Seus sistemas operam em estabilidade. Mantenha a constância do plano.")

    # 7. Formatação Final (Estilo Direto e Eficaz)
    mensagem = " ".join(insights[:2])
    
    # Corte de segurança para telas mobile (Prevenção de quebra de layout no Base44)
    if len(mensagem) > 160:
        mensagem = mensagem[:157] + "..."

    return mensagem

# --- Função Auxiliar de Navegação de Dados ---

def _extrair_valor(dados: dict, chave: str, subchave: str, padrao: float) -> float:
    """Navega no dicionário de sensores lidando com campos aninhados ou diretos."""
    raw = dados.get(chave, padrao)
    try:
        if isinstance(raw, dict):
            return float(raw.get(subchave, padrao))
        return float(raw)
    except (ValueError, TypeError):
        return float(padrao)