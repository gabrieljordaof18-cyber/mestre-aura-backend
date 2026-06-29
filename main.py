"""
main.py — Ponto de entrada para execução LOCAL (python main.py).
Em produção o Gunicorn importa app:app diretamente; o scheduler
é inicializado em app.py e permanece ativo em cada worker.
"""
import os
import logging
from app import app  # importar app já inicia o scheduler via app.py

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AURA_STARTUP")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5050))
    if os.environ.get("PORT"):
        from waitress import serve
        logger.info(f"🚀 PRODUÇÃO: Aura OS via Waitress na porta {port}")
        serve(app, host='0.0.0.0', port=port)
    else:
        logger.info(f"🛠️ DEV: Aura OS via Flask na porta {port}")
        app.run(host='0.0.0.0', port=port, debug=True)