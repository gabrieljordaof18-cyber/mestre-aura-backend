import os
import logging
from datetime import datetime

# Importa módulos do sistema
from app import app 
from data_manager import salvar_json
from schema import obter_schema_padrao_global, obter_schema_padrao_usuario
from logic_gamificacao import gerar_missoes_diarias
from logic_equilibrio import calcular_e_atualizar_equilibrio

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AURA_BOOT")

# ==============================================================
# 🛠️ FUNÇÕES DE INICIALIZAÇÃO (BOOT)
# ==============================================================

def verificar_ambiente():
    """Cria pastas e arquivos essenciais se não existirem."""
    logger.info("🔹 [BOOT] Verificando integridade do sistema...")
    
    # 1. Pastas
    pastas = ["memoria_global", "logs", "static/images"]
    for p in pastas:
        os.makedirs(p, exist_ok=True)
        
    # 2. Arquivos de Dados (Garante que existem e são válidos)
    
    # Memória Global
    caminho_global = "memoria_global/memoria_global.json"
    if not os.path.exists(caminho_global):
        logger.warning("🔸 Criando Memória Global inicial...")
        salvar_json(caminho_global, obter_schema_padrao_global())
        
    # Memória Usuário
    caminho_user = "memoria.json"
    if not os.path.exists(caminho_user):
        logger.warning("🔸 Criando Memória do Usuário inicial...")
        salvar_json(caminho_user, obter_schema_padrao_usuario())
        
    # Banco de Missões
    if not os.path.exists("banco_de_missoes.json"):
        logger.warning("🔸 Criando Banco de Missões padrão...")
        missoes_padrao = [
            {"id": "m1", "descricao": "Beber 2L de água", "xp": 50, "categoria": "saude", "tipo_verificacao": "manual"},
            {"id": "m2", "descricao": "Dormir 8h", "xp": 100, "categoria": "descanso", "tipo_verificacao": "sensor_sono"},
            {"id": "m3", "descricao": "Treinar 30min", "xp": 80, "categoria": "treino", "tipo_verificacao": "sensor_cardio"}
        ]
        salvar_json("banco_de_missoes.json", missoes_padrao)

    logger.info("✅ [BOOT] Sistema de arquivos íntegro.")

def rotina_diaria():
    """
    Executa tarefas automáticas ao iniciar
    (Gera missões do dia se ainda não tiver).
    """
    logger.info("🔹 [SISTEMA] Verificando rotinas diárias...")
    try:
        # Gera novas missões se necessário
        gerar_missoes_diarias()
        # Recalcula equilíbrio inicial
        calcular_e_atualizar_equilibrio()
        logger.info("✅ [SISTEMA] Rotinas concluídas.")
    except Exception as e:
        logger.error(f"⚠️ Erro na rotina diária: {e}")

# ==============================================================
# 🚀 EXECUÇÃO PRINCIPAL
# ==============================================================

if __name__ == '__main__':
    # 1. Prepara o terreno
    verificar_ambiente()
    rotina_diaria()
    
    # 2. Configuração de Rede
    # No Render, a porta é fornecida via env. Localmente usamos 5050.
    porta = int(os.environ.get("PORT", 5050))
    
    logger.info("=========================================")
    logger.info(f"   🔱 SISTEMA MESTRE DA AURA ONLINE   ")
    logger.info(f"   👉 Porta: {porta}")
    logger.info("=========================================")
    
    # Roda o Flask
    # host='0.0.0.0' é obrigatório para o Render expor o serviço
    app.run(host='0.0.0.0', port=porta, debug=True)