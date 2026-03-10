import os
import logging
from app import app # Importa a instância única e configurada do Flask
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

# Importações para Sincronização de Dados e Nova Robustez
from data_manager import mongo_db
from data_global import carregar_memoria_global, registrar_interacao_global
from logic_gamificacao import gerar_missoes_diarias
from logic_equilibrio import resetar_homeostase_diaria # [AURA FIX] Vital para reset de fadiga

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AURA_STARTUP")

# ======================================================
# 🕛 AGENDADOR DE TAREFAS (SCHEDULER ROBUST 3.3.0)
# ======================================================

def rotina_diaria_manutencao():
    """
    Executa tarefas de manutenção e sincronização global.
    1. Valida conexão com MongoDB Atlas.
    2. Recalibra fadiga dos usuários para novos treinos robustos.
    3. Atualiza metadados da temporada global.
    """
    logger.info(f"🕛 [SCHEDULER] Iniciando manutenção neural Aura 3.3.0: {datetime.now()}")
    
    # [AURA FIX] Verificação explícita com None para segurança no MongoDB Atlas
    if mongo_db is None:
        logger.error("❌ [SCHEDULER] Abortando: Banco de dados inacessível.")
        return

    try:
        # Recupera estado global para auditoria de versão
        estado_global = carregar_memoria_global()
        logger.info(f"🌍 Aura OS operando na versão: {estado_global.get('versao_ia_ativa', '3.3.0-Native')}")

        # [AURA ROBUST] Iteração sobre usuários ativos para reset de fadiga
        colecao_users = mongo_db["usuarios"]
        # Buscamos apenas quem já passou pelo onboarding para economizar processamento
        usuarios_ativos = colecao_users.find({"configuracoes_sistema.onboarding_completo": True})
        
        count_reset = 0
        for user in usuarios_ativos:
            user_id = str(user["_id"])
            # O resetar_homeostase garante que a fadiga comece baixa para o treino do dia
            resetar_homeostase_diaria(user_id)
            count_reset += 1
            
        logger.info(f"✅ [SCHEDULER] Homeostase recalibrada para {count_reset} atletas.")
        
        # Registra a atividade de manutenção no analytics global
        registrar_interacao_global(sentimento="sistema", tipo_acao="manutencao_diaria")
        
        logger.info("✅ [SCHEDULER] Manutenção concluída com sucesso.")
    except Exception as e:
        logger.error(f"⚠️ [SCHEDULER] Erro durante a rotina neural: {e}")

# Configuração do Agendador
# [AURA INFO] BackgroundScheduler daemonizado para não bloquear o servidor Flask
scheduler = BackgroundScheduler(daemon=True)
# O reset ocorre à meia-noite (00:00)
scheduler.add_job(rotina_diaria_manutencao, 'cron', hour=0, minute=0)

# ======================================================
# 🚀 PONTO DE ENTRADA DO SERVIDOR (AURA OS)
# ======================================================

# [AURA FIX] Iniciamos o scheduler fora do bloco __main__ para garantir ativação
# automática em servidores WSGI como Gunicorn (Render).
if not scheduler.running:
    try:
        scheduler.start()
        logger.info("✅ Agendador de tarefas Aura OS (Hybrid Scheduler) ativado.")
    except Exception as e:
        logger.error(f"❌ Falha crítica ao iniciar Scheduler: {e}")

if __name__ == '__main__':
    # 1. Define a Porta (Dinâmica via Render PORT)
    port = int(os.environ.get("PORT", 5050))
    
    # 2. Identifica o Ambiente e Lança o Motor de Execução
    if os.environ.get("PORT"):
        # MODO PRODUÇÃO (Render/Nuvem)
        from waitress import serve
        logger.info(f"🚀 MODO PRODUÇÃO: Aura OS operando via Waitress na porta {port}")
        # Waitress isola o app garantindo estabilidade para múltiplas requisições
        serve(app, host='0.0.0.0', port=port)
    else:
        # MODO DESENVOLVIMENTO (MacBook/Local)
        logger.info(f"🛠️ MODO DEV: Aura OS operando via Flask na porta {port}")
        # Usamos a instância importada para rodar localmente
        app.run(host='0.0.0.0', port=port, debug=True)