import logging
from datetime import datetime
from typing import Dict, Any

# Importação para acesso ao banco de dados (Leitura de Atividades)
from data_manager import mongo_db, DESCENDING

# Configuração de Logs
logger = logging.getLogger("AURA_SENSORES_REAL")

# ======================================================
# 📡 LEITOR DE SENSORES (ORQUESTRAÇÃO DE DADOS)
# ======================================================

def coletar_dados(user_id: str, config_integracoes: Dict[str, Any]) -> Dict[str, Any]:
    """
    Busca dados REAIS das atividades sincronizadas no MongoDB.
    Mapeia batimentos, passos e calorias para o Dashboard.
    """
    # 1. Estrutura Base conforme Schema 2.0
    dados_fisiologicos = {
        "frequencia_cardiaca": {"valor": 0, "repouso": 0},
        "hrv": {"valor": 0, "status": "aguardando"},
        "sono": {"horas": 0.0, "qualidade": "manual"}, 
        "energia": {"nivel": 0, "status": "analisando"},
        "passos_hoje": 0,
        "calorias_hoje": 0,
        "ultima_sincronizacao": datetime.now().isoformat()
    }

    if mongo_db is None:
        return dados_fisiologicos

    # 2. Processamento STRAVA (Se o usuário vinculou a conta)
    if config_integracoes.get("strava", {}).get("conectado"):
        try:
            # Busca a atividade mais recente na coleção 'activities'
            ultima_atividade = mongo_db["activities"].find_one(
                {"user_id": user_id},
                sort=[("start_date_local", DESCENDING)]
            )

            if ultima_atividade:
                # Verificamos se a atividade ocorreu nas últimas 24 horas
                data_ativ_str = ultima_atividade.get("start_date_local", "")[:10]
                hoje_str = datetime.now().date().isoformat()

                if data_ativ_str == hoje_str:
                    logger.info(f"🏃 Sincronizando atividade Strava de hoje para {user_id}")
                    
                    # Conversões Técnicas
                    # Strava fornece moving_time em segundos e distance em metros
                    duracao_min = round(ultima_atividade.get("moving_time", 0) / 60)
                    distancia_km = ultima_atividade.get("distance", 0) / 1000
                    bpm_medio = int(ultima_atividade.get("average_heartrate", 0))
                    
                    # Cálculo de Calorias (KJ para Kcal: fator aproximado de 0.239)
                    calorias = int(ultima_atividade.get("kilojoules", 0) * 0.239)

                    # Atualização do Dicionário (Campos do Schema 2.0)
                    dados_fisiologicos["frequencia_cardiaca"]["valor"] = bpm_medio
                    dados_fisiologicos["calorias_hoje"] = calorias
                    
                    # Estimativa inteligente de passos baseada na atividade física
                    if ultima_atividade.get("type") in ["Run", "Walk", "Hike"]:
                        dados_fisiologicos["passos_hoje"] = int(distancia_km * 1350) # Média de passos por km

                    # Definimos o status de Energia baseado no esforço
                    if bpm_medio > 150:
                        dados_fisiologicos["energia"]["status"] = "recuperação necessária"
                    else:
                        dados_fisiologicos["energia"]["status"] = "estável"

        except Exception as e:
            logger.error(f"❌ Erro ao ler sensores via Strava: {e}")

    return dados_fisiologicos

def status_integracoes(user_id: str) -> Dict[str, bool]:
    """
    Verifica quais serviços de wearables estão ativos para o usuário.
    """
    status = {"apple": False, "garmin": False, "strava": False}
    if mongo_db is None: return status

    try:
        from data_manager import buscar_usuario_por_id
        usuario = buscar_usuario_por_id(user_id)
        
        if usuario:
            integracoes = usuario.get("integracoes", {})
            status["strava"] = integracoes.get("strava", {}).get("conectado", False)
            status["apple"] = integracoes.get("apple_health", {}).get("conectado", False)
            status["garmin"] = integracoes.get("garmin", {}).get("conectado", False)

    except Exception as e:
        logger.error(f"❌ Erro ao verificar status integrações: {e}")

    return status