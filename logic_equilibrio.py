import logging
from datetime import datetime
from typing import Dict, Any, Optional

# Importações da Nova Arquitetura
from data_user import carregar_memoria, salvar_memoria

# Configuração de Logs
logger = logging.getLogger("AURA_LOGIC_EQUILIBRIO")

# ======================================================
# ⚙️ CONSTANTES E PESOS (BIOHACKING CORE)
# ======================================================
PESO_SONO = 0.4
PESO_ENERGIA = 0.3
PESO_HRV = 0.3

# ======================================================
# ⚖️ LÓGICA DE EQUILÍBRIO (HOMEOSTASE)
# ======================================================

def calcular_e_atualizar_equilibrio(user_id: str) -> Dict[str, Any]:
    """
    Analisa os biomarcadores do usuário e calcula o score de Homeostase.
    O resultado impacta diretamente a afinidade da IA e o feedback emocional.
    """
    if not user_id:
        logger.warning("⚠️ Tentativa de calcular equilíbrio sem user_id.")
        return {}

    # 1. Carrega memória do usuário (Multijogador)
    memoria = carregar_memoria(user_id)
    if not memoria:
        logger.error(f"❌ Usuário {user_id} não localizado para bio-análise.")
        return {}

    dados_fisio = memoria.get("dados_fisiologicos", {})
    
    # 2. Extração e Normalização de Dados (Schema 2.0)
    # Buscamos valores reais ou usamos padrões de segurança
    sono_val = _extrair_valor(dados_fisio, "sono", "horas", 7.0)
    hrv_val = _extrair_valor(dados_fisio, "hrv", "valor", 50.0)
    energia_val = _extrair_valor(dados_fisio, "energia", "nivel", 50.0)

    # 3. Algoritmo de Pontuação (Escala 0-100)
    
    # Sono: Ideal 8h. Abaixo de 4h é crítico.
    score_sono = max(0, min(100, (sono_val - 4) * 25))
    
    # HRV (Variabilidade Cardíaca): Proxy de recuperação do SNC.
    score_hrv = max(0, min(100, (hrv_val - 20) * 1.6))
    
    # Energia: Nível percebido ou calculado pelos sensores.
    score_energia = max(0, min(100, energia_val))

    # 4. Cálculo do Índice de Homeostase Ponderado
    harmonia = (score_sono * PESO_SONO) + (score_energia * PESO_ENERGIA) + (score_hrv * PESO_HRV)
    harmonia_final = int(round(harmonia))

    estado_str = _definir_estado(harmonia_final)

    # 5. Persistência no Perfil (Schema 2.0)
    memoria["homeostase"] = {
        "score": harmonia_final,
        "estado": estado_str,
        "componentes": {
            "corpo": int(score_hrv),
            "mente": int(score_sono), 
            "energia": int(score_energia)
        },
        "ultima_analise": datetime.now().isoformat() # Harmonia com o backend
    }
    
    # Salva os novos dados de saúde no MongoDB
    salvar_memoria(user_id, memoria)

    logger.info(f"⚖️ Homeostase calculada para {user_id}: {harmonia_final}% - {estado_str}")
    return memoria["homeostase"]

# --- Funções Auxiliares de Processamento ---

def _extrair_valor(dados: dict, chave: str, subchave: str, padrao: float) -> float:
    """Navega no dicionário de sensores lidando com campos aninhados[cite: 78, 79]."""
    raw = dados.get(chave, padrao)
    try:
        if isinstance(raw, dict):
            return float(raw.get(subchave, padrao))
        return float(raw)
    except (ValueError, TypeError):
        return padrao

def _definir_estado(score: int) -> str:
    """Define a categoria visual/narrativa baseada no score."""
    if score >= 85: return "Plena Harmonia 🌟"
    if score >= 65: return "Equilíbrio Estável ✅"
    if score >= 40: return "Atenção Necessária ⚠️"
    return "Desequilíbrio Crítico 🔴"