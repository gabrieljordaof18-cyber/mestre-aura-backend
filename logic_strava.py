import time
import requests
import logging
import os
from datetime import datetime

# Importações da Nova Arquitetura
from data_manager import mongo_db, salvar_atividade_strava
from logic_gamificacao import aplicar_xp

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AURA_LOGIC_STRAVA")

# =========================================================
# ⚙️ CONFIGURAÇÕES & REGRAS DE GAMIFICAÇÃO
# =========================================================
XP_POR_KM = 10
XP_BONUS_MADRUGADA = 50
XP_POR_METRO_ELEVACAO = 2
XP_BONUS_FLASH = 30
VELOCIDADE_FLASH_MS = 2.78  # ~10km/h (Ritmo forte para iniciantes)
TAXA_CONVERSAO_COINS = 20   # 20 XP = 1 Aura Coin

# =========================================================
# 🧠 CÉREBRO DA INTEGRAÇÃO STRAVA (SAAS / MULTI-USER)
# =========================================================

def processar_evento_webhook(dados_evento: dict) -> bool:
    """
    Orquestrador principal.
    Recebe o webhook, valida, verifica duplicidade, calcula XP e salva.
    """
    logger.info(f"🔄 Recebendo evento Strava: {dados_evento.get('object_id')}")

    # 1. FILTRO DE SEGURANÇA E TIPO
    # Só queremos atividades novas (create)
    if dados_evento.get('object_type') != 'activity' or dados_evento.get('aspect_type') != 'create':
        return False

    strava_id_atleta = dados_evento.get('owner_id')
    atividade_id = dados_evento.get('object_id')

    if mongo_db is None:
        logger.error("❌ Banco de dados desconectado.")
        return False

    # 2. PROTEÇÃO CONTRA SPAM (IDEMPOTÊNCIA)
    # Verifica se essa atividade já foi processada antes
    ja_processado = mongo_db["activities"].find_one({"id": atividade_id})
    if ja_processado:
        logger.warning(f"⚠️ Atividade {atividade_id} já processada. Ignorando duplicidade.")
        return True

    # 3. IDENTIFICAR O JOGADOR NO NOSSO BANCO
    # No novo Schema, o ID do Strava fica dentro de 'integracoes'
    usuario = mongo_db["users"].find_one({"integracoes.strava.atleta_id": strava_id_atleta})
    
    if not usuario:
        logger.warning(f"⚠️ Usuário com Strava ID {strava_id_atleta} não encontrado no sistema.")
        return False

    user_id = str(usuario["_id"])

    # 4. GARANTIR TOKEN VÁLIDO (REFRESH)
    access_token = obter_token_valido(usuario)
    if not access_token:
        logger.error(f"❌ Falha crítica: Não foi possível renovar o token para user {user_id}.")
        return False

    # 5. BUSCAR DETALHES DO TREINO NA API DO STRAVA
    try:
        headers = {'Authorization': f"Bearer {access_token}"}
        url = f"https://www.strava.com/api/v3/activities/{atividade_id}"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"❌ Erro Strava API ({response.status_code}): {response.text}")
            return False
            
        dados_treino = response.json()
    except Exception as e:
        logger.error(f"❌ Erro de conexão com Strava: {e}")
        return False

    # 6. 🧙‍♂️ A MÁGICA: CALCULAR XP E MOEDAS
    xp_total, lista_bonus = calcular_xp_avancado(dados_treino)

    # Regra Econômica
    coins_ganhas = int(xp_total / TAXA_CONVERSAO_COINS)
    if xp_total > 0 and coins_ganhas < 1: coins_ganhas = 1

    logger.info(f"💰 SUCESSO! User {user_id} -> XP: {xp_total} | Coins: {coins_ganhas}")

    # 7. PERSISTÊNCIA E APLICAÇÃO DE GANHOS
    try:
        # A. Salvar Atividade Bruta (Para histórico detalhado)
        dados_treino["aura_analysis"] = {
            "xp_ganho": xp_total,
            "coins_ganhas": coins_ganhas,
            "bonus": lista_bonus,
            "processed_at": datetime.now()
        }
        salvar_atividade_strava(user_id, dados_treino)

        # B. Aplicar XP e Nível (Usando a lógica centralizada de gamificação)
        resultado_xp = aplicar_xp(user_id, xp_total)
        
        # C. Adicionar Coins e Atualizar Saldo (Manual, pois aplicar_xp cuida só de XP/Cristais)
        mongo_db["users"].update_one(
            {"_id": usuario["_id"]},
            {
                "$inc": {"jogador.saldo_coins": coins_ganhas}
            }
        )
        
        # Log de sucesso
        if resultado_xp.get("subiu"):
            logger.info(f"🆙 USUÁRIO SUBIU DE NÍVEL COM O TREINO! Nível {resultado_xp['novo_nivel']}")

        return True
    except Exception as e:
        logger.error(f"❌ Erro ao salvar dados pós-treino: {e}")
        return False

def obter_token_valido(usuario: dict) -> str:
    """
    Gerencia a renovação do token OAuth2 olhando para o Schema correto.
    """
    # Acesso seguro ao dicionário aninhado
    integracao = usuario.get('integracoes', {}).get('strava', {})
    tokens = integracao.get('tokens', {})
    
    access_token = tokens.get('access_token')
    expires_at = tokens.get('expires_at')
    refresh_token = tokens.get('refresh_token')
    
    # Margem de segurança de 5 minutos
    agora = time.time()
    
    if expires_at and agora < (expires_at - 300):
        return access_token
        
    logger.info("⏳ Token Strava expirado. Solicitando renovação...")
    
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
            
            # Atualiza no Banco (Caminho aninhado correto)
            mongo_db["users"].update_one(
                {"_id": usuario["_id"]},
                {"$set": {
                    "integracoes.strava.tokens.access_token": novos_dados.get('access_token'),
                    "integracoes.strava.tokens.refresh_token": novos_dados.get('refresh_token'),
                    "integracoes.strava.tokens.expires_at": novos_dados.get('expires_at')
                }}
            )
            logger.info("✅ Token Strava renovado e salvo!")
            return novos_dados.get('access_token')
        else:
            logger.error(f"❌ Erro renovação Strava: {res.text}")
            return None
    except Exception as e:
        logger.error(f"❌ Erro de conexão na renovação: {e}")
        return None

def calcular_xp_avancado(treino: dict) -> tuple:
    """
    Aplica as regras de gamificação. Retorna (xp_total, lista_de_motivos).
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

    # --- REGRAS ---

    # 1. Distância
    distancia_km = distancia_m / 1000
    xp_distancia = int(distancia_km * XP_POR_KM)
    
    # XP Mínimo para qualquer atividade válida (>100m)
    if xp_distancia < 10 and distancia_km > 0.1: 
        xp_distancia = 10 
    
    if xp_distancia > 0:
        xp_acumulado += xp_distancia
        motivos.append(f"Distância ({distancia_km:.1f}km)")

    # 2. Madrugador (04h - 08h)
    if 4 <= hora_treino < 8:
        xp_acumulado += XP_BONUS_MADRUGADA
        motivos.append("☀️ Bônus Madrugador")

    # 3. Rei da Montanha
    if elevacao_m > 50:
        xp_subida = int(elevacao_m * XP_POR_METRO_ELEVACAO)
        xp_acumulado += xp_subida
        motivos.append(f"⛰️ Rei da Montanha (+{int(elevacao_m)}m)")

    # 4. The Flash (Velocidade)
    if velocidade_media_ms > VELOCIDADE_FLASH_MS:
        xp_acumulado += XP_BONUS_FLASH
        motivos.append("⚡ Ritmo The Flash")

    return xp_acumulado, motivos