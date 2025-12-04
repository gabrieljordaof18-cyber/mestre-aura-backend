import logging
import random
from datetime import datetime
from typing import Dict, Any, List, Union
from data_global import carregar_memoria_global, salvar_memoria_global
from data_user import carregar_memoria, salvar_memoria
from data_manager import carregar_json

# Configuração de Logs
logger = logging.getLogger("AURA_GAMIFICACAO")

# ======================================================
# ⚙️ CONSTANTES DE JOGO (Balanceamento)
# ======================================================
XP_BASE_NIVEL = 1000        # Quanto custa o Nível 1
XP_SONO_OTIMO = 50          # > 7h
XP_SONO_BOM = 30            # > 6h
XP_TREINO_INSANO = 100      # Intensidade > 80%
XP_TREINO_BOM = 50          # Intensidade > 50%

# Economia Premium
CRISTAIS_POR_LEVEL_UP = 10  # Recompensa fixa ao subir de nível

# ======================================================
# 🎮 LÓGICA CENTRAL DE GAMIFICAÇÃO
# ======================================================

def gerar_missoes_diarias() -> List[Dict[str, Any]]:
    """
    Sorteia 3 novas missões para o dia.
    Possui verificação de idempotência (não gera duplicado no mesmo dia).
    """
    memoria = carregar_memoria()
    hoje_str = str(datetime.now().date())
    
    # 1. Verificação de Idempotência (Já gerou hoje?)
    ultima_geracao = memoria.get("gamificacao", {}).get("ultima_geracao_missoes", "").split(" ")[0]
    missoes_atuais = memoria.get("gamificacao", {}).get("missoes_ativas", [])

    if ultima_geracao == hoje_str and missoes_atuais:
        logger.info("📅 Missões de hoje já existem. Retornando cacheadas.")
        return missoes_atuais

    # 2. Carregar Banco de Missões
    todas_missoes = carregar_json("banco_de_missoes.json", schema_padrao=[])
    
    if not todas_missoes:
        todas_missoes = [{"id": "fallback", "descricao": "Treinar hoje", "xp": 50}]

    # 3. Sortear 3 missões
    novas = random.sample(todas_missoes, min(3, len(todas_missoes)))

    missoes_ativas = []
    for m in novas:
        missoes_ativas.append({
            "id": m["id"],
            "descricao": m["descricao"],
            "xp": m["xp"],
            "concluida": False
        })

    # 4. Salvar na Memória Global (Histórico)
    mg = carregar_memoria_global()
    if "gamificacao" not in mg: mg["gamificacao"] = {}
    if "missoes_diarias_historico" not in mg["gamificacao"]: 
        mg["gamificacao"]["missoes_diarias_historico"] = []
        
    mg["gamificacao"]["missoes_diarias_historico"].append({
        "data": hoje_str,
        "missoes": missoes_ativas
    })
    salvar_memoria_global(mg)

    # 5. Salvar na Memória Local (Estado Atual)
    if "gamificacao" not in memoria: memoria["gamificacao"] = {}
    
    memoria["gamificacao"]["missoes_ativas"] = missoes_ativas
    memoria["gamificacao"]["ultima_geracao_missoes"] = str(datetime.now())
    salvar_memoria(memoria)

    logger.info(f"🎲 Novas missões geradas para {hoje_str}")
    return missoes_ativas

def calcular_xp_fisiologico(dados_fisiologicos: Dict[str, Any]) -> int:
    """
    Calcula XP baseado puramente no esforço físico do dia (Sensores).
    """
    xp_ganho = 0
    
    # Helpers de extração segura
    horas_sono = _extrair_valor(dados_fisiologicos, "sono", "horas")
    intensidade_treino = _extrair_valor(dados_fisiologicos, "treino", "intensidade")
    duracao_treino = _extrair_valor(dados_fisiologicos, "treino", "duracao_min")

    # Regra 1: Sono
    if horas_sono >= 7: xp_ganho += XP_SONO_OTIMO
    elif horas_sono >= 6: xp_ganho += XP_SONO_BOM

    # Regra 2: Treino
    if intensidade_treino > 80 or duracao_treino > 45:
        xp_ganho += XP_TREINO_INSANO
    elif intensidade_treino > 50:
        xp_ganho += XP_TREINO_BOM

    return xp_ganho

def aplicar_xp(quantidade: int) -> Dict[str, Any]:
    """
    Adiciona XP ao jogador, verifica Level Up e concede bônus de Cristais Aura.
    """
    memoria = carregar_memoria()
    jogador = memoria.get("jogador", {})
    
    # Garante integridade dos dados
    if "experiencia" not in jogador: jogador["experiencia"] = 0
    if "nivel" not in jogador: jogador["nivel"] = 1
    if "saldo_cristais" not in jogador: jogador["saldo_cristais"] = 0 # Garante que o campo existe
    
    # Adiciona XP
    jogador["experiencia"] += quantidade
    subiu_de_nivel = False
    cristais_ganhos_total = 0
    
    # Loop de Level Up (Permite subir múltiplos níveis de uma vez)
    while True:
        xp_para_proximo = XP_BASE_NIVEL * jogador["nivel"]
        
        if jogador["experiencia"] >= xp_para_proximo:
            jogador["experiencia"] -= xp_para_proximo # Carry Over
            jogador["nivel"] += 1
            
            # BÔNUS DE LEVEL UP (ECONOMIA PREMIUM)
            jogador["saldo_cristais"] += CRISTAIS_POR_LEVEL_UP
            cristais_ganhos_total += CRISTAIS_POR_LEVEL_UP
            
            subiu_de_nivel = True
            logger.info(f"🆙 LEVEL UP! Nível {jogador['nivel']} | +{CRISTAIS_POR_LEVEL_UP} Cristais")
        else:
            break
            
    # Salva
    memoria["jogador"] = jogador
    salvar_memoria(memoria)
    
    return {
        "novo_xp": jogador["experiencia"], 
        "novo_nivel": jogador["nivel"], 
        "subiu": subiu_de_nivel,
        "cristais_ganhos": cristais_ganhos_total
    }

# --- Função Auxiliar Local ---
def _extrair_valor(dados: dict, chave: str, subchave: str) -> float:
    """Extrai valor numérico lidando com dicionários aninhados ou valores diretos."""
    raw = dados.get(chave, 0)
    try:
        if isinstance(raw, dict):
            return float(raw.get(subchave, 0))
        return float(raw)
    except (ValueError, TypeError):
        return 0.0