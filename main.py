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
    # Aqui chamaremos funções do logic_gamificacao no futuro

scheduler = BackgroundScheduler()
scheduler.add_job(rotina_diaria_sistema, 'cron', hour=0, minute=0)

# ======================================================
# 🚀 PONTO DE ENTRADA DO SERVIDOR
# ======================================================

if __name__ == '__main__':
    # Inicia o agendador antes de ligar o servidor
    if not scheduler.running:
        scheduler.start()
        logger.info("✅ Agendador de tarefas Aura OS ativado.")

    # Porta definida pelo Render ou 5050 para o seu MacBook
    port = int(os.environ.get("PORT", 5050))
    
    logger.info(f"🔥 Aura OS está ONLINE na porta {port}")
    
    # Rodamos o app importado do arquivo app.py
    import uvicorn
    # Usamos o adaptador para Flask rodar via comando de servidor moderno
    from waitress import serve
    
    if os.environ.get("FLASK_ENV") == "production":
        serve(app, host='0.0.0.0', port=port)
    else:
        app.run(host='0.0.0.0', port=port, debug=True)