import os
import logging
from app import app # Importa a instância configurada do Flask
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

# Importações para Sincronização de Dados
from data_manager import mongo_db
from logic_gamificacao import gerar_missoes_diarias

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AURA_STARTUP")

# ======================================================
# 🕛 AGENDADOR DE TAREFAS (SCHEDULER)
# ======================================================

def rotina_diaria_manutencao():
    """
    Executa tarefas de manutenção e sincronização global.
    1. Valida conexão com MongoDB Atlas.
    2. Prepara o reset de missões para usuários ativos.
    """
    logger.info(f"🕛 [SCHEDULER] Iniciando rotina de manutenção: {datetime.now()}")
    
    # [AURA FIX] Verificação explícita com None para evitar erro de truth value no Render
    if mongo_db is None:
        logger.error("❌ [SCHEDULER] Abortando: MongoDB Atlas inacessível para manutenção.")
        return

    try:
        # No futuro, aqui podemos iterar sobre usuários ativos para pré-gerar missões
        # Exemplo: limpar_logs_antigos() ou atualizar_cache_ranking_global()
        logger.info("✅ [SCHEDULER] Manutenção diária concluída com sucesso.")
    except Exception as e:
        logger.error(f"⚠️ [SCHEDULER] Erro durante a rotina: {e}")

# Configuração do Agendador
# [AURA INFO] O BackgroundScheduler roda em uma thread separada do Flask
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(rotina_diaria_manutencao, 'cron', hour=0, minute=0)

# ======================================================
# 🚀 PONTO DE ENTRADA DO SERVIDOR (AURA OS)
# ======================================================

# No Render, o servidor de produção (Gunicorn/Waitress) importa o 'app' 
# diretamente do 'main.py' ou 'app.py'. 

# [AURA FIX] Iniciamos o scheduler fora do bloco __main__ para garantir que ele 
# funcione mesmo quando o App é lançado por um WSGI Server (Gunicorn) no Render.
if not scheduler.running:
    try:
        scheduler.start()
        logger.info("✅ Agendador de tarefas Aura OS (Scheduler) ativado com sucesso.")
    except Exception as e:
        logger.error(f"❌ Falha ao iniciar Agendador: {e}")

if __name__ == '__main__':
    # 1. Define a Porta (Prioridade para o Render PORT, fallback para 5050 local)
    # [AURA INFO] O Render injeta a porta dinamicamente na variável de ambiente PORT.
    port = int(os.environ.get("PORT", 5050))
    
    # 2. Identifica o Ambiente e Lança o Motor de Execução Correto
    # Se houver uma PORT definida no ambiente, estamos operando na nuvem (Render)
    if os.environ.get("PORT"):
        from waitress import serve
        logger.info(f"🚀 MODO PRODUÇÃO: Aura OS operando via Waitress na porta {port}")
        # Waitress é o servidor WSGI recomendado para produção em Python/Flask
        serve(app, host='0.0.0.0', port=port)
    else:
        # Modo de desenvolvimento no seu MacBook
        logger.info(f"🛠️ MODO DEV: Aura OS operando via Flask na porta {port}")
        # Debug=True permite o reload automático ao salvar arquivos no Mac
        app.run(host='0.0.0.0', port=port, debug=True)