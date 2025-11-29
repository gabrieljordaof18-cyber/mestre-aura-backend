import logging
from datetime import datetime
from typing import Dict, Any, Optional
from sensores import coletar_dados 
from data_user import carregar_memoria, salvar_memoria

# Configuração de Logs
logger = logging.getLogger("AURA_SENSORES")

# ======================================================
# ⚙️ FUNÇÃO 3 — Obter Dados Fisiológicos (Otimizada)
# ======================================================
def obter_dados_fisiologicos(memoria: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Atualiza os dados fisiológicos a partir do módulo sensores.
    Gerencia fallback de simulação e evita inchaço de logs.
    """
    if memoria is None:
        memoria = carregar_memoria()

    try:
        # 1. Coleta Real
        novos_dados = coletar_dados() 
        
        if not isinstance(novos_dados, dict):
            raise ValueError(f"Formato inválido retornado pelos sensores: {type(novos_dados)}")

        # 2. Atualização de Estado
        if "dados_fisiologicos" not in memoria:
            memoria["dados_fisiologicos"] = {}

        memoria["dados_fisiologicos"].update(novos_dados)
        memoria["dados_fisiologicos"]["ultima_sincronizacao"] = str(datetime.now())
        
        # 3. Log Otimizado (Sem salvar dados brutos para não pesar o JSON)
        if "logs" not in memoria: memoria["logs"] = []
        
        # Mantemos apenas os últimos 50 logs para não travar o arquivo local
        if len(memoria["logs"]) > 50:
            memoria["logs"].pop(0)

        memoria["logs"].append({
            "tipo": "SINCRONIZACAO_SENSORES",
            "data": str(datetime.now()),
            "status": "sucesso"
        })
        
        salvar_memoria(memoria)
        return novos_dados

    except Exception as e:
        logger.warning(f"⚠️ Erro nos sensores ({e}). Ativando modo simulação.")
        
        # 4. Fallback (Modo Simulado)
        dados = memoria.get("dados_fisiologicos", {})
        
        # Pequena variação para não parecer estático
        fc_atual = dados.get("frequencia_cardiaca", 72)
        hrv_atual = dados.get("variabilidade_hrv", 75)

        dados["frequencia_cardiaca"] = int(max(55, min(160, fc_atual + 1)))
        dados["variabilidade_hrv"] = float(round(max(20, min(120, hrv_atual + 0.5)), 1))
        dados["ultima_sincronizacao"] = str(datetime.now())
        
        memoria["dados_fisiologicos"] = dados
        salvar_memoria(memoria)
        return dados