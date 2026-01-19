import os
import logging
import json
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

# Importa a aplicação Flask configurada
from app import app 

# Importações de Dados (Serão refatorados a seguir, mas já preparamos o terreno)
# Nota: O data_manager atual ainda não tem a variável mongo_db exportada corretamente,
# mas vamos corrigir isso no próximo passo (Arquivo 24).
try:
    from data_manager import mongo_db
except ImportError:
    mongo_db = None

# Configuração de Logs (Formato Nuvem - StreamHandler)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler()] # Garante saída no console do Render
)
logger = logging.getLogger("AURA_MAIN")

# ==============================================================
# 🛠️ ROTINAS AUTOMÁTICAS (SCHEDULER)
# ==============================================================

def job_rotina_diaria_global():
    """
    Executada todo dia à 00:00 (Meia-noite).
    Responsável por resetar missões diárias de todos os usuários
    e verificar vencimento de planos.
    """
    logger.info("🕛 [SCHEDULER] Iniciando rotina da meia-noite...")
    
    if mongo_db is not None:
        try:
            # Lógica futura:
            # 1. Buscar todos usuários ativos
            # 2. Gerar novas missões para eles
            # 3. Verificar status de assinatura (Vencido -> Free)
            logger.info("✅ [SCHEDULER] Rotina diária finalizada (Placeholder).")
        except Exception as e:
            logger.error(f"❌ [SCHEDULER] Erro na rotina diária: {e}")
    else:
        logger.warning("⚠️ [SCHEDULER] Banco desconectado. Pulando rotina.")

def iniciar_scheduler():
    """Configura e inicia o agendador de tarefas em segundo plano."""
    try:
        scheduler = BackgroundScheduler()
        # Adiciona o job para rodar todos os dias à meia-noite
        scheduler.add_job(job_rotina_diaria_global, 'cron', hour=0, minute=0)
        scheduler.start()
        logger.info("⏰ [SISTEMA] Agendador (Scheduler) iniciado com sucesso.")
    except Exception as e:
        logger.error(f"❌ [SISTEMA] Falha ao iniciar Scheduler: {e}")

# ==============================================================
# 🌱 SEED DATABASE (POPULAR DADOS INICIAIS)
# ==============================================================

def verificar_seed_missoes():
    """
    Verifica se a coleção de missões está vazia. 
    Se estiver, carrega o JSON padrão para dentro do MongoDB.
    """
    if mongo_db is None:
        return

    try:
        colecao_missoes = mongo_db["missoes"]
        contagem = colecao_missoes.count_documents({})
        
        if contagem == 0:
            logger.info("🌱 [SEED] Banco de missões vazio. Populando inicial...")
            
            # Tenta ler o arquivo JSON local apenas para a primeira carga
            if os.path.exists("banco_de_missoes.json"):
                with open("banco_de_missoes.json", "r", encoding="utf-8") as f:
                    dados_missoes = json.load(f)
                    
                if dados_missoes:
                    colecao_missoes.insert_many(dados_missoes)
                    logger.info(f"✅ [SEED] {len(dados_missoes)} missões inseridas no MongoDB.")
            else:
                logger.warning("⚠️ Arquivo banco_de_missoes.json não encontrado para seed.")
        else:
            logger.info(f"✅ [BOOT] Banco de missões já populado ({contagem} itens).")
            
    except Exception as e:
        logger.error(f"❌ [SEED] Erro ao popular missões: {e}")

# ==============================================================
# 🚀 ENTRY POINT (PONTO DE PARTIDA)
# ==============================================================

# Executa verificações apenas se este arquivo for o principal
if __name__ == '__main__':
    # 1. Inicializa Scheduler
    iniciar_scheduler()
    
    # 2. Verifica Seed (Popula banco se necessário)
    # Nota: Isso vai falhar silenciosamente agora se o data_manager não estiver pronto,
    # mas funcionará assim que corrigirmos o próximo arquivo.
    verificar_seed_missoes()

    # 3. Configuração de Rede
    port = int(os.environ.get("PORT", 5000))
    
    logger.info("=========================================")
    logger.info(f"   🔱 AURA PERFORMANCE API ONLINE   ")
    logger.info(f"   👉 Ambiente: {os.environ.get('FLASK_ENV', 'development')}")
    logger.info(f"   👉 Porta: {port}")
    logger.info("=========================================")
    
    # Inicia o Servidor
    app.run(host='0.0.0.0', port=port, use_reloader=False) 
    # use_reloader=False evita que o Scheduler rode duplicado em dev