import os
from datetime import datetime
from typing import Dict, Any
from data_manager import carregar_json, salvar_json
from schema import obter_schema_padrao_global

# Configuração de Caminhos
CAMINHO_DIR = "memoria_global"
CAMINHO_ARQUIVO = os.path.join(CAMINHO_DIR, "memoria_global.json")

def carregar_memoria_global() -> Dict[str, Any]:
    """
    Carrega o estado global da IA (afinidade, stats, etc).
    Usa o Guardião (data_manager) para garantir integridade.
    """
    padrao = obter_schema_padrao_global()
    return carregar_json(CAMINHO_ARQUIVO, schema_padrao=padrao)

def salvar_memoria_global(dados: Dict[str, Any]) -> bool:
    """Persiste o estado global de forma segura."""
    return salvar_json(CAMINHO_ARQUIVO, dados)

# --- Lógica de Estado Global (Business Logic) ---

def registrar_interacao_global(sentimento: str = "neutro", mensagem: str = "") -> Dict[str, Any]:
    """
    Registra uma interação no histórico e recalcula afinidade/estatísticas.
    """
    mg = carregar_memoria_global()
    ts = str(datetime.now())
    
    entry = {
        "sentimento": sentimento,
        "mensagem": mensagem,
        "timestamp": ts
    }
    
    # 1. Adiciona ao Histórico (Defensivo: cria lista se não existir)
    if "interacoes" not in mg: mg["interacoes"] = []
    mg["interacoes"].append(entry)
    
    # 2. Atualiza Estatísticas
    if "estatisticas" not in mg: 
        mg["estatisticas"] = {"positivas": 0, "negativas": 0, "neutras": 0, "total": 0}
        
    stats = mg["estatisticas"]
    stats["total"] += 1
    
    if sentimento == "positivo": 
        stats["positivas"] += 1
    elif sentimento == "negativo": 
        stats["negativas"] += 1
    else: 
        stats["neutras"] += 1
    
    # 3. Atualiza Afinidade (Lógica Refinada)
    # A IA valoriza consistência. Interações neutras também ajudam um pouco (atenção).
    if "afinidade" not in mg:
        mg["afinidade"] = {"score": 50, "min": 0, "max": 100}

    score_atual = mg["afinidade"].get("score", 50)
    delta = 0
    
    if sentimento == "positivo": 
        delta = 2.5  # Sobe com elogios
    elif sentimento == "negativo": 
        delta = -5.0 # Cai o dobro com ofensas (IA sensível)
    elif sentimento == "neutro": 
        delta = 0.5  # Sobe devagar apenas por interagir
    
    # Matemáticazinha para garantir limites (Clamp 0-100)
    novo_score = max(0, min(100, score_atual + delta))
    
    mg["afinidade"]["score"] = int(novo_score) # Arredonda para inteiro
    mg["afinidade"]["ultima_atualizacao"] = ts

    salvar_memoria_global(mg)
    return entry

def obter_afinidade() -> int:
    """Retorna o score de afinidade atual (0 a 100)."""
    mg = carregar_memoria_global()
    return mg.get("afinidade", {}).get("score", 50)