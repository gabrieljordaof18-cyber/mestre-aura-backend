# sensores.py
import random
from datetime import datetime

# ======================================================
# 🌡️ SENSORES SIMULADOS (COLETA DE DADOS APENAS)
# ======================================================
# Este módulo NÃO toma decisões. Ele apenas entrega números.

def gerar_dados_fisiologicos():
    """Gera dados simulados realistas."""
    agora = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # Simulações aleatórias dentro de faixas humanas
    sono_horas = round(random.uniform(5.5, 9.0), 1)
    hrv_valor = random.randint(40, 95)
    energia_nivel = random.randint(40, 100)
    
    # Treino (30% de chance de ter treinado)
    treinou = random.random() > 0.7
    treino_int = random.randint(60, 90) if treinou else 0
    treino_dur = random.randint(30, 60) if treinou else 0
    tipo_treino = random.choice(["musculação", "cardio", "descanso"]) if treinou else "descanso"

    return {
        "frequencia_cardiaca": random.randint(60, 100),
        "hrv": {"valor": hrv_valor, "status": "simulado"},
        "sono": {"horas": sono_horas, "qualidade": "calculada"},
        "energia": {"nivel": energia_nivel, "status": "simulado"},
        "treino": {
            "intensidade": treino_int,
            "duracao_min": treino_dur,
            "tipo": tipo_treino
        },
        "ultima_sincronizacao": agora
    }

# Mantemos para compatibilidade
def coletar_dados():
    return gerar_dados_fisiologicos()

def status_integracoes():
    return {"apple": True, "garmin": False, "simulador": True}