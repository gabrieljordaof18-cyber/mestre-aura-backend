# logic_equilibrio.py
from data_user import carregar_memoria, salvar_memoria
from data_global import carregar_memoria_global, salvar_memoria_global

# ======================================================
# ⚖️ LÓGICA DE EQUILÍBRIO (HOMEOSTASE)
# ======================================================

def calcular_e_atualizar_equilibrio():
    """
    Lê dados fisiológicos, calcula score de harmonia e salva.
    """
    memoria = carregar_memoria()
    dados = memoria["dados_fisiologicos"]
    
    # 1. Normalização dos Dados (Garantir que são números)
    try:
        # Extrai valor do sono (pode ser dict ou float direto, dependendo do legado)
        sono_raw = dados.get("sono", {})
        if isinstance(sono_raw, dict): sono_val = float(sono_raw.get("horas", 0))
        else: sono_val = float(sono_raw)

        # Extrai HRV
        hrv_raw = dados.get("hrv", {})
        if isinstance(hrv_raw, dict): hrv_val = float(hrv_raw.get("valor", 50))
        else: hrv_val = float(hrv_raw)
        
        # Extrai Energia
        energia_raw = dados.get("energia", {})
        if isinstance(energia_raw, dict): energia_val = float(energia_raw.get("nivel", 50))
        else: energia_val = float(energia_raw)

    except (ValueError, TypeError):
        # Fallback de segurança
        sono_val, hrv_val, energia_val = 7.0, 50.0, 50.0

    # 2. Cálculo dos Scores (0 a 100)
    
    # Sono: 8h = 100%, 4h = 0%
    score_sono = min(100, max(0, (sono_val - 4) * 25))
    
    # HRV: 80ms = 100%, 20ms = 0%
    score_hrv = min(100, max(0, (hrv_val - 20) * 1.6))
    
    # Energia: Já vem em 0-100
    score_energia = energia_val

    # 3. Score Final (Ponderado)
    # 40% Sono, 30% Energia, 30% HRV
    harmonia = (score_sono * 0.4) + (score_energia * 0.3) + (score_hrv * 0.3)
    harmonia = int(round(harmonia))

    # 4. Atualizar Memória Local (Visualização do Jogador)
    memoria["homeostase"] = {
        "score": harmonia,
        "estado": _definir_estado(harmonia),
        "componentes": {
            "corpo": int(score_hrv),
            "mente": int(score_sono), # Usando sono como proxy de mente por enquanto
            "energia": int(score_energia)
        }
    }
    salvar_memoria(memoria)

    # 5. Atualizar Memória Global (Histórico da IA)
    mg = carregar_memoria_global()
    mg["equilibrio"]["harmonia"] = harmonia
    salvar_memoria_global(mg)

    return memoria["homeostase"]

def _definir_estado(score):
    if score >= 80: return "Plena Harmonia 🌟"
    if score >= 60: return "Equilíbrio Bom ✅"
    if score >= 40: return "Atenção Necessária ⚠️"
    return "Desequilíbrio Crítico 🔴"