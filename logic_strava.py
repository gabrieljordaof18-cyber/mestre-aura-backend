import requests
from datetime import datetime
from data_manager import mongo_db

# =========================================================
# 🧠 CÉREBRO DA INTEGRAÇÃO STRAVA (VERSÃO 2.0 - GAMIFICADA)
# =========================================================

def processar_evento_webhook(dados_evento):
    """
    Função principal.
    Recebe o aviso -> Pega dados -> Aplica Regras de XP -> Salva.
    """
    print(f"🔄 [LOGIC] Processando evento Strava...")

    # 1. FILTRO DE SEGURANÇA
    # Só processamos criações de novas atividades
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

    # 3. BUSCAR DETALHES DO TREINO NA API DO STRAVA
    # (Aqui precisaríamos renovar o token se estivesse expirado, mas para MVP assumimos que está válido)
    access_token = usuario['tokens']['access_token']
    headers = {'Authorization': f"Bearer {access_token}"}
    url = f"https://www.strava.com/api/v3/activities/{atividade_id}"
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"❌ Erro Strava API: {response.text}")
        return False

    dados_treino = response.json()

    # 4. 🧙‍♂️ A MÁGICA: CALCULAR XP AVANÇADO
    # Chamamos a nova função de regras complexas
    xp_total, lista_bonus = calcular_xp_avancado(dados_treino)

    print(f"💰 TREINO PROCESSADO! XP Total: {xp_total}")
    print(f"📜 Bônus aplicados: {lista_bonus}")

    # 5. SALVAR NO BANCO
    # Atualizamos o XP Total e guardamos o histórico com os detalhes dos bônus
    mongo_db["usuarios"].update_one(
        {"strava_id": strava_id_usuario},
        {
            "$inc": {"xp_total": xp_total},
            "$push": { 
                "historico_atividades": {
                    "id_atividade": atividade_id,
                    "data": datetime.now(),
                    "nome_treino": dados_treino.get('name'),
                    "distancia_km": round(dados_treino.get('distance', 0) / 1000, 2),
                    "xp_ganho": xp_total,
                    "bonus_conquistados": lista_bonus # <--- O App vai ler isso para mostrar as medalhas
                }
            }
        }
    )
    
    return True

def calcular_xp_avancado(treino):
    """
    Aplica as regras de gamificação do AURA.
    Retorna: (Inteiro XP, Lista de Strings com os motivos)
    """
    xp_acumulado = 0
    motivos = []

    # Extraindo dados (O Strava manda sempre em metros e segundos)
    distancia_m = treino.get('distance', 0.0)
    tempo_s = treino.get('moving_time', 0)
    elevacao_m = treino.get('total_elevation_gain', 0.0)
    velocidade_media_ms = treino.get('average_speed', 0.0)
    
    # Tratamento da Hora (Strava manda ex: "2025-11-24T06:30:00Z")
    data_local = treino.get('start_date_local', '')
    hora_treino = 12 # Valor padrão seguro
    try:
        if data_local:
            # Pega apenas a hora (ex: 06) da string
            hora_treino = int(data_local.split('T')[1].split(':')[0])
    except:
        pass

    # --- REGRA 1: BASE DE DISTÂNCIA (10 XP por km) ---
    distancia_km = distancia_m / 1000
    xp_distancia = int(distancia_km * 10)
    
    # Garante no mínimo 10XP se correu alguma coisa
    if xp_distancia < 10 and distancia_km > 0.1:
        xp_distancia = 10
        
    xp_acumulado += xp_distancia
    motivos.append(f"Distância ({distancia_km:.1f}km): +{xp_distancia}")

    # --- REGRA 2: MADRUGADOR (Treino entre 04h e 08h) ---
    if 4 <= hora_treino < 8:
        xp_acumulado += 50
        motivos.append("☀️ Madrugador: +50")

    # --- REGRA 3: REI DA MONTANHA (Elevação > 50m) ---
    if elevacao_m > 50:
        # 2 XP por metro subido
        xp_subida = int(elevacao_m * 2)
        xp_acumulado += xp_subida
        motivos.append(f"⛰️ Rei da Montanha ({elevacao_m:.0f}m): +{xp_subida}")

    # --- REGRA 4: THE FLASH (Velocidade > 10km/h) ---
    # 10 km/h é aproximadamente 2.78 m/s
    if velocidade_media_ms > 2.78:
        xp_acumulado += 30
        motivos.append("⚡ The Flash (Ritmo Alto): +30")

    return xp_acumulado, motivos