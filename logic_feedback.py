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
    uma resposta narrativa curta e impactante para o Frontend (Base44).
    """
    if not user_id:
        return "Aguardando identificação do atleta..."

    # 1. Carrega Perfil (Sincronizado com o ID limpo do Render)
    memoria = carregar_memoria(user_id)
    if not memoria:
        return "Sincronizando sistemas de análise bio-rítmica..."
    
    # [AURA FIX] Ajustado para 'status_atual' para refletir o seu MongoDB Atlas
    dados_fisio = memoria.get("status_atual", {})
    homeostase = memoria.get("homeostase", {})
    score_geral = homeostase.get("score", 0)

    # 2. Extração Segura de Dados (Sincronização com os campos manuais do Atlas)
    # No seu banco: 'recuperacao' mapeia para energia, 'sono' para horas.
    energia = float(dados_fisio.get("recuperacao", 0))
    sono = _extrair_valor(dados_fisio, "sono", "horas", 0)
    hrv = _extrair_valor(dados_fisio, "hrv", "valor", 0)

    # 3. Verificação de Dados Ausentes (Cold Start)
    # Se o score de homeostase e a energia estiverem zerados, o sistema pede sync
    if score_geral == 0 and energia == 0:
        return "Seus sinais vitais ainda não foram mapeados. Sincronize seus dispositivos para iniciar sua evolução."

    insights = []

    # 4. Insights Baseados no Score de Homeostase (Prioridade 1)
    if score_geral >= 85:
        insights.append("Sua fisiologia está em ápice — modo de alta performance ativado.")
    elif score_geral > 0 and score_geral <= 40:
        insights.append("Detectamos fadiga sistêmica elevada. Priorize a regeneração profunda hoje.")

    # 5. Insights de Energia / Recuperação (Prioridade 2)
    if energia > 0 and len(insights) < 2:
        if energia >= 90:
            insights.append("Prontidão neural e estoques de glicogênio excelentes.")
        elif energia < 50:
            insights.append("Reserva energética reduzida — hoje o foco deve ser técnica leve.")

    # 6. Insights de HRV e Bio-status (Prioridade 3)
    if hrv > 0 and len(insights) < 2:
        if hrv < 40:
            insights.append("HRV em declínio — seu sistema nervoso pede redução no volume de carga.")
        elif hrv > 80:
            insights.append("Sinal verde: recuperação autonômica acelerada detectada.")

    # 7. Fallback Caso não entre em faixas críticas
    if not insights:
        insights.append("Seus sistemas operam em estabilidade. Mantenha a constância e siga o plano.")

    # 8. Formatação Final (Estilo Direto e Eficaz para o Base44)
    mensagem = " ".join(insights[:2])
    
    # Corte de segurança para telas mobile (Prevenção de quebra de layout no Frontend)
    if len(mensagem) > 160:
        mensagem = mensagem[:157] + "..."

    logger.info(f"💬 Feedback gerado para {user_id}: {mensagem}")
    return mensagem

# --- Função Auxiliar de Navegação de Dados ---

def _extrair_valor(dados: dict, chave: str, subchave: str, padrao: float) -> float:
    """Navega no dicionário de sensores lidando com campos aninhados ou diretos."""
    if not dados: return float(padrao)
    
    raw = dados.get(chave, padrao)
    try:
        if isinstance(raw, dict):
            return float(raw.get(subchave, padrao))
        return float(raw)
    except (ValueError, TypeError):
        return float(padrao)