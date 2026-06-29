import os
import logging
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler

from data_manager import mongo_db
from data_global import carregar_memoria_global, registrar_interacao_global
from logic_equilibrio import resetar_homeostase_diaria
from performance_bp import limpar_mensagens_chat

logger = logging.getLogger("AURA_SCHEDULER")

_scheduler = None
TZ_BRASILIA = pytz.timezone("America/Sao_Paulo")


# ──────────────────────────────────────────────────────────────
# Lock distribuído MongoDB
# Garante que apenas 1 dos 4 workers Gunicorn execute cada job.
# Usa insert_one com _id único: apenas o primeiro insere com sucesso;
# os demais recebem DuplicateKeyError e pulam o job.
# ──────────────────────────────────────────────────────────────
def _acquire_lock(nome_job: str, ttl_segundos: int = 3600) -> bool:
    if mongo_db is None:
        return False
    agora = datetime.utcnow()
    expira = agora + timedelta(seconds=ttl_segundos)
    try:
        # Remove lock expirado (se existir) para permitir nova execução
        mongo_db["scheduler_locks"].delete_one(
            {"_id": nome_job, "expire_at": {"$lt": agora}}
        )
        # Tenta inserir: falha com DuplicateKeyError se outro worker chegou primeiro
        mongo_db["scheduler_locks"].insert_one({
            "_id":         nome_job,
            "expire_at":   expira,
            "pid":         os.getpid(),
            "iniciado_em": agora.isoformat()
        })
        return True
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────
# JOB: Manutenção diária (meia-noite)
# ──────────────────────────────────────────────────────────────
def rotina_diaria_manutencao():
    if not _acquire_lock("manutencao_diaria", ttl_segundos=3600):
        logger.info("[SCHEDULER] manutencao_diaria: outro worker já rodando, pulando.")
        return

    logger.info(f"🕛 [SCHEDULER] Manutenção diária iniciada (PID {os.getpid()}): {datetime.now()}")
    if mongo_db is None:
        logger.error("❌ [SCHEDULER] MongoDB inacessível, abortando.")
        return

    try:
        estado = carregar_memoria_global()
        logger.info(f"🌍 Versão ativa: {estado.get('versao_ia_ativa', '3.3.0')}")

        usuarios = mongo_db["usuarios"].find(
            {"configuracoes_sistema.onboarding_completo": True}
        )
        count = 0
        for user in usuarios:
            resetar_homeostase_diaria(str(user["_id"]))
            count += 1
        logger.info(f"✅ Homeostase recalibrada: {count} atletas.")

        agora_iso = datetime.now().isoformat()

        r1 = mongo_db["grants_saude"].update_many(
            {"status": "ativo", "data_expiracao": {"$lte": agora_iso}},
            {"$set": {"status": "expirado", "atualizado_em": agora_iso}}
        )
        logger.info(f"🔒 Grants expirados: {r1.modified_count}")

        r2 = mongo_db["profissionais"].update_many(
            {"plano_ativo": True, "plano_expira": {"$lte": agora_iso}},
            {"$set": {"plano_ativo": False, "updated_at": agora_iso}}
        )
        logger.info(f"🔒 Assinaturas expiradas: {r2.modified_count}")

        g, p, c = limpar_mensagens_chat()
        logger.info(f"💬 Chat limpo: grupo={g} priv={p} clã={c}")

        registrar_interacao_global(sentimento="sistema", tipo_acao="manutencao_diaria")
        logger.info("✅ [SCHEDULER] Manutenção concluída.")
    except Exception as e:
        logger.error(f"⚠️ [SCHEDULER] Erro na manutenção: {e}")


# ──────────────────────────────────────────────────────────────
# Helper: query base obrigatória para todos os jobs de push
# ──────────────────────────────────────────────────────────────
def _filtro_base_push() -> dict:
    """Condições comuns a todos os jobs: onboarding completo + token registrado."""
    return {
        "configuracoes_sistema.onboarding_completo": True,
        "fcm_tokens": {"$exists": True, "$not": {"$size": 0}},
    }


# ──────────────────────────────────────────────────────────────
# JOB: Missões diárias pendentes — 17:00 BRT
# Notifica quem gerou missões hoje E ainda tem ao menos 1 pendente.
# ──────────────────────────────────────────────────────────────
def push_missoes_pendentes():
    if not _acquire_lock("push_missoes", ttl_segundos=3600):
        logger.info("[SCHEDULER] push_missoes: outro worker já rodando, pulando.")
        return
    if mongo_db is None:
        return

    hoje_str = datetime.now(TZ_BRASILIA).strftime("%Y-%m-%d")
    filtro = {
        **_filtro_base_push(),
        "notificacoes_preferences.treino_lembretes": True,
        # Missões geradas hoje
        "gamificacao.ultima_geracao_missoes": {"$regex": f"^{hoje_str}"},
        # Ao menos uma missão não concluída
        "gamificacao.missoes_ativas": {"$elemMatch": {"concluida": False}},
    }

    try:
        from logic_push import enviar_push_usuario
        usuarios = mongo_db["usuarios"].find(filtro, {"_id": 1, "nome": 1})
        count = 0
        for u in usuarios:
            enviar_push_usuario(
                user_id=str(u["_id"]),
                titulo="Suas missões aguardam, Atleta! 🏅",
                corpo="Você ainda tem missões para completar hoje. Não deixe o dia acabar!",
                dados={"tela": "missoes"},
            )
            count += 1
        logger.info(f"[PUSH] push_missoes: {count} usuários notificados.")
    except Exception as e:
        logger.error(f"[PUSH] Erro push_missoes: {e}")


# ──────────────────────────────────────────────────────────────
# JOB: Ofensiva em risco — 21:30 BRT
# Notifica quem tem streak ≥ 1 E não concluiu missão hoje.
# ──────────────────────────────────────────────────────────────
def push_ofensiva_risco():
    if not _acquire_lock("push_ofensiva", ttl_segundos=3600):
        logger.info("[SCHEDULER] push_ofensiva: outro worker já rodando, pulando.")
        return
    if mongo_db is None:
        return

    hoje_str = datetime.now(TZ_BRASILIA).strftime("%Y-%m-%d")
    filtro = {
        **_filtro_base_push(),
        "notificacoes_preferences.atualizacoes_sistema": True,
        "ofensiva_atual": {"$gte": 1},
        # ultima_missao_data existe, não está vazia, e NÃO começa com hoje
        "ultima_missao_data": {
            "$exists": True,
            "$ne": "",
            "$not": {"$regex": f"^{hoje_str}"},
        },
    }

    try:
        from logic_push import enviar_push_usuario
        usuarios = mongo_db["usuarios"].find(filtro, {"_id": 1, "ofensiva_atual": 1})
        count = 0
        for u in usuarios:
            streak = u.get("ofensiva_atual", 1)
            enviar_push_usuario(
                user_id=str(u["_id"]),
                titulo=f"🔥 Sua ofensiva de {streak} dia{'s' if streak > 1 else ''} está em risco!",
                corpo="Complete uma missão antes da meia-noite para manter sua sequência.",
                dados={"tela": "missoes"},
            )
            count += 1
        logger.info(f"[PUSH] push_ofensiva: {count} usuários notificados.")
    except Exception as e:
        logger.error(f"[PUSH] Erro push_ofensiva: {e}")


# ──────────────────────────────────────────────────────────────
# JOB: Ofertas do Mercado — 12:00 BRT
# Opt-in: só para quem ativou mercado_ofertas.
# ──────────────────────────────────────────────────────────────
def push_mercado_ofertas():
    if not _acquire_lock("push_mercado", ttl_segundos=3600):
        logger.info("[SCHEDULER] push_mercado: outro worker já rodando, pulando.")
        return
    if mongo_db is None:
        return

    filtro = {
        **_filtro_base_push(),
        "notificacoes_preferences.mercado_ofertas": True,
    }

    try:
        from logic_push import enviar_push_usuario
        usuarios = mongo_db["usuarios"].find(filtro, {"_id": 1})
        count = 0
        for u in usuarios:
            enviar_push_usuario(
                user_id=str(u["_id"]),
                titulo="🛒 Novidades no Mercado AURA",
                corpo="Confira os suplementos e produtos disponíveis para você hoje.",
                dados={"tela": "mercado"},
            )
            count += 1
        logger.info(f"[PUSH] push_mercado: {count} usuários notificados.")
    except Exception as e:
        logger.error(f"[PUSH] Erro push_mercado: {e}")


# ──────────────────────────────────────────────────────────────
# JOB: Atualizações do Clã — 19:00 BRT
# Só para usuários com clã ativo (cla_atual_id não nulo/vazio).
# ──────────────────────────────────────────────────────────────
def push_cla_atualizacoes():
    if not _acquire_lock("push_cla", ttl_segundos=3600):
        logger.info("[SCHEDULER] push_cla: outro worker já rodando, pulando.")
        return
    if mongo_db is None:
        return

    filtro = {
        **_filtro_base_push(),
        "notificacoes_preferences.cla_chat": True,
        # cla_atual_id deve existir e não ser nulo nem string vazia
        "cla_atual_id": {"$nin": [None, ""]},
    }

    try:
        from logic_push import enviar_push_usuario
        usuarios = mongo_db["usuarios"].find(filtro, {"_id": 1})
        count = 0
        for u in usuarios:
            enviar_push_usuario(
                user_id=str(u["_id"]),
                titulo="⚔️ Seu Clã está ativo!",
                corpo="Veja os novos desafios, conquistas e mensagens do seu clã.",
                dados={"tela": "cla"},
            )
            count += 1
        logger.info(f"[PUSH] push_cla: {count} usuários notificados.")
    except Exception as e:
        logger.error(f"[PUSH] Erro push_cla: {e}")


# ──────────────────────────────────────────────────────────────
# Inicialização (chamada de app.py no nível de módulo)
# ──────────────────────────────────────────────────────────────
def iniciar_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(daemon=True, timezone=TZ_BRASILIA)

    jobs = [
        # id                    função                   hora  min
        ("manutencao_diaria",   rotina_diaria_manutencao, 0,    0),
        ("push_missoes",        push_missoes_pendentes,   17,   0),
        ("push_cla",            push_cla_atualizacoes,    19,   0),
        ("push_ofensiva",       push_ofensiva_risco,      21,   30),
        ("push_mercado",        push_mercado_ofertas,     12,   0),
    ]
    for job_id, func, hora, minuto in jobs:
        _scheduler.add_job(
            func,
            "cron",
            hour=hora,
            minute=minuto,
            id=job_id,
            replace_existing=True,
            misfire_grace_time=1800,
        )

    try:
        _scheduler.start()
        logger.info(f"✅ Scheduler iniciado (PID {os.getpid()}) — 5 jobs agendados.")
    except Exception as e:
        logger.error(f"❌ Falha ao iniciar scheduler: {e}")
