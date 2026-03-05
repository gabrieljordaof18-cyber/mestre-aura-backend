import logging
from typing import Dict, Any, Optional
from datetime import datetime

# Importações da Nova Arquitetura
from data_user import carregar_memoria

# Configuração de Logs
logger = logging.getLogger("AURA_LOGIC_FEEDBACK")

# ======================================================
# 🧭 NÚCLEO NARRATIVO — Feedback Adaptativo Robust 3.0
# ======================================================

def gerar_feedback_emocional(user_id: str) -> str:
    """
    Analisa biomarcadores e o novo contexto de treinos robustos para gerar 
    uma resposta narrativa técnica e impactante para o Frontend.
    """
    if not user_id:
        return "Aguardando identificação do atleta..."

    # 1. Carrega Perfil (Sincronizado com o ID limpo do Render)
    memoria = carregar_memoria(user_id)
    if not memoria:
        return "Sincronizando sistemas de análise bio-rítmica..."
    
    # [AURA FIX] Busca o status_atual estruturado pelo novo data_sensores
    dados_fisio = memoria.get("status_atual", {})
    homeostase = memoria.get("homeostase", {})
    score_geral = homeostase.get("score", 0)
    objetivo = memoria.get("objetivo", "Performance")
    esportes = memoria.get("esportes_favoritos", [])

    # 2. Extração Segura de Dados (Campos unificados do Atlas)
    energia = float(dados_fisio.get("recuperacao", 0))
    sono = float(dados_fisio.get("sono_horas", 0))
    hrv = float(dados_fisio.get("hrv_valor", 0))
    fadiga = float(dados_fisio.get("fadiga", 0))

    # 3. Verificação de Dados Ausentes (Cold Start)
    if score_geral == 0 and energia == 0:
        return "Seus sinais vitais ainda não foram mapeados. Sincronize seus dispositivos para iniciar sua evolução robusta."

    insights = []

    # 4. Insights de Homeostase e Prontidão (Prioridade 1)
    if score_geral >= 88:
        insights.append("Sua fisiologia está em ápice — modo de alta performance ativado para o novo ciclo.")
    elif score_geral > 0 and score_geral <= 45:
        insights.append("Fadiga neural detectada. O Mestre recomenda reduzir o volume de exercícios hoje.")

    # 5. Insights de Volume e Treino Híbrido (Prioridade 2)
    # Se a fadiga estiver alta e o usuário faz esportes de endurance
    if fadiga > 60 and any(e in ["Corrida", "Ciclismo", "Natação"] for e in esportes):
        insights.append("Carga cardiovascular acumulada alta; foque em técnica de musculação isolada.")
    elif energia >= 90 and score_geral > 70:
        insights.append(f"Glicogênio e prontidão neural excelentes para seu foco em {objetivo}.")

    # 6. Insights de Recuperação e HRV (Prioridade 3)
    if hrv > 0 and len(insights) < 2:
        if hrv < 35:
            insights.append("HRV baixo — seu sistema nervoso pede cautela com treinos de 10 exercícios.")
        elif hrv > 75:
            insights.append("Sinal verde: sua variabilidade cardíaca indica resiliência para carga máxima.")

    # 7. Fallback de Estabilidade
    if not insights:
        insights.append("Sistemas operando em estabilidade técnica. Mantenha a constância na sua planilha.")

    # 8. Formatação Final (Foco em clareza para mobile)
    mensagem = " ".join(insights[:2])
    
    # Corte de segurança para evitar quebra de layout no Base44
    if len(mensagem) > 170:
        mensagem = mensagem[:167] + "..."

    logger.info(f"💬 [FEEDBACK] User: {user_id} | Score: {score_geral}% | Msg: {mensagem}")
    return mensagem

# --- Função Auxiliar de Navegação de Dados ---

def _extrair_valor(dados: dict, chave: str, subchave: str, padrao: float) -> float:
    """Navega no dicionário de sensores de forma robusta."""
    if not dados: return float(padrao)
    
    raw = dados.get(chave, padrao)
    try:
        if isinstance(raw, dict):
            return float(raw.get(subchave, padrao))
        return float(raw)
    except (ValueError, TypeError):
        return float(padrao)