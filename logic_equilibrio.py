import logging
from datetime import datetime
from typing import Dict, Any, Optional

# Importações da Nova Arquitetura
from data_user import carregar_memoria, salvar_memoria

# Configuração de Logs
logger = logging.getLogger("AURA_LOGIC_EQUILIBRIO")

# ======================================================
# ⚙️ CONSTANTES E PESOS (BIOHACKING CORE 3.0)
# ======================================================
# [AURA INFO] Pesos recalibrados para a nova era de treinos híbridos
PESO_SONO = 0.40      # Impacto na clareza mental e recuperação profunda
PESO_ENERGIA = 0.35    # Impacto no desempenho físico imediato
PESO_HRV = 0.25       # Impacto no Sistema Nervoso Autônomo

# ======================================================
# ⚖️ LÓGICA DE EQUILÍBRIO (HOMEOSTASE)
# ======================================================

def calcular_e_atualizar_equilibrio(user_id: str) -> Dict[str, Any]:
    """
    Analisa os biomarcadores do usuário e calcula o score de Homeostase.
    O resultado impacta diretamente a complexidade dos treinos gerados pela IA.
    """
    if not user_id:
        logger.warning("⚠️ Tentativa de calcular equilíbrio sem user_id.")
        return {}

    # 1. Carrega memória do usuário (Sincronizado com o ID do Render/Base44)
    memoria = carregar_memoria(user_id)
    if not memoria:
        logger.error(f"❌ Usuário {user_id} não localizado para bio-análise.")
        return {}

    # [AURA FIX] Busca o status_atual que contém os dados processados pelos sensores
    dados_fisio = memoria.get("status_atual", {})
    
    # 2. Extração e Normalização de Dados (Schema 2.1.0 Robust)
    # Buscamos valores reais injetados pelo data_sensores.py
    sono_val = float(dados_fisio.get("sono_horas", 7.5))
    hrv_val = float(dados_fisio.get("hrv_valor", 50.0))
    energia_val = float(dados_fisio.get("recuperacao", 50.0))
    fadiga_val = float(dados_fisio.get("fadiga", 20.0))

    # 3. Algoritmo de Pontuação (Escala 0-100)
    
    # Score de Sono: Ideal 8h. Penaliza severamente abaixo de 5h.
    score_sono = max(0, min(100, (sono_val - 4) * 25))
    
    # Score de HRV: Proxy de prontidão do sistema nervoso.
    score_hrv = max(0, min(100, (hrv_val - 20) * 1.6))
    
    # Score de Energia: Baseado na recuperação calculada.
    score_energia = max(0, min(100, energia_val))

    # 4. Cálculo do Índice de Homeostase Ponderado
    harmonia = (score_sono * PESO_SONO) + (score_energia * PESO_ENERGIA) + (score_hrv * PESO_HRV)
    
    # [AURA ROBUST] Aplica o redutor de fadiga acumulada por treinos híbridos
    # Isso garante que se o atleta treinou 10 exercícios ontem, hoje o score reflete o cansaço.
    ajuste_fadiga = fadiga_val / 5
    harmonia_final = int(round(max(0, harmonia - ajuste_fadiga)))

    estado_str = _definir_estado(harmonia_final)

    # 5. Persistência no Perfil (Sincronização MongoDB Atlas)
    if "status_atual" not in memoria:
        memoria["status_atual"] = {}
        
    memoria["status_atual"]["prontidao"] = harmonia_final
    memoria["status_atual"]["estado_bio"] = estado_str
    memoria["status_atual"]["ultima_sincronizacao"] = datetime.now().isoformat()
    
    # Sincroniza o bloco principal de homeostase para leitura da IA no logic.py
    memoria["homeostase"] = {
        "score": harmonia_final,
        "estado": estado_str,
        "componentes": {
            "corpo": int(score_hrv),
            "mente": int(score_sono), 
            "energia": int(score_energia)
        },
        "ultima_analise": datetime.now().isoformat()
    }
    
    # 6. Salva os novos dados processados no MongoDB Atlas
    salvar_memoria(user_id, memoria)

    logger.info(f"⚖️ [EQUILÍBRIO] Score: {harmonia_final}% | Fadiga: {fadiga_val} | Estado: {estado_str}")
    return memoria["homeostase"]

# --- Funções Auxiliares de Processamento ---

def _definir_estado(score: int) -> str:
    """Define a categoria visual/narrativa baseada no score para o Frontend e IA."""
    if score >= 88: return "Plena Harmonia 🌟"
    if score >= 70: return "Equilíbrio Estável ✅"
    if score >= 50: return "Atenção Necessária ⚠️"
    if score >= 30: return "Recuperação Crítica 🔴"
    return "Esgotamento Neural ⛔"

def resetar_homeostase_diaria(user_id: str):
    """
    Limpa picos de fadiga no início do ciclo diário para permitir novos treinos.
    """
    try:
        memoria = carregar_memoria(user_id)
        if not memoria: return
        
        # Reduz fadiga gradualmente durante o descanso
        fadiga_atual = memoria.get("status_atual", {}).get("fadiga", 20)
        nova_fadiga = max(10, fadiga_atual * 0.7)
        
        salvar_memoria(user_id, {"status_atual.fadiga": nova_fadiga})
        logger.info(f"🔄 Fadiga resetada para {user_id} no novo ciclo.")
    except Exception as e:
        logger.error(f"❌ Erro ao resetar fadiga: {e}")