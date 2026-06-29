import os
import json
import time
import logging
from bson.objectid import ObjectId
import requests
from jose import jwt as jose_jwt

logger = logging.getLogger("AURA_PUSH")

# Cache do service account (carregado uma vez da env var)
_SA_JSON = None
# Cache do access token OAuth2 (válido 1h)
_token_cache: dict = {"token": None, "exp": 0}


def _service_account() -> dict:
    global _SA_JSON
    if _SA_JSON is None:
        raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
        if not raw:
            raise ValueError("FIREBASE_SERVICE_ACCOUNT_JSON não configurada nas variáveis de ambiente.")
        _SA_JSON = json.loads(raw)
    return _SA_JSON


def _get_access_token() -> str:
    """Obtém ou reutiliza o access token OAuth2 do service account Firebase."""
    now = int(time.time())
    if _token_cache["token"] and _token_cache["exp"] > now + 120:
        return _token_cache["token"]

    sa = _service_account()
    payload = {
        "iss":   sa["client_email"],
        "scope": "https://www.googleapis.com/auth/firebase.messaging",
        "aud":   "https://oauth2.googleapis.com/token",
        "iat":   now,
        "exp":   now + 3600,
    }
    signed = jose_jwt.encode(payload, sa["private_key"], algorithm="RS256")
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion":  signed,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["exp"]   = now + data.get("expires_in", 3600)
    return _token_cache["token"]


def _enviar_token(token: str, titulo: str, corpo: str, dados: dict = None):
    """
    Envia push para um único FCM token via API v1.
    Retorna: True (ok) | False (erro geral) | "UNREGISTERED" (token inválido)
    """
    try:
        sa         = _service_account()
        project_id = sa.get("project_id", "")
        if not project_id or not token:
            return False

        access_token = _get_access_token()
        mensagem = {
            "message": {
                "token": token,
                "notification": {"title": titulo, "body": corpo},
                "apns": {
                    "payload": {"aps": {"sound": "default", "badge": 1}}
                },
                "android": {
                    "priority": "high"
                }
            }
        }
        if dados:
            mensagem["message"]["data"] = {k: str(v) for k, v in dados.items()}

        resp = requests.post(
            f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type":  "application/json",
            },
            json=mensagem,
            timeout=15,
        )

        if resp.status_code == 200:
            return True

        # Token inválido/desregistrado
        if resp.status_code in (400, 404):
            body = resp.text
            if "UNREGISTERED" in body or "INVALID_ARGUMENT" in body:
                return "UNREGISTERED"

        logger.warning(f"[PUSH] FCM {resp.status_code}: {resp.text[:300]}")
        return False

    except Exception as e:
        logger.error(f"[PUSH] Erro ao enviar token ...{token[-10:]}: {e}")
        return False


def enviar_push_usuario(user_id: str, titulo: str, corpo: str, dados: dict = None):
    """
    Envia push para todos os tokens registrados de um usuário.
    Remove automaticamente tokens com status UNREGISTERED do banco.
    """
    from data_manager import mongo_db
    if mongo_db is None:
        return

    try:
        usuario = mongo_db["usuarios"].find_one(
            {"_id": ObjectId(user_id)},
            {"fcm_tokens": 1}
        )
        if not usuario:
            return

        tokens = usuario.get("fcm_tokens") or []
        if not tokens:
            return

        invalidos = []
        for token in tokens:
            resultado = _enviar_token(token, titulo, corpo, dados)
            if resultado == "UNREGISTERED":
                invalidos.append(token)

        if invalidos:
            mongo_db["usuarios"].update_one(
                {"_id": ObjectId(user_id)},
                {"$pull": {"fcm_tokens": {"$in": invalidos}}}
            )
            logger.info(f"[PUSH] Removidos {len(invalidos)} tokens inválidos do usuário {user_id}")

    except Exception as e:
        logger.error(f"[PUSH] Erro push usuário {user_id}: {e}")


def enviar_push_em_lote(user_ids: list, titulo: str, corpo: str, dados: dict = None):
    """Envia o mesmo push para uma lista de user_ids."""
    for uid in user_ids:
        enviar_push_usuario(uid, titulo, corpo, dados)
