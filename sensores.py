import random
import logging
from datetime import datetime
from typing import Dict, Any

# Configuração de Logs
logger = logging.getLogger("AURA_SENSORES_HARDWARE")

# ======================================================
# 🌡️ SENSORES SIMULADOS (MOCKUP DE HARDWARE)
# ======================================================
# Este módulo simula a leitura de wearables (Apple Watch, Garmin).
# Em produção, ele seria substituído pelas APIs oficiais.

def coletar_dados() -> Dict[str, Any]:
    """
    Gera dados fisiológicos simulados dentro de faixas humanas realistas.
    Retorna um dicionário padronizado.
    """
    agora = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # 1. Simulações aleatórias (Biohacking Range)
    # Sono: 5.5h a 9h
    sono_horas = round(random.uniform(5.5, 9.0), 1)
    
    # HRV: 40ms a 95ms (Normal)
    hrv_valor = random.randint(40, 95)
    
    # Energia: 40% a 100%
    energia_nivel = random.randint(40, 100)
    
    # 2. Simulação de Treino (30% de chance de ter treinado agora)
    treinou = random.random() > 0.7
    
    if treinou:
        treino_int = random.randint(60, 90)
        treino_dur = random.randint(30, 60)
        tipo_treino = random.choice(["musculação", "cardio", "crossfit"])
    else:
        treino_int = 0
        treino_dur = 0
        tipo_treino = "descanso"

    # 3. Montagem do Pacote de Dados
    dados = {
        "frequencia_cardiaca": random.randint(60, 100),
        "hrv": {"valor": hrv_valor, "status": "simulado"},
        "sono": {"horas": sono_horas, "qualidade": "calculada"},
        "energia": {"nivel": energia_nivel, "status": "simulado"},
        "treino": {
            "intensidade": treino_int,
            "duracao_min": treino_dur,
            "tipo": tipo_treino
        },
        "passos_diarios": random.randint(2000, 12000),
        "calorias_gastas": random.randint(1800, 3200),
        "ultima_sincronizacao": agora
    }
    
    # logger.debug("Dados simulados gerados com sucesso.") # Debug apenas se necessário
    return dados

def status_integracoes() -> Dict[str, bool]:
    """Retorna o status dos serviços conectados."""
    return {
        "apple": True,      # Simulado
        "garmin": False,    # Simulado
        "strava": True,     # REAL (Via Webhook)
        "simulador": True   # Ativo
    }