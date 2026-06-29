"""
Testa os filtros MongoDB dos 4 jobs de push notification
sem enviar nenhuma notificação real.

Estratégia:
- Insere documentos sintéticos em 'test_push_usuarios' (coleção isolada).
- Executa cada filtro contra essa coleção.
- Verifica quem seria notificado e quem seria excluído corretamente.
- Apaga toda a coleção de teste ao final.

Execução:  source venv/bin/activate && python3 test_push_filters.py
"""

import sys
import os
from datetime import datetime, timedelta
import pytz

# Garante que o .env seja carregado
from dotenv import load_dotenv
load_dotenv()

from data_manager import mongo_db

# ──────────────────────────────────────────────────────────────
TZ = pytz.timezone("America/Sao_Paulo")
COLECAO = "test_push_usuarios"      # NUNCA toca em 'usuarios' de produção
HOJE = datetime.now(TZ).strftime("%Y-%m-%d")
ONTEM = (datetime.now(TZ) - timedelta(days=1)).strftime("%Y-%m-%d")

PASS = "✅ PASSOU"
FAIL = "❌ FALHOU"
erros = []

# ──────────────────────────────────────────────────────────────
# Usuários sintéticos
# ──────────────────────────────────────────────────────────────
USUARIOS = [
    # ── JOB 1: Missões pendentes ───────────────────────────────
    {
        "_id": "test_u1_missao_pendente",
        "nome": "Atleta com missão pendente",
        "configuracoes_sistema": {"onboarding_completo": True},
        "fcm_tokens": ["token_valido_u1"],
        "notificacoes_preferences": {
            "treino_lembretes": True, "cla_chat": True,
            "mercado_ofertas": False, "atualizacoes_sistema": True,
        },
        "gamificacao": {
            "ultima_geracao_missoes": f"{HOJE}T09:00:00",
            "missoes_ativas": [
                {"id": "m1", "concluida": False},
                {"id": "m2", "concluida": True},
            ],
        },
        "ofensiva_atual": 3,
        "ultima_missao_data": f"{ONTEM}T20:00:00",
        "cla_atual_id": "cla_abc",
    },
    {
        "_id": "test_u2_missao_toda_concluida",
        "nome": "Atleta todas missões OK",
        "configuracoes_sistema": {"onboarding_completo": True},
        "fcm_tokens": ["token_valido_u2"],
        "notificacoes_preferences": {
            "treino_lembretes": True, "cla_chat": True,
            "mercado_ofertas": False, "atualizacoes_sistema": True,
        },
        "gamificacao": {
            "ultima_geracao_missoes": f"{HOJE}T09:00:00",
            "missoes_ativas": [
                {"id": "m1", "concluida": True},   # todas concluídas
                {"id": "m2", "concluida": True},
            ],
        },
        "ofensiva_atual": 5,
        "ultima_missao_data": f"{HOJE}T10:00:00",  # completou hoje
        "cla_atual_id": None,
    },
    {
        "_id": "test_u3_missao_ontem",
        "nome": "Atleta missões de ontem",
        "configuracoes_sistema": {"onboarding_completo": True},
        "fcm_tokens": ["token_valido_u3"],
        "notificacoes_preferences": {
            "treino_lembretes": True, "cla_chat": False,
            "mercado_ofertas": False, "atualizacoes_sistema": True,
        },
        "gamificacao": {
            "ultima_geracao_missoes": f"{ONTEM}T09:00:00",  # geradas ontem
            "missoes_ativas": [{"id": "m1", "concluida": False}],
        },
        "ofensiva_atual": 0,
        "ultima_missao_data": f"{ONTEM}T20:00:00",
        "cla_atual_id": None,
    },
    {
        "_id": "test_u4_sem_token",
        "nome": "Atleta sem FCM token",
        "configuracoes_sistema": {"onboarding_completo": True},
        "fcm_tokens": [],                           # sem token → nunca notifica
        "notificacoes_preferences": {
            "treino_lembretes": True, "cla_chat": True,
            "mercado_ofertas": True, "atualizacoes_sistema": True,
        },
        "gamificacao": {
            "ultima_geracao_missoes": f"{HOJE}T09:00:00",
            "missoes_ativas": [{"id": "m1", "concluida": False}],
        },
        "ofensiva_atual": 10,
        "ultima_missao_data": f"{ONTEM}T20:00:00",
        "cla_atual_id": "cla_xyz",
    },
    # ── JOB 2: Ofensiva em risco ───────────────────────────────
    {
        "_id": "test_u5_ofensiva_risco",
        "nome": "Atleta ofensiva em risco",
        "configuracoes_sistema": {"onboarding_completo": True},
        "fcm_tokens": ["token_valido_u5"],
        "notificacoes_preferences": {
            "treino_lembretes": False, "cla_chat": False,
            "mercado_ofertas": False, "atualizacoes_sistema": True,
        },
        "gamificacao": {
            "ultima_geracao_missoes": f"{HOJE}T09:00:00",
            "missoes_ativas": [{"id": "m1", "concluida": False}],
        },
        "ofensiva_atual": 7,
        "ultima_missao_data": f"{ONTEM}T20:00:00",  # não completou hoje
        "cla_atual_id": None,
    },
    {
        "_id": "test_u6_ofensiva_zero",
        "nome": "Atleta sem ofensiva",
        "configuracoes_sistema": {"onboarding_completo": True},
        "fcm_tokens": ["token_valido_u6"],
        "notificacoes_preferences": {
            "treino_lembretes": True, "cla_chat": True,
            "mercado_ofertas": False, "atualizacoes_sistema": True,
        },
        "gamificacao": {
            "ultima_geracao_missoes": f"{HOJE}T09:00:00",
            "missoes_ativas": [{"id": "m1", "concluida": False}],
        },
        "ofensiva_atual": 0,                        # streak zero → não notifica
        "ultima_missao_data": f"{ONTEM}T20:00:00",
        "cla_atual_id": "cla_def",
    },
    # ── JOB 3: Mercado ofertas ─────────────────────────────────
    {
        "_id": "test_u7_mercado_optin",
        "nome": "Atleta opt-in mercado",
        "configuracoes_sistema": {"onboarding_completo": True},
        "fcm_tokens": ["token_valido_u7"],
        "notificacoes_preferences": {
            "treino_lembretes": False, "cla_chat": False,
            "mercado_ofertas": True, "atualizacoes_sistema": False,  # opt-in
        },
        "gamificacao": {"ultima_geracao_missoes": "", "missoes_ativas": []},
        "ofensiva_atual": 0,
        "ultima_missao_data": "",
        "cla_atual_id": None,
    },
    # ── JOB 4: Clã ────────────────────────────────────────────
    {
        "_id": "test_u8_cla_ativo",
        "nome": "Atleta com clã",
        "configuracoes_sistema": {"onboarding_completo": True},
        "fcm_tokens": ["token_valido_u8"],
        "notificacoes_preferences": {
            "treino_lembretes": True, "cla_chat": True,
            "mercado_ofertas": False, "atualizacoes_sistema": True,
        },
        "gamificacao": {
            "ultima_geracao_missoes": f"{HOJE}T09:00:00",
            "missoes_ativas": [{"id": "m1", "concluida": True}],
        },
        "ofensiva_atual": 2,
        "ultima_missao_data": f"{HOJE}T11:00:00",   # completou hoje
        "cla_atual_id": "cla_ghi",
    },
    {
        "_id": "test_u9_cla_null",
        "nome": "Atleta sem clã",
        "configuracoes_sistema": {"onboarding_completo": True},
        "fcm_tokens": ["token_valido_u9"],
        "notificacoes_preferences": {
            "treino_lembretes": True, "cla_chat": True,    # preferência ativa
            "mercado_ofertas": False, "atualizacoes_sistema": True,
        },
        "gamificacao": {"ultima_geracao_missoes": "", "missoes_ativas": []},
        "ofensiva_atual": 0,
        "ultima_missao_data": "",
        "cla_atual_id": None,                       # sem clã → não notifica
    },
    # ── Controle: onboarding incompleto ───────────────────────
    {
        "_id": "test_u10_sem_onboarding",
        "nome": "Atleta sem onboarding",
        "configuracoes_sistema": {"onboarding_completo": False},
        "fcm_tokens": ["token_valido_u10"],
        "notificacoes_preferences": {
            "treino_lembretes": True, "cla_chat": True,
            "mercado_ofertas": True, "atualizacoes_sistema": True,
        },
        "gamificacao": {
            "ultima_geracao_missoes": f"{HOJE}T09:00:00",
            "missoes_ativas": [{"id": "m1", "concluida": False}],
        },
        "ofensiva_atual": 5,
        "ultima_missao_data": f"{ONTEM}T20:00:00",
        "cla_atual_id": "cla_xyz",
    },
]


def setup():
    col = mongo_db[COLECAO]
    col.drop()
    for u in USUARIOS:
        col.replace_one({"_id": u["_id"]}, u, upsert=True)
    print(f"\n📦 {len(USUARIOS)} usuários de teste inseridos em '{COLECAO}'.\n")
    return col


def teardown():
    mongo_db[COLECAO].drop()
    print(f"\n🧹 Coleção '{COLECAO}' removida.\n")


def _filtro_base() -> dict:
    return {
        "configuracoes_sistema.onboarding_completo": True,
        "fcm_tokens": {"$exists": True, "$not": {"$size": 0}},
    }


def _ids(cursor) -> set:
    return {str(doc["_id"]) for doc in cursor}


def assert_ids(label: str, obtidos: set, esperados: set, excluidos: set):
    ok = True
    for e in esperados:
        if e not in obtidos:
            print(f"  {FAIL} [{label}] esperado {e} mas não retornado")
            erros.append(label)
            ok = False
    for x in excluidos:
        if x in obtidos:
            print(f"  {FAIL} [{label}] {x} NÃO deveria ser retornado")
            erros.append(label)
            ok = False
    if ok:
        print(f"  {PASS} [{label}] retornados={sorted(obtidos)}")


# ──────────────────────────────────────────────────────────────
# Testes
# ──────────────────────────────────────────────────────────────
def teste_missoes(col):
    print("── JOB 1: Missões diárias pendentes (17h) ──────────────")
    filtro = {
        **_filtro_base(),
        "notificacoes_preferences.treino_lembretes": True,
        "gamificacao.ultima_geracao_missoes": {"$regex": f"^{HOJE}"},
        "gamificacao.missoes_ativas": {"$elemMatch": {"concluida": False}},
    }
    ids = _ids(col.find(filtro, {"_id": 1}))
    assert_ids(
        "Missões pendentes",
        obtidos=ids,
        esperados={"test_u1_missao_pendente"},       # gerou hoje + tem pendente
        excluidos={
            "test_u2_missao_toda_concluida",          # todas concluídas
            "test_u3_missao_ontem",                   # geradas ontem
            "test_u4_sem_token",                      # sem FCM token
            "test_u10_sem_onboarding",                # onboarding falso
        },
    )


def teste_ofensiva(col):
    print("── JOB 2: Ofensiva em risco (21h30) ───────────────────")
    filtro = {
        **_filtro_base(),
        "notificacoes_preferences.atualizacoes_sistema": True,
        "ofensiva_atual": {"$gte": 1},
        "ultima_missao_data": {
            "$exists": True,
            "$ne": "",
            "$not": {"$regex": f"^{HOJE}"},
        },
    }
    ids = _ids(col.find(filtro, {"_id": 1}))
    assert_ids(
        "Ofensiva em risco",
        obtidos=ids,
        esperados={
            "test_u1_missao_pendente",   # streak 3, não completou hoje
            "test_u5_ofensiva_risco",    # streak 7, não completou hoje
        },
        excluidos={
            "test_u2_missao_toda_concluida",  # completou hoje
            "test_u6_ofensiva_zero",          # streak = 0
            "test_u4_sem_token",              # sem token
            "test_u8_cla_ativo",              # completou hoje
            "test_u10_sem_onboarding",        # onboarding falso
        },
    )


def teste_mercado(col):
    print("── JOB 3: Ofertas do Mercado (12h) ─────────────────────")
    filtro = {
        **_filtro_base(),
        "notificacoes_preferences.mercado_ofertas": True,
    }
    ids = _ids(col.find(filtro, {"_id": 1}))
    assert_ids(
        "Mercado opt-in",
        obtidos=ids,
        esperados={"test_u7_mercado_optin"},
        excluidos={
            "test_u1_missao_pendente",    # mercado_ofertas=False
            "test_u4_sem_token",          # sem token (e mercado=True mas sem token)
            "test_u10_sem_onboarding",    # onboarding falso
        },
    )


def teste_cla(col):
    print("── JOB 4: Atualizações do Clã (19h) ───────────────────")
    filtro = {
        **_filtro_base(),
        "notificacoes_preferences.cla_chat": True,
        "cla_atual_id": {"$nin": [None, ""]},
    }
    ids = _ids(col.find(filtro, {"_id": 1}))
    assert_ids(
        "Clã ativo",
        obtidos=ids,
        esperados={
            "test_u1_missao_pendente",    # cla_chat=True, tem clã
            "test_u6_ofensiva_zero",      # cla_chat=True, tem clã
            "test_u8_cla_ativo",          # cla_chat=True, tem clã
        },
        excluidos={
            "test_u9_cla_null",           # cla_atual_id=None
            "test_u4_sem_token",          # sem token
            "test_u10_sem_onboarding",    # onboarding falso
            "test_u7_mercado_optin",      # cla_chat=False
        },
    )


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if mongo_db is None:
        print("❌ Impossível conectar ao MongoDB. Verifique MONGODB_URI no .env")
        sys.exit(1)

    print(f"📅 Data de referência (BRT): {HOJE}  |  Ontem: {ONTEM}\n")
    col = setup()

    teste_missoes(col)
    teste_ofensiva(col)
    teste_mercado(col)
    teste_cla(col)

    teardown()

    if erros:
        print(f"\n❌ {len(erros)} falha(s): {erros}")
        sys.exit(1)
    else:
        print("\n✅ Todos os filtros validados com sucesso.")
        sys.exit(0)
