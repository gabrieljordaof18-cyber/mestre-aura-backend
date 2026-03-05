import time
import requests
import logging
import os
from datetime import datetime

# Importações da Nova Arquitetura
# [AURA FIX] data_manager centraliza a conexão com o MongoDB Atlas do Render
from data_manager import mongo_db
from logic_gamificacao import aplicar_xp

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AURA_LOGIC_STRAVA")

# =========================================================
# ⚙️ REGRAS DE GAMIFICAÇÃO (BALANCEAMENTO)
# =========================================================
# [AURA INFO] Parâmetros de conversão para o ecossistema Aura
XP_POR_KM = 10
XP_BONUS_MADRUGADA = 50
XP_POR_METRO_ELEVACAO = 2
XP_BONUS_FLASH = 30
VELOCIDADE_FLASH_MS = 2.78  # ~10km/h

# [AURA REMOVED] Removida a taxa de conversão antiga (20:1) 
# Agora usamos a lógica centralizada em aplicar_xp (1:1 e 10:1)

# =========================================================
# 🧠 CÉREBRO DA INTEGRAÇÃO STRAVA (SAAS / MULTI-USER)
# =========================================================

def processar_evento_webhook(dados_evento: dict) -> bool:
    """
    Orquestrador de treinos. Valida, calcula XP e atualiza o Jogador.
    Sincroniza os dados entre Strava API -> MongoDB Atlas -> Frontend (Base44).
    """
    logger.info(f"🔄 Processando evento Strava ID: {dados_evento.get('object_id')}")

    # 1. FILTRO DE SEGURANÇA (Apenas novas atividades importam para ganho de XP)
    if dados_evento.get('object_type') != 'activity' or dados_evento.get('aspect_type') != 'create':
        return False

    strava_id_atleta = str(dados_evento.get('owner_id'))
    atividade_id = str(dados_evento.get('object_id'))

    # [AURA FIX] Comparação explícita com None exigida pelo PyMongo no Render
    if mongo_db is None:
        logger.error("❌ Erro: Banco de dados offline. Impossível processar atividade.")
        return False

    # 2. PROTEÇÃO CONTRA DUPLICIDADE (Idempotência)
    if mongo_db["atividades_strava"].find_one({"id": atividade_id}):
        logger.warning(f"⚠️ Atividade {atividade_id} já processada anteriormente.")
        return True

    # 3. IDENTIFICAR JOGADOR (Sincronização com a coleção correta)
    # Alterado de 'users' para 'usuarios' conforme sua estrutura no Atlas
    usuario = mongo_db["usuarios"].find_one({"integracoes.strava.atleta_id": strava_id_atleta})
    
    if not usuario:
        logger.warning(f"⚠️ Atleta Strava {strava_id_atleta} não vinculado a nenhum usuário na coleção 'usuarios'.")
        return False

    user_id = str(usuario["_id"])

    # 4. RENOVAÇÃO DE TOKEN (Segurança OAuth2 obrigatória do Strava)
    access_token = obter_token_valido(usuario)
    if not access_token: 
        logger.error(f"❌ Falha ao obter token válido para o usuário {user_id}")
        return False

    # 5. BUSCA DETALHES NA API DO STRAVA
    try:
        url = f"https://www.strava.com/api/v3/activities/{atividade_id}"
        headers = {'Authorization': f"Bearer {access_token}"}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"❌ Erro Strava API ({response.status_code}): {response.text}")
            return False
            
        dados_treino = response.json()
    except Exception as e:
        logger.error(f"❌ Falha na conexão de rede com Strava: {e}")
        return False

    # 6. CÁLCULO DE RECOMPENSAS (XP Base)
    xp_ganho, lista_bonus = calcular_xp_avancado(dados_treino)

    # 7. PERSISTÊNCIA E ATUALIZAÇÃO DO JOGADOR
    try:
        # [AURA FIX] Aplicar XP, Moedas e Cristais usando a Regra de Ouro (100% Sincronizado)
        # Chamamos a função centralizada que já faz: Moedas = XP e Cristais = XP / 10
        resultado_economia = aplicar_xp(user_id, xp_ganho)
        
        # A. Salvar no Histórico (Coleção 'atividades_strava') com metadados do ganho
        dados_treino["user_id"] = user_id
        dados_treino["aura_analysis"] = {
            "xp_ganho": xp_ganho,
            "moedas_ganhas": resultado_economia.get("moedas_ganhas", 0),
            "cristais_ganhos": resultado_economia.get("cristais_ganhos", 0),
            "bonus_detectados": lista_bonus,
            "processed_at": datetime.now().isoformat()
        }
        mongo_db["atividades_strava"].insert_one(dados_treino)
        
        logger.info(f"✅ Treino Strava Concluído! User: {user_id} | +{xp_ganho} XP/Moedas | +{resultado_economia.get('cristais_ganhos')} Cristais")
        return True

    except Exception as e:
        logger.error(f"❌ Erro ao finalizar persistência de treino no MongoDB: {e}")
        return False

def obter_token_valido(usuario: dict) -> str:
    """Renova o access_token caso esteja expirado ou prestes a expirar."""
    integracao = usuario.get('integracoes', {}).get('strava', {})
    tokens = integracao.get('tokens', {})
    
    if tokens.get('expires_at', 0) > (time.time() + 300):
        return tokens.get('access_token')
        
    logger.info(f"⏳ Token Strava expirado. Iniciando renovação para o usuário ID: {usuario.get('_id')}")
    
    try:
        payload = {
            'client_id': os.getenv('STRAVA_CLIENT_ID'),
            'client_secret': os.getenv('STRAVA_CLIENT_SECRET'),
            'grant_type': 'refresh_token',
            'refresh_token': tokens.get('refresh_token')
        }
        res = requests.post("https://www.strava.com/oauth/token", data=payload, timeout=10)
        
        if res.status_code == 200:
            novos = res.json()
            mongo_db["usuarios"].update_one(
                {"_id": usuario["_id"]},
                {"$set": {
                    "integracoes.strava.tokens.access_token": novos.get('access_token'),
                    "integracoes.strava.tokens.refresh_token": novos.get('refresh_token'),
                    "integracoes.strava.tokens.expires_at": novos.get('expires_at'),
                    "updated_at": datetime.now().isoformat()
                }}
            )
            return novos.get('access_token')
        else:
            logger.error(f"❌ Erro ao renovar token no Strava: {res.text}")
    except Exception as e:
        logger.error(f"❌ Falha crítica na conexão OAuth Strava: {e}")
    return None

def calcular_xp_avancado(treino: dict) -> tuple:
    """Calcula XP baseado em distância, elevação e velocidade média."""
    xp = 0
    motivos = []

    dist_km = treino.get('distance', 0) / 1000
    elevacao = treino.get('total_elevation_gain', 0)
    vel_ms = treino.get('average_speed', 0)
    
    try:
        hora_str = treino.get('start_date_local', 'T12')
        hora = int(hora_str.split('T')[1][:2])
    except Exception: 
        hora = 12

    if dist_km > 0.1:
        ganho_dist = int(dist_km * XP_POR_KM)
        xp += max(10, ganho_dist)
        motivos.append(f"Distância ({dist_km:.1f}km)")

    if 4 <= hora < 8:
        xp += XP_BONUS_MADRUGADA
        motivos.append("☀️ Bônus Madrugador")

    if elevacao > 50:
        xp += int(elevacao * XP_POR_METRO_ELEVACAO)
        motivos.append(f"⛰️ Elevação (+{int(elevacao)}m)")

    if vel_ms > VELOCIDADE_FLASH_MS:
        xp += XP_BONUS_FLASH
        motivos.append("⚡ Ritmo The Flash")

    return xp, motivos