# data_global.py
import os
from datetime import datetime
from data_manager import carregar_json, salvar_json
from schema import obter_schema_padrao_global

# Caminhos fixos
CAMINHO_DIR = "memoria_global"
CAMINHO_ARQUIVO = os.path.join(CAMINHO_DIR, "memoria_global.json")

def carregar_memoria_global():
    """Carrega memória da IA usando o Guardião."""
    padrao = obter_schema_padrao_global()
    return carregar_json(CAMINHO_ARQUIVO, schema_padrao=padrao)

def salvar_memoria_global(dados):
    """Salva memória da IA de forma segura."""
    return salvar_json(CAMINHO_ARQUIVO, dados)

# --- Funções Específicas de Lógica Global ---
# (Mantemos a lógica de negócio aqui, mas o salvamento é via Guardião)

def registrar_interacao_global(sentimento="neutro", mensagem=""):
    mg = carregar_memoria_global()
    ts = str(datetime.now())
    
    entry = {
        "sentimento": sentimento,
        "mensagem": mensagem,
        "timestamp": ts
    }
    mg["interacoes"].append(entry)
    
    # Atualiza estatísticas simples
    stats = mg["estatisticas"]
    stats["total"] += 1
    if sentimento == "positivo": stats["positivas"] += 1
    elif sentimento == "negativo": stats["negativas"] += 1
    else: stats["neutras"] += 1
    
    # Atualiza afinidade (simplificada para não quebrar fluxo)
    # Na fase 2 moveremos lógica matemática para 'logic'
    score_atual = mg["afinidade"]["score"]
    delta = 5 if sentimento == "positivo" else (-5 if sentimento == "negativo" else 0)
    mg["afinidade"]["score"] = max(0, min(100, score_atual + delta))
    mg["afinidade"]["ultima_atualizacao"] = ts

    salvar_memoria_global(mg)
    return entry

def obter_afinidade():
    mg = carregar_memoria_global()
    return mg.get("afinidade", {"score": 50})