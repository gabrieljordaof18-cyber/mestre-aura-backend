import logging
from datetime import datetime
from typing import Dict, Any

# Importação para acesso ao banco de dados (Leitura de Atividades)
from data_manager import mongo_db
from pymongo import DESCENDING

# Configuração de Logs
logger = logging.getLogger("AURA_SENSORES_REAL")

# ======================================================
# 📡 LEITOR DE SENSORES REAIS (DB & INTEGRAÇÕES)
# ======================================================

def coletar_dados(user_id: str, config_integracoes: Dict[str, Any]) -> Dict[str, Any]:
    """
    Busca dados REAIS das atividades sincronizadas no banco de dados.
    Não inventa dados. Se não houver, retorna vazio/zeros.
    
    Args:
        user_id: ID do usuário no MongoDB.
        config_integracoes: Dicionário de configurações (do perfil do usuário).
    """
    # 1. Estrutura Base (Fallback / Vazio)
    # Se não encontrarmos nada, retornamos isso para não quebrar o UI.
    dados_fisiologicos = {
        "frequencia_cardiaca": 0,    # 0 = Sem dados
        "hrv": {"valor": 0, "status": "sem_dados"},
        "sono": {"horas": 0.0, "qualidade": "manual"}, # Strava não dá sono, requer input manual
        "energia": {"nivel": 0, "status": "aguardando"},
        "treino": {
            "intensidade": 0,
            "duracao_min": 0,
            "tipo": "descanso"
        },
        "passos_diarios": 0,
        "calorias_gastas": 0,
        "ultima_sincronizacao": str(datetime.now())
    }

    if mongo_db is None:
        return dados_fisiologicos

    # 2. Processamento STRAVA (Se conectado)
    if config_integracoes.get("strava", {}).get("conectado"):
        try:
            # Busca a ÚLTIMA atividade registrada deste usuário no banco
            # (Alimentada pelo webhook logic_strava.py)
            ultima_atividade = mongo_db["activities"].find_one(
                {"user_id": user_id},
                sort=[("start_date", DESCENDING)] # Pega a mais recente
            )

            if ultima_atividade:
                # Verifica se a atividade é de HOJE (data local do servidor/atividade)
                data_ativ_str = ultima_atividade.get("start_date_local", "")[:10]
                hoje_str = datetime.now().strftime("%Y-%m-%d")

                if data_ativ_str == hoje_str:
                    logger.info(f"🏃 Dados do Strava encontrados para hoje (User {user_id})")
                    
                    # Mapeamento Strava -> Aura
                    # Nota: Strava envia duração em segundos, convertemos para minutos
                    duracao_min = round(ultima_atividade.get("moving_time", 0) / 60)
                    distancia_km = ultima_atividade.get("distance", 0) / 1000
                    bpm_medio = ultima_atividade.get("average_heartrate", 0)
                    calorias = ultima_atividade.get("kilojoules", 0) * 0.239 # Aprox KJ -> Kcal

                    # Atualiza os dados
                    dados_fisiologicos["treino"] = {
                        "intensidade": int(bpm_medio) if bpm_medio else 0, # Usamos BPM como proxy de intensidade
                        "duracao_min": duracao_min,
                        "tipo": ultima_atividade.get("type", "treino").lower()
                    }
                    
                    dados_fisiologicos["calorias_gastas"] = int(calorias)
                    
                    # Estimativa de Passos baseada na distância (se for corrida/caminhada)
                    # Média: 1km ~ 1300 passos
                    if dados_fisiologicos["treino"]["tipo"] in ["run", "walk", "hike"]:
                        dados_fisiologicos["passos_diarios"] = int(distancia_km * 1300)

                    if bpm_medio > 0:
                        dados_fisiologicos["frequencia_cardiaca"] = int(bpm_medio)

        except Exception as e:
            logger.error(f"❌ Erro ao ler dados do Strava no banco: {e}")

    # 3. Processamento APPLE HEALTH / GARMIN
    # (Futuro: Aqui leríamos de outras coleções ou APIs)
    
    return dados_fisiologicos

def status_integracoes(user_id: str) -> Dict[str, bool]:
    """
    Verifica no BANCO DE DADOS quais serviços estão realmente conectados.
    """
    status = {
        "apple": False,
        "garmin": False,
        "strava": False
    }

    if mongo_db is None:
        return status

    try:
        from data_manager import buscar_usuario_por_id
        usuario = buscar_usuario_por_id(user_id)
        
        if usuario:
            integracoes = usuario.get("integracoes", {})
            
            # Strava
            if integracoes.get("strava", {}).get("conectado"):
                status["strava"] = True
                
            # Apple / Garmin (Placeholder para futuro)
            if integracoes.get("apple_health", {}).get("conectado"):
                status["apple"] = True
                
            if integracoes.get("garmin", {}).get("conectado"):
                status["garmin"] = True

    except Exception as e:
        logger.error(f"❌ Erro ao verificar status integrações: {e}")

    return status