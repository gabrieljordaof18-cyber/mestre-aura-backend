# main.py
import os
import sys
import threading
import time
from datetime import datetime

# Importa módulos do sistema
from app import app # Importa o servidor Flask
from data_manager import carregar_json, salvar_json
from schema import obter_schema_padrao_global, obter_schema_padrao_usuario
from logic_gamificacao import gerar_missoes_diarias
from logic_equilibrio import calcular_e_atualizar_equilibrio

# ==============================================================
# 🛠️ FUNÇÕES DE INICIALIZAÇÃO (BOOT)
# ==============================================================

def verificar_ambiente():
    """Cria pastas e arquivos essenciais se não existirem."""
    print("🔹 [BOOT] Verificando integridade do sistema...")
    
    # 1. Pastas
    pastas = ["memoria_global", "logs", "static/images"]
    for p in pastas:
        os.makedirs(p, exist_ok=True)
        
    # 2. Arquivos de Dados (Garante que existem e são válidos)
    # Memória Global
    caminho_global = "memoria_global/memoria_global.json"
    if not os.path.exists(caminho_global):
        print("🔸 Criando Memória Global inicial...")
        salvar_json(caminho_global, obter_schema_padrao_global())
        
    # Memória Usuário
    caminho_user = "memoria.json"
    if not os.path.exists(caminho_user):
        print("🔸 Criando Memória do Usuário inicial...")
        salvar_json(caminho_user, obter_schema_padrao_usuario())
        
    # Banco de Missões (Se não existir, cria um básico)
    if not os.path.exists("banco_de_missoes.json"):
        print("🔸 Criando Banco de Missões padrão...")
        missoes_padrao = [
            {"id": "m1", "descricao": "Beber 2L de água", "xp": 50},
            {"id": "m2", "descricao": "Dormir 8h", "xp": 100},
            {"id": "m3", "descricao": "Treinar 30min", "xp": 80}
        ]
        salvar_json("banco_de_missoes.json", missoes_padrao)

    print("✅ [BOOT] Sistema de arquivos íntegro.")

def rotina_diaria():
    """
    Executa tarefas automáticas ao iniciar
    (Gera missões do dia se ainda não tiver).
    """
    print("🔹 [SISTEMA] Verificando rotinas diárias...")
    try:
        # Gera novas missões se necessário
        gerar_missoes_diarias()
        # Recalcula equilíbrio inicial
        calcular_e_atualizar_equilibrio()
        print("✅ [SISTEMA] Rotinas concluídas.")
    except Exception as e:
        print(f"⚠️ Erro na rotina diária: {e}")

# ==============================================================
# 🚀 EXECUÇÃO PRINCIPAL
# ==============================================================

if __name__ == '__main__':
    print("=========================================")
    print("   🔱 SISTEMA MESTRE DA AURA (Base44)   ")
    print("=========================================")
    
    # 1. Prepara o terreno
    verificar_ambiente()
    rotina_diaria()
    
    # 2. Inicia o Servidor Web
    print("\n🌍 Iniciando Servidor AURA...")
    print("👉 Acesso: http://localhost:5050/recurso/mestre")
    print("=========================================\n")
    
    # Roda o Flask (app.py)
    # debug=True ajuda no desenvolvimento, reload automático
    app.run(host='0.0.0.0', port=5050, debug=True)