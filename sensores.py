import logging
from datetime import datetime
from typing import Dict, Any

# Importação para acesso ao banco de dados (Leitura de Atividades)
# [AURA FIX] Importação explícita para garantir sincronização com Render/Atlas
from data_manager import mongo_db, DESCENDING

# Configuração de Logs
logger = logging.getLogger("AURA_SENSORES_REAL")

# ======================================================
# 📡 LEITOR DE SENSORES (ORQUESTRAÇÃO DE DADOS)
# ======================================================

def coletar_dados(user_id: str, config_integracoes: Dict[str, Any]) -> Dict[str, Any]:
    """
    Busca dados REAIS das atividades sincronizadas no MongoDB Atlas.
    Mapeia batimentos, passos e calorias para o Dashboard do Base44.
    """
    # 1. Estrutura Base conforme Schema 2.0.1 (Harmonia com status_atual)
    # [AURA FIX] Ajustado para as chaves que o seu Frontend e Banco esperam
    dados_fisiologicos = {
        "fc_repouso": 0,
        "hrv_valor": 0,
        "sono_horas": 0.0, 
        "recuperacao": 100,
        "fadiga": 0,
        "prontidao": 100,
        "passos_hoje": 0,
        "calorias_hoje": 0,
        "ultima_sincronizacao": datetime.now().isoformat()
    }

    # [AURA FIX] Comparação explícita com None para evitar erro de truth value no Render
    if mongo_db is None:
        logger.error("❌ MongoDB inacessível em sensores.py")
        return dados_fisiologicos

    # 2. Processamento STRAVA (Se o usuário vinculou a conta no Atlas)
    if config_integracoes.get("strava", {}).get("conectado"):
        try:
            # [AURA FIX] Busca na coleção 'atividades_strava' (conforme configurado no logic_strava)
            ultima_atividade = mongo_db["atividades_strava"].find_one(
                {"user_id": str(user_id)},
                sort=[("start_date_local", DESCENDING)]
            )

            if ultima_atividade:
                # Verificamos se a atividade ocorreu nas últimas 24 horas para ser relevante hoje
                data_ativ_str = ultima_atividade.get("start_date_local", "")[:10]
                hoje_str = datetime.now().date().isoformat()

                if data_ativ_str == hoje_str:
                    logger.info(f"🏃 Sincronizando atividade Strava de hoje para {user_id}")
                    
                    # Conversões Técnicas de dados brutos da API
                    bpm_medio = int(ultima_atividade.get("average_heartrate", 0))
                    distancia_km = ultima_atividade.get("distance", 0) / 1000
                    
                    # Cálculo de Calorias (KJ para Kcal: fator aproximado de 0.239)
                    calorias_total = int(ultima_atividade.get("kilojoules", 0) * 0.239)

                    # Atualização do Dicionário (Campos do status_atual no Atlas)
                    dados_fisiologicos["fc_repouso"] = bpm_medio
                    dados_fisiologicos["calorias_hoje"] = calorias_total
                    
                    # Estimativa de passos baseada no deslocamento GPS
                    if ultima_atividade.get("type") in ["Run", "Walk", "Hike"]:
                        dados_fisiologicos["passos_hoje"] = int(distancia_km * 1350)

                    # Lógica de Fadiga/Recuperação baseada no BPM
                    # [AURA FIX] Mapeado para os campos reais que a lógica de Equilíbrio lê
                    if bpm_medio > 150:
                        dados_fisiologicos["fadiga"] = 80
                        dados_fisiologicos["recuperacao"] = 20
                    elif bpm_medio > 120:
                        dados_fisiologicos["fadiga"] = 40
                        dados_fisiologicos["recuperacao"] = 60
                    else:
                        dados_fisiologicos["fadiga"] = 10
                        dados_fisiologicos["recuperacao"] = 90

        except Exception as e:
            logger.error(f"❌ Erro ao ler sensores via Strava: {e}")

    return dados_fisiologicos

def status_integracoes(user_id: str) -> Dict[str, bool]:
    """
    Verifica quais serviços de wearables estão ativos para o usuário no MongoDB Atlas.
    """
    status = {"apple": False, "garmin": False, "strava": False}
    if mongo_db is None: return status

    try:
        # Importação local para evitar dependência circular
        from data_user import carregar_memoria
        usuario = carregar_memoria(user_id)
        
        if usuario:
            integracoes = usuario.get("integracoes", {})
            status["strava"] = integracoes.get("strava", {}).get("conectado", False)
            status["apple"] = integracoes.get("apple_health", {}).get("conectado", False)
            status["garmin"] = integracoes.get("garmin", {}).get("conectado", False)

    except Exception as e:
        logger.error(f"❌ Erro ao verificar status integrações para {user_id}: {e}")

    return status