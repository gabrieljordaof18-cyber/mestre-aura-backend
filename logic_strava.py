import time
import requests
import os
from datetime import datetime
from data_manager import mongo_db

# =========================================================
# 🧠 CÉREBRO DA INTEGRAÇÃO STRAVA (VERSÃO 4.0 - ECONOMIA)
# =========================================================

def processar_evento_webhook(dados_evento):
    """
    Função principal.
    Recebe o aviso -> Garante Token Válido -> Pega dados -> Aplica XP e COINS -> Salva.
    """
    print(f"🔄 [LOGIC] Processando evento Strava...")

    # 1. FILTRO DE SEGURANÇA
    if dados_evento.get('object_type') != 'activity' or dados_evento.get('aspect_type') != 'create':
        return False

    strava_id_usuario = dados_evento.get('owner_id')
    atividade_id = dados_evento.get('object_id')

    # 2. IDENTIFICAR O JOGADOR
    if mongo_db is None:
        print("❌ Banco desconectado.")
        return False

    usuario = mongo_db["usuarios"].find_one({"strava_id": strava_id_usuario})
    if not usuario:
        print(f"⚠️ Usuário {strava_id_usuario} não encontrado.")
        return False

    # 3. GARANTIR TOKEN VÁLIDO (Renovação Automática)
    access_token = obter_token_valido(usuario)
    
    if not access_token:
        print("❌ Falha crítica: Não foi possível renovar o token.")
        return False

    # 4. BUSCAR DETALHES DO TREINO
    headers = {'Authorization': f"Bearer {access_token}"}
    url = f"https://www.strava.com/api/v3/activities/{atividade_id}"
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"❌ Erro Strava API: {response.text}")
        return False

    dados_treino = response.json()

    # 5. 🧙‍♂️ A MÁGICA: CALCULAR XP AVANÇADO E MOEDAS
    xp_total, lista_bonus = calcular_xp_avancado(dados_treino)

    # --- REGRA ECONÔMICA (Aura Coins) ---
    # Divisão por 20 para equilibrar com a meta de R$10,00/semana
    coins_ganhas = int(xp_total / 20)
    
    # Garante pelo menos 1 moeda se houve esforço (>0 XP)
    if xp_total > 0 and coins_ganhas < 1:
        coins_ganhas = 1

    print(f"💰 TREINO PROCESSADO! XP: {xp_total} | Coins: {coins_ganhas}")

    # 6. SALVAR NO BANCO
    mongo_db["usuarios"].update_one(
        {"strava_id": strava_id_usuario},
        {
            # $inc soma os valores ao que o usuário já tem
            "$inc": {
                "xp_total": xp_total,
                "aura_coins": coins_ganhas # <--- O SALÁRIO DO JOGADOR
            },
            "$push": { 
                "historico_atividades": {
                    "id_atividade": atividade_id,
                    "data": datetime.now(),
                    "nome_treino": dados_treino.get('name'),
                    "distancia_km": round(dados_treino.get('distance', 0) / 1000, 2),
                    "xp_ganho": xp_total,
                    "coins_ganhas": coins_ganhas, # <--- Histórico financeiro
                    "bonus_conquistados": lista_bonus
                }
            }
        }
    )
    
    return True

def obter_token_valido(usuario):
    """
    Verifica se o token venceu. Se venceu, usa o Refresh Token para pegar um novo.
    """
    tokens = usuario.get('tokens', {})
    access_token = tokens.get('access_token')
    expires_at = tokens.get('expires_at')
    refresh_token = tokens.get('refresh_token')
    
    # Margem de segurança de 5 minutos (300 segundos)
    agora = time.time()
    
    if expires_at and agora < (expires_at - 300):
        # Token ainda é válido
        return access_token
        
    print("⏳ Token expirado! Solicitando renovação ao Strava...")
    
    # URL para pedir novo token
    url_token = "https://www.strava.com/oauth/token"
    payload = {
        'client_id': os.getenv('STRAVA_CLIENT_ID'),
        'client_secret': os.getenv('STRAVA_CLIENT_SECRET'),
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }
    
    res = requests.post(url_token, data=payload)
    
    if res.status_code == 200:
        novos_dados = res.json()
        novo_access = novos_dados.get('access_token')
        novo_refresh = novos_dados.get('refresh_token')
        novo_expire = novos_dados.get('expires_at')
        
        # Atualiza no Banco para não precisar pedir de novo tão cedo
        mongo_db["usuarios"].update_one(
            {"strava_id": usuario['strava_id']},
            {"$set": {
                "tokens.access_token": novo_access,
                "tokens.refresh_token": novo_refresh,
                "tokens.expires_at": novo_expire
            }}
        )
        print("✅ Token renovado com sucesso!")
        return novo_access
    else:
        print(f"❌ Erro ao renovar token: {res.text}")
        return None

def calcular_xp_avancado(treino):
    """
    Aplica as regras de gamificação do AURA.
    """
    xp_acumulado = 0
    motivos = []

    distancia_m = treino.get('distance', 0.0)
    elevacao_m = treino.get('total_elevation_gain', 0.0)
    velocidade_media_ms = treino.get('average_speed', 0.0)
    
    data_local = treino.get('start_date_local', '')
    hora_treino = 12
    try:
        if data_local:
            hora_treino = int(data_local.split('T')[1].split(':')[0])
    except:
        pass

    # Regra 1: Distância
    distancia_km = distancia_m / 1000
    xp_distancia = int(distancia_km * 10)
    if xp_distancia < 10 and distancia_km > 0.1: xp_distancia = 10
    xp_acumulado += xp_distancia
    motivos.append(f"Distância ({distancia_km:.1f}km): +{xp_distancia}")

    # Regra 2: Madrugador
    if 4 <= hora_treino < 8:
        xp_acumulado += 50
        motivos.append("☀️ Madrugador: +50")

    # Regra 3: Rei da Montanha
    if elevacao_m > 50:
        xp_subida = int(elevacao_m * 2)
        xp_acumulado += xp_subida
        motivos.append(f"⛰️ Rei da Montanha ({elevacao_m:.0f}m): +{xp_subida}")

    # Regra 4: The Flash
    if velocidade_media_ms > 2.78:
        xp_acumulado += 30
        motivos.append("⚡ The Flash (Ritmo Alto): +30")

    return xp_acumulado, motivos