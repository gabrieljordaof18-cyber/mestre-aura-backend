# data_user.py
import os
from data_manager import carregar_json, salvar_json
from schema import obter_schema_padrao_usuario

# Caminho fixo da memória local
CAMINHO_MEMORIA = "memoria.json"

def carregar_memoria():
    """Carrega perfil do jogador usando o Guardião e o Schema."""
    padrao = obter_schema_padrao_usuario()
    return carregar_json(CAMINHO_MEMORIA, schema_padrao=padrao)

def salvar_memoria(dados):
    """Salva perfil do jogador de forma segura."""
    return salvar_json(CAMINHO_MEMORIA, dados)

# Mantemos estas funções utilitárias para compatibilidade com seu código antigo
def redefinir_metas_usuario():
    memoria = carregar_memoria()
    padrao = obter_schema_padrao_usuario()
    memoria["jogador"]["metas"] = padrao["jogador"]["metas"]
    salvar_memoria(memoria)
    return True

def obter_status_fisiologico():
    memoria = carregar_memoria()
    return memoria.get("dados_fisiologicos", {})