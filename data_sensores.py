import json
from datetime import datetime
from sensores import coletar_dados # Importa a função do seu módulo sensores.py
from data_user import carregar_memoria, salvar_memoria # Funções que acabamos de mover

# ======================================================
# ⚙️ FUNÇÃO 3 — Obter Dados Fisiológicos (via sensores.py)
# ======================================================
def obter_dados_fisiologicos(memoria=None):
    """
    Atualiza os dados fisiológicos a partir do módulo sensores.
    Se os sensores estiverem offline, mantém simulação leve.
    Retorna o dicionário de novos dados e salva na memória local.
    """
    if memoria is None:
        memoria = carregar_memoria() # Chama a função que agora está em data_user.py
    try:
        # AQUI, chamamos o seu módulo externo (sensores.py)
        novos_dados = coletar_dados() 
        if not isinstance(novos_dados, dict):
            raise ValueError("Formato inválido retornado pelos sensores.")

        # Mantém campos existentes e atualiza
        memoria.setdefault("dados_fisiologicos", {}).update(novos_dados)
        memoria["dados_fisiologicos"]["ultima_sincronizacao"] = str(datetime.now())
        memoria.setdefault("logs", []).append({
            "tipo": "SINCRONIZACAO_SENSORES",
            "data": str(datetime.now()),
            "dados": novos_dados
        })
        salvar_memoria(memoria) # Chama a função que agora está em data_user.py
        return novos_dados

    except Exception as e:
        print(f"⚠️ Erro ao obter dados dos sensores: {e}")
        # fallback para modo simulado sem sobrescrever tudo
        dados = memoria.get("dados_fisiologicos", {})
        # pequenas mudanças conservadoras (lógica de simulação continua aqui)
        dados["frequencia_cardiaca"] = int(max(55, min(160, dados.get("frequencia_cardiaca", 72) + 1)))
        dados["variabilidade_hrv"] = float(round(max(20, min(120, dados.get("variabilidade_hrv", 75) + 0.5)), 1))
        dados["ultima_sincronizacao"] = str(datetime.now())
        memoria["dados_fisiologicos"] = dados
        salvar_memoria(memoria) # Chama a função que agora está em data_user.py
        return dados