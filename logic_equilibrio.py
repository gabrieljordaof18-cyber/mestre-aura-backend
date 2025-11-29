import logging
from typing import Dict, Any, Union
from data_user import carregar_memoria, salvar_memoria
from data_global import carregar_memoria_global, salvar_memoria_global

# Configuração de Logs
logger = logging.getLogger("AURA_LOGIC_EQUILIBRIO")

# ======================================================
# ⚙️ CONSTANTES E PESOS
# ======================================================
PESO_SONO = 0.4
PESO_ENERGIA = 0.3
PESO_HRV = 0.3

# ======================================================
# ⚖️ LÓGICA DE EQUILÍBRIO (HOMEOSTASE)
# ======================================================

def calcular_e_atualizar_equilibrio() -> Dict[str, Any]:
    """
    Lê dados fisiológicos, calcula score de harmonia e sincroniza
    tanto na memória do usuário quanto na memória global da IA.
    """
    memoria = carregar_memoria()
    dados_fisio = memoria.get("dados_fisiologicos", {})
    
    # 1. Extração Segura de Dados (Normalização)
    sono_val = _extrair_valor(dados_fisio, "sono", "horas", 7.0)
    hrv_val = _extrair_valor(dados_fisio, "hrv", "valor", 50.0)
    energia_val = _extrair_valor(dados_fisio, "energia", "nivel", 50.0)

    # 2. Cálculo dos Scores Normalizados (0 a 100)
    
    # Sono: 8h = 100%, 4h = 0% (Clamp entre 0 e 100)
    score_sono = max(0, min(100, (sono_val - 4) * 25))
    
    # HRV: 80ms = 100%, 20ms = 0%
    score_hrv = max(0, min(100, (hrv_val - 20) * 1.6))
    
    # Energia: Já vem em 0-100 (Assumindo confiança no sensor)
    score_energia = max(0, min(100, energia_val))

    # 3. Score Final (Ponderado)
    harmonia = (score_sono * PESO_SONO) + (score_energia * PESO_ENERGIA) + (score_hrv * PESO_HRV)
    harmonia_final = int(round(harmonia))

    estado_str = _definir_estado(harmonia_final)

    # 4. Atualizar Memória Local (Para o Jogador ver no App)
    memoria["homeostase"] = {
        "score": harmonia_final,
        "estado": estado_str,
        "componentes": {
            "corpo": int(score_hrv),
            "mente": int(score_sono), # Sono como proxy de mente/descanso
            "energia": int(score_energia)
        }
    }
    salvar_memoria(memoria)

    # 5. Atualizar Memória Global (Para a IA lembrar no Chat)
    try:
        mg = carregar_memoria_global()
        
        # Garante que a estrutura existe (Programação Defensiva)
        if "homeostase" not in mg:
            mg["homeostase"] = {}
            
        mg["homeostase"]["score_harmonia"] = harmonia_final
        mg["homeostase"]["estado"] = estado_str
        mg["homeostase"]["componentes"] = memoria["homeostase"]["componentes"]
        
        salvar_memoria_global(mg)
    except Exception as e:
        logger.error(f"❌ Erro ao sincronizar memória global: {e}")

    logger.info(f"⚖️ Equilíbrio atualizado: {harmonia_final}% ({estado_str})")
    return memoria["homeostase"]

# --- Funções Auxiliares ---

def _extrair_valor(dados: dict, chave: str, subchave: str, padrao: float) -> float:
    """Extrai valor numérico lidando com dicionários ou valores diretos."""
    raw = dados.get(chave, padrao)
    try:
        if isinstance(raw, dict):
            return float(raw.get(subchave, padrao))
        return float(raw)
    except (ValueError, TypeError):
        return padrao

def _definir_estado(score: int) -> str:
    if score >= 80: return "Plena Harmonia 🌟"
    if score >= 60: return "Equilíbrio Bom ✅"
    if score >= 40: return "Atenção Necessária ⚠️"
    return "Desequilíbrio Crítico 🔴"