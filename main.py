import os
import logging
from app import app # Importa a instância configurada do Flask
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AURA_STARTUP")

# ======================================================
# 🕛 AGENDADOR DE TAREFAS (SCHEDULER)
# ======================================================
def rotina_diaria_sistema():
    """
    Executa tarefas de manutenção todo dia à meia-noite.
    Ex: Resetar missões diárias, limpar caches antigos.
    """
    logger.info(f"🕛 [SCHEDULER] Iniciando rotina de manutenção: {datetime.now()}")
    # No futuro, aqui chamaremos o reset_missoes() do logic_gamificacao

scheduler = BackgroundScheduler()
scheduler.add_job(rotina_diaria_sistema, 'cron', hour=0, minute=0)

# ======================================================
# 🚀 PONTO DE ENTRADA DO SERVIDOR (AURA OS)
# ======================================================

if __name__ == '__main__':
    # 1. Inicia o agendador de missões e manutenção
    if not scheduler.running:
        scheduler.start()
        logger.info("✅ Agendador de tarefas Aura OS ativado.")

    # 2. Define a Porta (Prioridade para o Render, fallback para 5050 local)
    port = int(os.environ.get("PORT", 5050))
    
    # 3. Identifica o Ambiente e Lança o Motor Correto
    # Se houver uma PORT definida pelo sistema, estamos no Render
    if os.environ.get("PORT"):
        from waitress import serve
        logger.info(f"🚀 MODO PRODUÇÃO: Aura OS operando via Waitress na porta {port}")
        serve(app, host='0.0.0.0', port=port)
    else:
        # Modo de desenvolvimento no seu MacBook
        logger.info(f"🛠️ MODO DEV: Aura OS operando via Flask na porta {port}")
        app.run(host='0.0.0.0', port=port, debug=True)