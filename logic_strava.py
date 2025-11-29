import time
import requests
import logging
from datetime import datetime
from data_manager import mongo_db
import os

# =========================================================
# ⚙️ CONFIGURAÇÕES & REGRAS DO JOGO
# =========================================================
# Aqui ficam as regras. Se quiser mudar a economia, mude AQUI.
XP_POR_KM = 10
XP_BONUS_MADRUGADA = 50
XP_POR_METRO_ELEVACAO = 2
XP_BONUS_FLASH = 30
VELOCIDADE_FLASH_MS = 2.78  # ~10km/h
TAXA_CONVERSAO_COINS = 20   # 20 XP = 1 Aura Coin

# Configuração de Logs (Para o Render ficar organizado)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AURA_LOGIC")

# =========================================================
# 🧠 CÉREBRO DA INTEGRAÇÃO STRAVA (VERSÃO 5.0 - FINAL)
# =========================================================

def processar_evento_webhook(dados_evento: dict) -> bool:
    """
    Orquestrador principal.
    Recebe o webhook, valida, calcula e salva.
    """
    logger.info(f"🔄 Recebendo evento Strava: {dados_evento.get('object_id')}")

    # 1. FILTRO DE SEGURANÇA
    if dados_evento.get('object_type') != 'activity' or dados_evento.get('aspect_type') != 'create':
        return False

    strava_id_usuario = dados_evento.get('owner_id')
    atividade_id = dados_evento.get('object_id')

    # 2. IDENTIFICAR O JOGADOR
    if mongo_db is None:
        logger.error("❌ Banco de dados desconectado.")
        return False

    usuario = mongo_db["usuarios"].find_one({"strava_id": strava_id_usuario})
    if not usuario:
        logger.warning(f"⚠️ Usuário Strava ID {strava_id_usuario} não encontrado no banco.")
        return False

    # 3. GARANTIR TOKEN VÁLIDO
    access_token = obter_token_valido(usuario)
    if not access_token:
        logger.error("❌ Falha crítica: Não foi possível renovar o token.")
        return False

    # 4. BUSCAR DETALHES DO TREINO
    try:
        headers = {'Authorization': f"Bearer {access_token}"}
        url = f"https://www.strava.com/api/v3/activities/{atividade_id}"
        response = requests.get(url, headers=headers, timeout=10) # Timeout evita travar o servidor
        
        if response.status_code != 200:
            logger.error(f"❌ Erro Strava API: {response.text}")
            return False
            
        dados_treino = response.json()
    except Exception as e:
        logger.error(f"❌ Erro de conexão com Strava: {e}")
        return False

    # 5. 🧙‍♂️ A MÁGICA: CALCULAR XP E MOEDAS
    xp_total, lista_bonus = calcular_xp_avancado(dados_treino)

    # Regra Econômica Centralizada
    coins_ganhas = int(xp_total / TAXA_CONVERSAO_COINS)
    if xp_total > 0 and coins_ganhas < 1:
        coins_ganhas = 1

    logger.info(f"💰 SUCESSO! Atividade {atividade_id} -> XP: {xp_total} | Coins: {coins_ganhas}")

    # 6. SALVAR NO BANCO
    try:
        mongo_db["usuarios"].update_one(
            {"strava_id": strava_id_usuario},
            {
                "$inc": {
                    "xp_total": xp_total,
                    "aura_coins": coins_ganhas
                },
                "$push": { 
                    "historico_atividades": {
                        "id_atividade": atividade_id,
                        "data": datetime.now(),
                        "nome_treino": dados_treino.get('name'),
                        "distancia_km": round(dados_treino.get('distance', 0) / 1000, 2),
                        "xp_ganho": xp_total,
                        "coins_ganhas": coins_ganhas,
                        "bonus_conquistados": lista_bonus
                    }
                }
            }
        )
        return True
    except Exception as e:
        logger.error(f"❌ Erro ao salvar no MongoDB: {e}")
        return False

def obter_token_valido(usuario: dict) -> str:
    """
    Gerencia a renovação do token OAuth2.
    """
    tokens = usuario.get('tokens', {})
    access_token = tokens.get('access_token')
    expires_at = tokens.get('expires_at')
    refresh_token = tokens.get('refresh_token')
    
    # Margem de segurança de 5 minutos
    agora = time.time()
    
    if expires_at and agora < (expires_at - 300):
        return access_token
        
    logger.info("⏳ Token expirado. Solicitando renovação...")
    
    url_token = "https://www.strava.com/oauth/token"
    payload = {
        'client_id': os.getenv('STRAVA_CLIENT_ID'),
        'client_secret': os.getenv('STRAVA_CLIENT_SECRET'),
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }
    
    try:
        res = requests.post(url_token, data=payload, timeout=10)
        
        if res.status_code == 200:
            novos_dados = res.json()
            
            # Atualiza no Banco
            mongo_db["usuarios"].update_one(
                {"strava_id": usuario['strava_id']},
                {"$set": {
                    "tokens.access_token": novos_dados.get('access_token'),
                    "tokens.refresh_token": novos_dados.get('refresh_token'),
                    "tokens.expires_at": novos_dados.get('expires_at')
                }}
            )
            logger.info("✅ Token renovado com sucesso!")
            return novos_dados.get('access_token')
        else:
            logger.error(f"❌ Erro renovação Strava: {res.text}")
            return None
    except Exception as e:
        logger.error(f"❌ Erro de conexão na renovação: {e}")
        return None

def calcular_xp_avancado(treino: dict) -> tuple:
    """
    Aplica as regras de gamificação. Retorna (int, list).
    """
    xp_acumulado = 0
    motivos = []

    # Extração segura de dados
    distancia_m = treino.get('distance', 0.0)
    elevacao_m = treino.get('total_elevation_gain', 0.0)
    velocidade_media_ms = treino.get('average_speed', 0.0)
    
    # Parsing de Data
    data_local = treino.get('start_date_local', '')
    hora_treino = 12
    try:
        if data_local:
            hora_treino = int(data_local.split('T')[1].split(':')[0])
    except:
        pass

    # --- APLICAÇÃO DAS REGRAS (Baseadas nas Constantes) ---

    # 1. Distância
    distancia_km = distancia_m / 1000
    xp_distancia = int(distancia_km * XP_POR_KM)
    if xp_distancia < 10 and distancia_km > 0.1: 
        xp_distancia = 10 # XP Mínimo
    
    xp_acumulado += xp_distancia
    motivos.append(f"Distância ({distancia_km:.1f}km): +{xp_distancia}")

    # 2. Madrugador (04h - 08h)
    if 4 <= hora_treino < 8:
        xp_acumulado += XP_BONUS_MADRUGADA
        motivos.append(f"☀️ Madrugador: +{XP_BONUS_MADRUGADA}")

    # 3. Rei da Montanha
    if elevacao_m > 50:
        xp_subida = int(elevacao_m * XP_POR_METRO_ELEVACAO)
        xp_acumulado += xp_subida
        motivos.append(f"⛰️ Rei da Montanha ({elevacao_m:.0f}m): +{xp_subida}")

    # 4. The Flash
    if velocidade_media_ms > VELOCIDADE_FLASH_MS:
        xp_acumulado += XP_BONUS_FLASH
        motivos.append(f"⚡ The Flash: +{XP_BONUS_FLASH}")

    return xp_acumulado, motivos