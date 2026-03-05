import logging
from datetime import datetime
from typing import Dict, Any, List

# Importação para acesso ao banco de dados (Leitura de Atividades)
# [AURA FIX] Importação explícita para garantir sincronização com Render/Atlas
from data_manager import mongo_db, DESCENDING

# Configuração de Logs
logger = logging.getLogger("AURA_SENSORES_REAL")

# ======================================================
# 📡 LEITOR DE SENSORES (ORQUESTRAÇÃO HÍBRIDA 3.0)
# ======================================================

def coletar_dados(user_id: str, config_integracoes: Dict[str, Any]) -> Dict[str, Any]:
    """
    Busca dados REAIS das atividades sincronizadas no MongoDB Atlas.
    Mapeia batimentos, passos e contextos esportivos para a IA Robusta.
    """
    # 1. Estrutura Base conforme Schema 3.0 (Harmonia com status_atual)
    dados_fisiologicos = {
        "fc_repouso": 0,
        "hrv_valor": 55, # Valor base de saúde sistêmica
        "sono_horas": 7.5, 
        "recuperacao": 100,
        "fadiga": 20,
        "prontidao": 100,
        "passos_hoje": 0,
        "calorias_hoje": 0,
        "resumo_esportes": [], # Contexto vital para o treino de 10 exercícios
        "ultima_sincronizacao": datetime.now().isoformat()
    }

    if mongo_db is None:
        logger.error("❌ MongoDB inacessível em sensores.py")
        return dados_fisiologicos

    # 2. Processamento STRAVA (Integração Híbrida)
    if config_integracoes.get("strava", {}).get("conectado"):
        try:
            # Buscamos as atividades das últimas 24 horas para compor o contexto
            cursor_atividades = mongo_db["atividades_strava"].find(
                {"user_id": str(user_id)},
                sort=[("start_date_local", DESCENDING)]
            ).limit(3) # Analisamos as 3 últimas para dar profundidade à IA

            atividades = list(cursor_atividades)

            if atividades:
                hoje_str = datetime.now().date().isoformat()
                
                for atividade in atividades:
                    data_ativ_str = atividade.get("start_date_local", "")[:10]
                    tipo = atividade.get("type", "Workout")
                    dist_km = round(atividade.get("distance", 0) / 1000, 2)
                    
                    # Adiciona ao resumo de esportes para o logic.py ler
                    dados_fisiologicos["resumo_esportes"].append({
                        "tipo": tipo,
                        "distancia": dist_km,
                        "data": data_ativ_str
                    })

                    # Se a atividade foi HOJE, atualizamos os sensores em tempo real
                    if data_ativ_str == hoje_str:
                        logger.info(f"🏃 Sincronizando {tipo} de hoje para o atleta {user_id}")
                        
                        bpm_medio = int(atividade.get("average_heartrate", 0))
                        calorias_total = int(atividade.get("kilojoules", 0) * 0.239)

                        if bpm_medio > 0:
                            dados_fisiologicos["fc_repouso"] = bpm_medio
                        
                        dados_fisiologicos["calorias_hoje"] += calorias_total
                        
                        # Estimativa de passos para modalidades terrestres
                        if tipo in ["Run", "Walk", "Hike"]:
                            dados_fisiologicos["passos_hoje"] += int(dist_km * 1320)

                        # Cálculo de Fadiga Acumulada (Impacta na Homeostase)
                        # [AURA ROBUST] Atividades intensas hoje reduzem a prontidão de amanhã
                        esforco = atividade.get("suffer_score", 0)
                        if esforco > 50 or bpm_medio > 150:
                            dados_fisiologicos["fadiga"] = min(100, dados_fisiologicos["fadiga"] + 50)
                            dados_fisiologicos["recuperacao"] = max(10, dados_fisiologicos["recuperacao"] - 40)

        except Exception as e:
            logger.error(f"❌ Erro ao processar contexto híbrido via Strava: {e}")

    return dados_fisiologicos

def status_integracoes(user_id: str) -> Dict[str, bool]:
    """
    Verifica quais serviços de wearables estão ativos para o usuário.
    """
    status = {"apple": False, "garmin": False, "strava": False}
    if mongo_db is None: return status

    try:
        from data_user import carregar_memoria
        usuario = carregar_memoria(user_id)
        
        if usuario:
            integracoes = usuario.get("integracoes", {})
            status["strava"] = integracoes.get("strava", {}).get("conectado", False)
            status["apple"] = integracoes.get("apple_health", {}).get("conectado", False)
            status["garmin"] = integracoes.get("garmin", {}).get("conectado", False)

    except Exception as e:
        logger.error(f"❌ Erro ao verificar status integrações: {e}")

    return status