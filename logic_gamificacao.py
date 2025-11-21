# logic_gamificacao.py
import random
from datetime import datetime
from data_global import carregar_memoria_global, salvar_memoria_global
from data_user import carregar_memoria, salvar_memoria
from data_manager import carregar_json

# ======================================================
# 🎮 LÓGICA CENTRAL DE GAMIFICAÇÃO
# ======================================================

def gerar_missoes_diarias():
    """
    Lê o banco_de_missoes.json e sorteia 3 novas missões para o dia.
    Salva na memória global.
    """
    # 1. Carregar Banco de Missões
    todas_missoes = carregar_json("banco_de_missoes.json", schema_padrao=[])
    
    if not todas_missoes:
        # Fallback se o arquivo estiver vazio
        todas_missoes = [{"id": "fallback", "descricao": "Treinar hoje", "xp": 50}]

    # 2. Sortear 3 missões
    # (Futuramente podemos filtrar por categoria aqui)
    novas = random.sample(todas_missoes, min(3, len(todas_missoes)))

    # 3. Preparar para salvar (adicionar status)
    missoes_ativas = []
    for m in novas:
        missoes_ativas.append({
            "id": m["id"],
            "descricao": m["descricao"],
            "xp": m["xp"],
            "concluida": False
        })

    # 4. Salvar na Memória Global (Onde vive o estado do jogo)
    mg = carregar_memoria_global()
    mg["gamificacao"]["missoes_diarias_historico"].append({
        "data": str(datetime.now().date()),
        "missoes": missoes_ativas
    })
    salvar_memoria_global(mg)

    # 5. Salvar na Memória Local (O que o usuário vê agora)
    memoria = carregar_memoria()
    memoria["gamificacao"]["missoes_ativas"] = missoes_ativas
    memoria["gamificacao"]["ultima_geracao_missoes"] = str(datetime.now())
    salvar_memoria(memoria)

    return missoes_ativas

def calcular_xp_fisiologico(dados_fisiologicos):
    """
    Calcula XP baseado puramente no esforço físico do dia.
    Substitui a lógica antiga que estava espalhada no shell script.
    """
    xp_ganho = 0
    
    # Regra 1: Sono (até 50 XP)
    try:
        horas = float(dados_fisiologicos.get("sono", {}).get("horas", 0))
        if horas >= 7: xp_ganho += 50
        elif horas >= 6: xp_ganho += 30
    except: pass

    # Regra 2: Treino Intenso (até 100 XP)
    try:
        intensidade = int(dados_fisiologicos.get("treino", {}).get("intensidade", 0))
        duracao = int(dados_fisiologicos.get("treino", {}).get("duracao_min", 0))
        
        if intensidade > 80 or duracao > 45:
            xp_ganho += 100
        elif intensidade > 50:
            xp_ganho += 50
    except: pass

    return xp_ganho

def aplicar_xp(quantidade):
    """Adiciona XP ao jogador e verifica Level Up."""
    memoria = carregar_memoria()
    jogador = memoria["jogador"]
    
    # Adiciona XP
    jogador["experiencia"] += quantidade
    
    # Lógica de Nível (Ex: Nível = Raiz Quadrada do XP / 10 ou simples divisão)
    # Vamos usar: Cada nível custa 1000 XP * Nível Atual
    xp_para_proximo = 1000 * jogador["nivel"]
    
    subiu = False
    if jogador["experiencia"] >= xp_para_proximo:
        jogador["nivel"] += 1
        jogador["experiencia"] = 0 # Ou mantém acumulado, depende do seu estilo. 
        # No seu estilo anterior zerava, então mantivemos zerar a barra do nível.
        subiu = True
        
    salvar_memoria(memoria)
    return {"novo_xp": jogador["experiencia"], "novo_nivel": jogador["nivel"], "subiu": subiu}