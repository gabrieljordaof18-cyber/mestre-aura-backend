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
TAXA_CONVERSAO_COINS = 20   # 20 XP = 1 Aura Coin (Ajustado para o campo 'moedas')

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
    # Evita que o mesmo treino gere XP duas vezes se o webhook reenviar
    if mongo_db["atividades_strava"].find_one({"id": atividade_id}):
        logger.warning(f"⚠️ Atividade {atividade_id} já processada anteriormente.")
        return True

    # 3. IDENTIFICAR JOGADOR (Sincronização com a coleção correta)
    # [AURA FIX] Alterado de 'users' para 'usuarios' conforme sua estrutura no Atlas
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

    # 6. CÁLCULO DE RECOMPENSAS (XP e Aura Coins)
    xp_total, lista_bonus = calcular_xp_avancado(dados_treino)
    
    # [AURA FIX] Sincronização com o campo 'moedas' da sua raiz
    coins_ganhas = max(1, int(xp_total / TAXA_CONVERSAO_COINS)) if xp_total > 0 else 0

    # 7. PERSISTÊNCIA E ATUALIZAÇÃO DO JOGADOR
    try:
        # A. Salvar no Histórico (Coleção 'atividades_strava')
        dados_treino["user_id"] = user_id
        dados_treino["aura_analysis"] = {
            "xp_ganho": xp_total,
            "coins_ganhas": coins_ganhas,
            "bonus": lista_bonus,
            "processed_at": datetime.now().isoformat()
        }
        mongo_db["atividades_strava"].insert_one(dados_treino)

        # B. Aplicar XP e Nível (Usando a lógica de logic_gamificacao.py ajustada para a raiz)
        aplicar_xp(user_id, xp_total)
        
        # C. Atualizar Saldo de Moedas (Sincronização com o campo 'moedas' na raiz)
        # [AURA FIX] Alterado para atualizar o campo 'moedas' diretamente, sem o objeto 'jogador'
        mongo_db["usuarios"].update_one(
            {"_id": usuario["_id"]},
            {
                "$inc": {"moedas": coins_ganhas},
                "$set": {"updated_at": datetime.now().isoformat()}
            }
        )
        
        logger.info(f"✅ Treino Concluído! User: {user_id} | +{xp_total} XP | +{coins_ganhas} Aura Coins")
        return True

    except Exception as e:
        logger.error(f"❌ Erro ao finalizar persistência de treino no MongoDB: {e}")
        return False

def obter_token_valido(usuario: dict) -> str:
    """Renova o access_token caso esteja expirado ou prestes a expirar."""
    integracao = usuario.get('integracoes', {}).get('strava', {})
    tokens = integracao.get('tokens', {})
    
    # Se o token ainda é válido por mais de 5 minutos, reutiliza
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
            # [AURA FIX] Atualiza na coleção 'usuarios'
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

    # Extração de dados da API do Strava (Distância vem em metros)
    dist_km = treino.get('distance', 0) / 1000
    elevacao = treino.get('total_elevation_gain', 0)
    vel_ms = treino.get('average_speed', 0)
    
    # Parsing de Hora para Bônus Madrugador (Início do treino)
    try:
        # Formato esperado: "2026-03-05T06:30:00Z"
        hora_str = treino.get('start_date_local', 'T12')
        hora = int(hora_str.split('T')[1][:2])
    except Exception: 
        hora = 12

    # A. Cálculo por Distância
    if dist_km > 0.1:
        ganho_dist = int(dist_km * XP_POR_KM)
        xp += max(10, ganho_dist)
        motivos.append(f"Distância ({dist_km:.1f}km)")

    # B. Bônus por Horário (Consistência matinal)
    if 4 <= hora < 8:
        xp += XP_BONUS_MADRUGADA
        motivos.append("☀️ Bônus Madrugador")

    # C. Bônus por Esforço de Elevação
    if elevacao > 50:
        xp += int(elevacao * XP_POR_METRO_ELEVACAO)
        motivos.append(f"⛰️ Elevação (+{int(elevacao)}m)")

    # D. Bônus por Intensidade (Velocidade)
    if vel_ms > VELOCIDADE_FLASH_MS:
        xp += XP_BONUS_FLASH
        motivos.append("⚡ Ritmo The Flash")

    return xp, motivos