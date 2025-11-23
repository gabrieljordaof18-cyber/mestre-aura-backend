import requests
from datetime import datetime
from data_manager import mongo_db

# =========================================================
# 🧠 CÉREBRO DA INTEGRAÇÃO STRAVA
# =========================================================

def processar_evento_webhook(dados_evento):
    """
    Função principal chamada quando o Strava avisa de algo.
    Orquestra todo o processo de ler, calcular e salvar.
    """
    print(f"🔄 [LOGIC] Processando evento: {dados_evento}")

    # 1. FILTRO DE SEGURANÇA
    # Só queremos saber de 'activity' (atividades) que foram 'create' (criadas agora).
    # Ignoramos atualizações ou deleções por enquanto.
    tipo_objeto = dados_evento.get('object_type') # ex: 'activity'
    tipo_acao = dados_evento.get('aspect_type')   # ex: 'create'
    atividade_id = dados_evento.get('object_id')  # ID do treino no Strava
    strava_id_usuario = dados_evento.get('owner_id') # ID do atleta

    if tipo_objeto != 'activity' or tipo_acao != 'create':
        print("⏩ [LOGIC] Ignorando evento (não é criação de atividade).")
        return False

    # 2. IDENTIFICAR O JOGADOR
    # Vamos ao banco procurar quem tem esse strava_id
    if mongo_db is None:
        print("❌ [LOGIC] Erro: Banco de dados desconectado.")
        return False

    usuario = mongo_db["usuarios"].find_one({"strava_id": strava_id_usuario})
    
    if not usuario:
        print(f"⚠️ [LOGIC] Usuário Strava ID {strava_id_usuario} não encontrado no banco.")
        return False

    # 3. OBTER TOKEN DE ACESSO
    # Precisamos da chave para ler os detalhes do treino
    # NOTA: No futuro, faremos a renovação automática do token aqui se ele tiver expirado.
    access_token = usuario['tokens']['access_token']

    # 4. BUSCAR DETALHES DO TREINO (A API REAL)
    headers = {'Authorization': f"Bearer {access_token}"}
    url_atividade = f"https://www.strava.com/api/v3/activities/{atividade_id}"
    
    response = requests.get(url_atividade, headers=headers)
    
    if response.status_code != 200:
        print(f"❌ [LOGIC] Erro ao ler atividade no Strava: {response.text}")
        return False

    dados_treino = response.json()

    # 5. CÁLCULO DE XP (GAMIFICAÇÃO BÁSICA)
    # Extraímos os dados principais
    distancia_metros = dados_treino.get('distance', 0)
    tempo_segundos = dados_treino.get('moving_time', 0)
    tipo_esporte = dados_treino.get('type', 'Run')
    
    xp_ganho = calcular_xp(distancia_metros, tempo_segundos, tipo_esporte)

    print(f"💰 [LOGIC] Atividade processada! Distância: {distancia_metros}m | XP Gerado: {xp_ganho}")

    # 6. SALVAR NO BANCO (HISTÓRICO E EVOLUÇÃO)
    # Atualizamos o usuário somando o XP
    mongo_db["usuarios"].update_one(
        {"strava_id": strava_id_usuario},
        {
            "$inc": {"xp_total": xp_ganho}, # Incrementa o XP total
            "$push": { # Adiciona ao histórico de atividades
                "historico_atividades": {
                    "id_atividade": atividade_id,
                    "data": datetime.now(),
                    "tipo": tipo_esporte,
                    "distancia": distancia_metros,
                    "tempo": tempo_segundos,
                    "xp_ganho": xp_ganho
                }
            }
        }
    )
    
    return True

def calcular_xp(distancia, tempo, tipo):
    """
    Regra matemática simples para gerar XP.
    - 1 km (1000m) = 50 XP
    - 1 minuto (60s) = 2 XP (Bônus de esforço)
    """
    xp_distancia = (distancia / 1000) * 50
    xp_tempo = (tempo / 60) * 2
    
    total = int(xp_distancia + xp_tempo)
    
    # Bônus para corridas
    if tipo == 'Run':
        total = int(total * 1.2) # 20% extra para corredores
        
    return total