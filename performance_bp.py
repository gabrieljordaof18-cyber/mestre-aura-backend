"""
performance_bp.py — Marketplace de Profissionais de Performance
Prefixo: /api/performance

Fluxo financeiro:
  - Usuário paga pelo desafio (PIX/Cartão via Asaas)
  - AURA fica com 20%, profissional recebe 80% (repasse manual por ora)
  - Verificação de credenciais: R$99,90 (pagamento único)
  - Plano mensal profissional: R$49,90/mês após 3 meses grátis
"""

import os
import logging
import requests as _requests
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from bson.objectid import ObjectId

from data_manager import mongo_db
from data_user import carregar_memoria
from schema import (
    obter_schema_padrao_profissional,
    obter_schema_padrao_desafio,
    obter_schema_padrao_inscricao,
    obter_schema_padrao_mensagem_desafio,
)
from logic_asaas import criar_cobranca, criar_ou_buscar_cliente

logger = logging.getLogger("AURA_PERFORMANCE")

performance_bp = Blueprint("performance", __name__)

# ──────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────

def _get_user_id(request_obj):
    """Extrai o user_id do token JWT já validado pelo middleware externo."""
    return request_obj.environ.get("current_user_id", "")


def _token_required(f):
    """Decorador leve que reutiliza o middleware JWT de rotas_api.py via environ."""
    from functools import wraps
    from flask import request as req
    import jwt as pyjwt

    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth = req.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
        if not token:
            return jsonify({"erro": "Token ausente"}), 401
        try:
            secret = os.getenv("JWT_SECRET", "aura_secret_dev")
            payload = pyjwt.decode(token, secret, algorithms=["HS256"])
            user_id = payload.get("user_id") or payload.get("id") or payload.get("sub")
            if not user_id:
                return jsonify({"erro": "Token inválido"}), 401
        except Exception:
            return jsonify({"erro": "Token inválido ou expirado"}), 401
        return f(user_id, *args, **kwargs)
    return decorated


def _obter_profissional(user_id: str):
    """Retorna o doc de profissional ou None."""
    if mongo_db is None:
        return None
    return mongo_db["profissionais"].find_one({"user_id": user_id})


def _assinatura_prof_ativa(prof_doc: dict) -> bool:
    """Retorna True se o profissional tem assinatura (trial ou IAP) válida e não expirada."""
    if not prof_doc:
        return False
    if not prof_doc.get("plano_ativo"):
        return False
    expira = prof_doc.get("plano_expira", "")
    if expira and datetime.fromisoformat(expira) < datetime.now():
        return False
    return True


_ERRO_ASSINATURA = {"erro": "assinatura_expirada",
                    "detalhe": "Sua assinatura profissional expirou. Renove para acessar este recurso."}
_ERRO_CHAT_BLOQ  = {"erro": "profissional_indisponivel",
                    "detalhe": "Este profissional está temporariamente indisponível para novas interações."}


def _serializar(doc: dict) -> dict:
    """Converte _id ObjectId para string 'id'."""
    if doc is None:
        return {}
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


def _calc_split(valor: float, desconto_pct: float = 0) -> tuple:
    """Retorna (valor_aura, valor_profissional)."""
    valor_aura = round(valor * 0.20, 2)
    valor_prof = round(valor * 0.80, 2)
    return valor_aura, valor_prof


# ══════════════════════════════════════════════════════════════
# ROTAS DE PROFISSIONAL
# ══════════════════════════════════════════════════════════════

@performance_bp.route("/solicitar", methods=["POST"])
@_token_required
def solicitar_profissional(current_user_id):
    """Usuário comum solicita se tornar profissional. Libera 3 meses grátis."""
    try:
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        dados = request.get_json(force=True)
        tipo = str(dados.get("tipo_profissional", "personal")).lower()
        bio  = str(dados.get("bio", "")).strip()[:300]
        cref = str(dados.get("cref_crn_crm", "")).strip()

        tipos_validos = {"personal", "nutricionista", "medico", "fisioterapeuta",
                         "coach", "nutrologo", "endocrino"}
        if tipo not in tipos_validos:
            return jsonify({"erro": "Tipo de profissional inválido"}), 400

        existente = mongo_db["profissionais"].find_one({"user_id": current_user_id})
        if existente:
            return jsonify({"erro": "Você já possui um perfil profissional"}), 409

        doc = obter_schema_padrao_profissional(current_user_id)
        doc.update({
            "tipo_profissional": tipo,
            "bio": bio,
            "especialidades": list(dados.get("especialidades", [])),
            "cref_crn_crm": cref,
            "foto_perfil_url": str(dados.get("foto_perfil_url", "")).strip(),
            "instagram": str(dados.get("instagram", "")).strip().replace("@", ""),
            "nome_completo": str(dados.get("nome_completo", "")).strip(),
        })

        mongo_db["profissionais"].insert_one(doc)
        # Marca o tipo_perfil do usuário como profissional_pendente
        mongo_db["usuarios"].update_one(
            {"_id": ObjectId(current_user_id)},
            {"$set": {"tipo_perfil": "profissional_pendente", "updated_at": datetime.now().isoformat()}}
        )

        logger.info(f"[PERF] Novo profissional cadastrado: {current_user_id} ({tipo})")
        return jsonify({
            "sucesso": True,
            "mensagem": "Solicitação enviada! Seu perfil profissional foi criado com 3 meses gratuitos.",
            "plano_expira": doc["plano_expira"],
        }), 201

    except Exception as e:
        logger.error(f"[PERF] Erro ao solicitar profissional: {e}")
        return jsonify({"erro": str(e)}), 500


@performance_bp.route("/meu_perfil", methods=["GET"])
@_token_required
def meu_perfil_profissional(current_user_id):
    """Retorna perfil do profissional logado."""
    try:
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        prof = _obter_profissional(current_user_id)
        if not prof:
            return jsonify({"erro": "Perfil profissional não encontrado"}), 404

        return jsonify(_serializar(prof)), 200

    except Exception as e:
        logger.error(f"[PERF] Erro meu_perfil: {e}")
        return jsonify({"erro": str(e)}), 500


@performance_bp.route("/meu_perfil", methods=["PATCH"])
@_token_required
def atualizar_meu_perfil(current_user_id):
    """Atualiza bio, especialidades, foto do profissional."""
    try:
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        dados = request.get_json(force=True)
        campos_permitidos = {"bio", "especialidades", "foto_perfil_url", "tipo_profissional"}
        update = {k: v for k, v in dados.items() if k in campos_permitidos}
        if "bio" in update:
            update["bio"] = str(update["bio"])[:300]
        update["updated_at"] = datetime.now().isoformat()

        resultado = mongo_db["profissionais"].update_one(
            {"user_id": current_user_id},
            {"$set": update}
        )
        if resultado.matched_count == 0:
            return jsonify({"erro": "Perfil não encontrado"}), 404

        return jsonify({"sucesso": True}), 200

    except Exception as e:
        logger.error(f"[PERF] Erro atualizar perfil: {e}")
        return jsonify({"erro": str(e)}), 500


@performance_bp.route("/solicitar_verificacao", methods=["POST"])
@_token_required
def solicitar_verificacao(current_user_id):
    """
    Profissional solicita verificação de credenciais.
    Cria cobrança PIX de R$99,90 via Asaas.
    """
    try:
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        profissional = mongo_db["profissionais"].find_one({"user_id": current_user_id})
        if not profissional:
            return jsonify({"erro": "Perfil profissional não encontrado"}), 404
        if profissional.get("verificacao_paga"):
            return jsonify({"erro": "Verificação já solicitada"}), 409

        usuario = mongo_db["usuarios"].find_one({"_id": ObjectId(current_user_id)})
        nome = usuario.get("nome", "Profissional AURA") if usuario else "Profissional AURA"
        email = usuario.get("email", "") if usuario else ""

        import requests as req
        asaas_key = os.getenv("ASAAS_ACCESS_TOKEN")
        headers = {"access_token": asaas_key, "Content-Type": "application/json"}

        customer_resp = req.post("https://api.asaas.com/v3/customers", headers=headers, json={
            "name": nome, "email": email
        }, timeout=10)
        customer_id = customer_resp.json().get("id")

        cobranca = req.post("https://api.asaas.com/v3/payments", headers=headers, json={
            "customer": customer_id,
            "billingType": "PIX",
            "value": 99.90,
            "dueDate": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d"),
            "description": "Verificação de Credenciais AURA Performance",
            "externalReference": f"verificacao_{current_user_id}",
        }, timeout=10)
        dados_cobranca = cobranca.json()

        mongo_db["profissionais"].update_one(
            {"user_id": current_user_id},
            {"$set": {"verificacao_paga": True, "verificacao_payment_id": dados_cobranca.get("id")}}
        )

        return jsonify({
            "sucesso": True,
            "tipo": "pix",
            "payment_id": dados_cobranca.get("id"),
            "pix_copia_cola": dados_cobranca.get("pixTransaction", {}).get("payload"),
            "valor": 99.90
        }), 200

    except Exception as e:
        logger.error(f"[PERF] Erro solicitar_verificacao: {e}")
        return jsonify({"erro": str(e)}), 500


@performance_bp.route("/enviar_documentos_verificacao", methods=["POST"])
@_token_required
def enviar_documentos_verificacao(current_user_id):
    """Profissional envia documentos para análise de verificação."""
    try:
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        dados = request.get_json(force=True)
        nome_completo = str(dados.get("nome_completo", "")).strip()
        documento = str(dados.get("documento", "")).strip()
        codigo_profissional = str(dados.get("codigo_profissional", "")).strip()

        if not nome_completo or not documento or not codigo_profissional:
            return jsonify({"erro": "Todos os campos são obrigatórios"}), 400

        mongo_db["profissionais"].update_one(
            {"user_id": current_user_id},
            {"$set": {
                "verificacao_nome_completo": nome_completo,
                "verificacao_documento": documento,
                "verificacao_codigo_profissional": codigo_profissional,
                "status_verificacao": "aguardando_analise",
                "updated_at": datetime.now().isoformat()
            }}
        )

        mongo_db["notificacoes_admin"].insert_one({
            "tipo": "verificacao_profissional",
            "user_id": current_user_id,
            "dados": {"nome": nome_completo, "documento": documento, "codigo": codigo_profissional},
            "lida": False,
            "created_at": datetime.now().isoformat()
        })

        return jsonify({"sucesso": True, "mensagem": "Documentos enviados! Analisaremos em até 48h."}), 200
    except Exception as e:
        logger.error(f"[PERF] Erro enviar_documentos_verificacao: {e}")
        return jsonify({"erro": str(e)}), 500


# ══════════════════════════════════════════════════════════════
# ROTAS DE DESAFIOS — PROFISSIONAL
# ══════════════════════════════════════════════════════════════

@performance_bp.route("/desafios", methods=["POST"])
@_token_required
def criar_desafio(current_user_id):
    """Profissional cria um novo desafio."""
    try:
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        prof = _obter_profissional(current_user_id)
        if not prof:
            return jsonify({"erro": "Perfil profissional não encontrado. Solicite cadastro primeiro."}), 403

        if not _assinatura_prof_ativa(prof):
            return jsonify(_ERRO_ASSINATURA), 403

        dados = request.get_json(force=True)
        preco = float(dados.get("preco", 0))
        if preco < 19.90:
            return jsonify({"erro": "Preço mínimo é R$19,90"}), 400

        duracao = int(dados.get("duracao_dias", 30))
        if duracao not in (14, 21, 30, 60, 90, 180, 365):
            return jsonify({"erro": "Duração inválida. Use: 14, 21, 30, 60, 90, 180 ou 365 dias."}), 400

        doc = obter_schema_padrao_desafio(current_user_id)
        campos_aceitos = {
            "titulo", "descricao", "tipo", "duracao_dias", "preco",
            "vagas_total", "data_inicio", "imagem_capa_url", "o_que_inclui", "protocolo",
        }
        for k in campos_aceitos:
            if k in dados:
                doc[k] = dados[k]
        doc["preco"]       = preco
        doc["duracao_dias"] = duracao
        doc["status"]      = "ativo" if dados.get("publicar") else "rascunho"
        doc["updated_at"]  = datetime.now().isoformat()

        resultado = mongo_db["desafios"].insert_one(doc)
        desafio_id = str(resultado.inserted_id)

        logger.info(f"[PERF] Desafio '{doc['titulo']}' criado por {current_user_id}")
        return jsonify({"sucesso": True, "desafio_id": desafio_id}), 201

    except Exception as e:
        logger.error(f"[PERF] Erro criar_desafio: {e}")
        return jsonify({"erro": str(e)}), 500


@performance_bp.route("/meus_desafios", methods=["GET"])
@_token_required
def meus_desafios(current_user_id):
    """Lista desafios do profissional logado com métricas."""
    try:
        if mongo_db is None:
            return jsonify([]), 200

        cursor = mongo_db["desafios"].find(
            {"profissional_id": current_user_id},
            sort=[("criado_em", -1)]
        )
        desafios = []
        for d in cursor:
            d = _serializar(d)
            # Receita total gerada
            inscritos = mongo_db["inscricoes_desafio"].count_documents({
                "desafio_id": d["id"],
                "status_pagamento": "PAGO"
            })
            receita = round(d.get("preco", 0) * inscritos * 0.80, 2)
            d["inscritos_pagos"] = inscritos
            d["receita_profissional"] = receita
            desafios.append(d)

        return jsonify(desafios), 200

    except Exception as e:
        logger.error(f"[PERF] Erro meus_desafios: {e}")
        return jsonify([]), 200


@performance_bp.route("/desafios/<desafio_id>", methods=["PATCH"])
@_token_required
def editar_desafio(current_user_id, desafio_id):
    """Editar desafio (somente owner, somente rascunho ou antes do início)."""
    try:
        if mongo_db is None or not ObjectId.is_valid(desafio_id):
            return jsonify({"erro": "Inválido"}), 400

        desafio = mongo_db["desafios"].find_one({"_id": ObjectId(desafio_id)})
        if not desafio:
            return jsonify({"erro": "Desafio não encontrado"}), 404
        if desafio.get("profissional_id") != current_user_id:
            return jsonify({"erro": "Sem permissão"}), 403

        prof = _obter_profissional(current_user_id)
        if not _assinatura_prof_ativa(prof):
            return jsonify(_ERRO_ASSINATURA), 403

        dados = request.get_json(force=True)
        campos_aceitos = {
            "titulo", "descricao", "tipo", "duracao_dias", "preco",
            "vagas_total", "data_inicio", "imagem_capa_url", "o_que_inclui",
            "protocolo", "status",
        }
        update = {k: v for k, v in dados.items() if k in campos_aceitos}
        update["updated_at"] = datetime.now().isoformat()

        mongo_db["desafios"].update_one({"_id": ObjectId(desafio_id)}, {"$set": update})
        return jsonify({"sucesso": True}), 200

    except Exception as e:
        logger.error(f"[PERF] Erro editar_desafio: {e}")
        return jsonify({"erro": str(e)}), 500


@performance_bp.route("/desafios/<desafio_id>/inscritos", methods=["GET"])
@_token_required
def inscritos_desafio(current_user_id, desafio_id):
    """Lista alunos inscritos no desafio (apenas owner do desafio)."""
    try:
        if mongo_db is None or not ObjectId.is_valid(desafio_id):
            return jsonify([]), 200

        desafio = mongo_db["desafios"].find_one({"_id": ObjectId(desafio_id)})
        if not desafio or desafio.get("profissional_id") != current_user_id:
            return jsonify({"erro": "Sem permissão"}), 403

        prof = _obter_profissional(current_user_id)
        if not _assinatura_prof_ativa(prof):
            return jsonify(_ERRO_ASSINATURA), 403

        cursor = mongo_db["inscricoes_desafio"].find({"desafio_id": desafio_id})
        inscritos = []
        for ins in cursor:
            ins = _serializar(ins)
            # Enriquece com dados básicos do usuário
            try:
                u = mongo_db["usuarios"].find_one(
                    {"_id": ObjectId(ins["user_id"])},
                    {"nome": 1, "foto_perfil": 1, "nivel": 1}
                )
                if u:
                    ins["nome"]  = u.get("nome", "Atleta")
                    ins["foto"]  = u.get("foto_perfil", "")
                    ins["nivel"] = u.get("nivel", 1)
            except Exception:
                pass
            inscritos.append(ins)

        return jsonify(inscritos), 200

    except Exception as e:
        logger.error(f"[PERF] Erro inscritos_desafio: {e}")
        return jsonify([]), 200


# ══════════════════════════════════════════════════════════════
# ROTAS DE DESAFIOS — USUÁRIO
# ══════════════════════════════════════════════════════════════

@performance_bp.route("/desafios", methods=["GET"])
@_token_required
def listar_desafios(current_user_id):
    """
    Lista desafios ativos com filtros.
    ?tipo=emagrecimento&duracao=30&verificado=true
    """
    try:
        if mongo_db is None:
            return jsonify([]), 200

        filtro: dict = {"status": "ativo"}
        tipo = request.args.get("tipo")
        if tipo:
            filtro["tipo"] = tipo

        duracao = request.args.get("duracao")
        if duracao and duracao.isdigit():
            filtro["duracao_dias"] = int(duracao)

        tipo_prof = request.args.get("tipo_profissional")

        cursor = mongo_db["desafios"].find(filtro).sort("avaliacao_media", -1).limit(100)
        desafios = []
        for d in cursor:
            d = _serializar(d)
            # Enriquece com dados do profissional
            prof_doc = mongo_db["profissionais"].find_one(
                {"user_id": d["profissional_id"]},
                {"nome_profissional": 1, "tipo_profissional": 1,
                 "status_verificacao": 1, "foto_perfil_url": 1, "bio": 1}
            )
            # Dados do usuário do profissional
            try:
                u = mongo_db["usuarios"].find_one(
                    {"_id": ObjectId(d["profissional_id"])},
                    {"nome": 1, "foto_perfil": 1}
                )
                if u:
                    d["profissional_nome"] = u.get("nome", "Profissional")
                    d["profissional_foto"] = u.get("foto_perfil", "")
            except Exception:
                d["profissional_nome"] = "Profissional"
                d["profissional_foto"] = ""

            verificado = False
            if prof_doc:
                verificado = prof_doc.get("status_verificacao") == "verificado"
                d["profissional_tipo"] = prof_doc.get("tipo_profissional", "")
                if not d.get("profissional_foto") and prof_doc.get("foto_perfil_url"):
                    d["profissional_foto"] = prof_doc["foto_perfil_url"]
            d["profissional_verificado"] = verificado

            # Filtro opcional por tipo de profissional
            if tipo_prof and d.get("profissional_tipo", "") != tipo_prof:
                continue

            # Filtro verificado
            if request.args.get("verificado") == "true" and not verificado:
                continue

            desafios.append(d)

        return jsonify(desafios), 200

    except Exception as e:
        logger.error(f"[PERF] Erro listar_desafios: {e}")
        return jsonify([]), 200


@performance_bp.route("/desafios/<desafio_id>", methods=["GET"])
@_token_required
def detalhe_desafio(current_user_id, desafio_id):
    """Detalhes completos de um desafio + profissional + avaliações."""
    try:
        if mongo_db is None or not ObjectId.is_valid(desafio_id):
            return jsonify({"erro": "Inválido"}), 400

        d = mongo_db["desafios"].find_one({"_id": ObjectId(desafio_id)})
        if not d:
            return jsonify({"erro": "Desafio não encontrado"}), 404
        d = _serializar(d)

        # Dados do profissional
        try:
            u = mongo_db["usuarios"].find_one(
                {"_id": ObjectId(d["profissional_id"])},
                {"nome": 1, "foto_perfil": 1}
            )
            prof_doc = mongo_db["profissionais"].find_one({"user_id": d["profissional_id"]})
            if u:
                d["profissional_nome"] = u.get("nome", "Profissional")
                d["profissional_foto"] = u.get("foto_perfil", "")
            if prof_doc:
                d["profissional_verificado"] = prof_doc.get("status_verificacao") == "verificado"
                d["profissional_tipo"]       = prof_doc.get("tipo_profissional", "")
                d["profissional_bio"]        = prof_doc.get("bio", "")
        except Exception:
            pass

        # Vagas restantes
        vagas_total = d.get("vagas_total", 0)
        vagas_ocupadas = d.get("vagas_ocupadas", 0)
        d["vagas_restantes"] = (vagas_total - vagas_ocupadas) if vagas_total > 0 else None

        # Status da inscrição do usuário atual
        inscricao_minha = mongo_db["inscricoes_desafio"].find_one({
            "desafio_id": desafio_id,
            "user_id": current_user_id
        })
        d["minha_inscricao"] = _serializar(inscricao_minha) if inscricao_minha else None

        # Últimas 5 avaliações
        avals = list(mongo_db["inscricoes_desafio"].find(
            {"desafio_id": desafio_id, "avaliacao": {"$ne": None}},
            {"avaliacao": 1, "comentario": 1, "user_id": 1}
        ).sort("data_inscricao", -1).limit(5))
        for av in avals:
            try:
                u2 = mongo_db["usuarios"].find_one(
                    {"_id": ObjectId(av["user_id"])}, {"nome": 1}
                )
                av["nome_usuario"] = u2.get("nome", "Atleta") if u2 else "Atleta"
            except Exception:
                av["nome_usuario"] = "Atleta"
            av.pop("_id", None)
            av.pop("user_id", None)
        d["avaliacoes_recentes"] = avals

        return jsonify(d), 200

    except Exception as e:
        logger.error(f"[PERF] Erro detalhe_desafio: {e}")
        return jsonify({"erro": str(e)}), 500


@performance_bp.route("/desafios/<desafio_id>/inscrever", methods=["POST"])
@_token_required
def inscrever_desafio(current_user_id, desafio_id):
    """
    Usuário se inscreve num desafio.
    1. Cria cobrança no Asaas (PIX/Cartão)
    2. Cria inscrição com status PENDING
    3. Retorna dados para pagamento
    """
    try:
        if mongo_db is None or not ObjectId.is_valid(desafio_id):
            return jsonify({"erro": "Inválido"}), 400

        desafio = mongo_db["desafios"].find_one({"_id": ObjectId(desafio_id)})
        if not desafio or desafio.get("status") != "ativo":
            return jsonify({"erro": "Desafio não encontrado ou encerrado"}), 404

        # Verifica se já inscrito
        ja_inscrito = mongo_db["inscricoes_desafio"].find_one({
            "desafio_id": desafio_id,
            "user_id": current_user_id,
        })
        if ja_inscrito:
            return jsonify({"erro": "Você já está inscrito neste desafio"}), 409

        # Verifica vagas
        vagas_total = desafio.get("vagas_total", 0)
        vagas_ocupadas = desafio.get("vagas_ocupadas", 0)
        if vagas_total > 0 and vagas_ocupadas >= vagas_total:
            return jsonify({"erro": "Desafio sem vagas disponíveis"}), 409

        preco = float(desafio.get("preco", 0))
        dados_req = request.get_json(force=True) or {}
        metodo = str(dados_req.get("metodo", "pix")).lower()

        # [AURA NEW] Consentimento explícito de acesso a dados de saúde é obrigatório
        # antes de qualquer cobrança — sem ele, nem a inscrição nem o pagamento avançam.
        if dados_req.get("consentimento_aceito") is not True:
            return jsonify({
                "erro": "É necessário aceitar o termo de consentimento de acesso aos dados de saúde para se inscrever."
            }), 400

        memoria = carregar_memoria(current_user_id) or {}
        valor_aura, valor_prof = _calc_split(preco)

        # Cria inscrição pendente
        doc_insc = obter_schema_padrao_inscricao(
            desafio_id=desafio_id,
            user_id=current_user_id,
            profissional_id=str(desafio.get("profissional_id", "")),
        )
        doc_insc["valor_total"]         = preco
        doc_insc["valor_aura"]          = valor_aura
        doc_insc["valor_profissional"]  = valor_prof
        doc_insc["data_inicio"]         = desafio.get("data_inicio", "")
        doc_insc["metodo_pagamento"]    = metodo
        doc_insc["consentimento"] = {
            "aceito":       True,
            "versao_termo": str(dados_req.get("versao_termo", "v1")),
            "aceito_em":    datetime.now().isoformat(),
            "escopo":       ["peso", "altura", "percentual_gordura", "frequencia_treino", "treinos_completados"],
        }
        ins_result = mongo_db["inscricoes_desafio"].insert_one(doc_insc)
        inscricao_id = str(ins_result.inserted_id)

        # Cria cobrança Asaas
        dados_pag = {
            "user_id": current_user_id,
            "usuario": {
                "nome":     memoria.get("nome", "Atleta"),
                "email":    memoria.get("email", ""),
                "cpf":      memoria.get("cpf", ""),
                "telefone": memoria.get("telefone", ""),
            },
            "valor":          preco,
            "valor_produtos": preco,
            "valor_frete":    0,
            "metodo":         metodo,
            "descricao":      f"Desafio: {desafio.get('titulo', '')}",
            "tipo":           "desafio",
            "inscricao_id":   inscricao_id,
            "itens": [{"nome": desafio.get("titulo", "Desafio"), "valor": preco}],
        }
        resultado_pag = criar_cobranca(dados_pag)

        if "erro" in resultado_pag:
            # Reverte a inscrição se cobrança falhou
            mongo_db["inscricoes_desafio"].delete_one({"_id": ins_result.inserted_id})
            return jsonify(resultado_pag), 400

        # Vincula payment_id à inscrição
        mongo_db["inscricoes_desafio"].update_one(
            {"_id": ins_result.inserted_id},
            {"$set": {"asaas_id": resultado_pag["id_pagamento"]}}
        )
        # Guarda inscricao_id no pedido para o webhook encontrá-la
        mongo_db["pedidos"].update_one(
            {"asaas_id": resultado_pag["id_pagamento"]},
            {"$set": {"inscricao_id": inscricao_id, "desafio_id": desafio_id}}
        )

        resultado_pag["inscricao_id"] = inscricao_id
        return jsonify(resultado_pag), 200

    except Exception as e:
        logger.error(f"[PERF] Erro inscrever_desafio: {e}")
        return jsonify({"erro": str(e)}), 500


@performance_bp.route("/minhas_inscricoes", methods=["GET"])
@_token_required
def minhas_inscricoes(current_user_id):
    """Lista desafios em que o usuário está inscrito."""
    try:
        if mongo_db is None:
            return jsonify([]), 200

        cursor = mongo_db["inscricoes_desafio"].find(
            {"user_id": current_user_id},
            sort=[("data_inscricao", -1)]
        )
        inscricoes = []
        for ins in cursor:
            ins = _serializar(ins)
            # Enriquece com dados do desafio
            try:
                d = mongo_db["desafios"].find_one({"_id": ObjectId(ins["desafio_id"])})
                if d:
                    ins["desafio_titulo"]     = d.get("titulo", "")
                    ins["desafio_tipo"]       = d.get("tipo", "")
                    ins["desafio_duracao"]    = d.get("duracao_dias", 30)
                    ins["desafio_imagem"]     = d.get("imagem_capa_url", "")
                    # Dados do profissional
                    u = mongo_db["usuarios"].find_one(
                        {"_id": ObjectId(d["profissional_id"])}, {"nome": 1}
                    )
                    ins["profissional_nome"] = u.get("nome", "Profissional") if u else "Profissional"
            except Exception:
                pass
            inscricoes.append(ins)

        return jsonify(inscricoes), 200

    except Exception as e:
        logger.error(f"[PERF] Erro minhas_inscricoes: {e}")
        return jsonify([]), 200


# ══════════════════════════════════════════════════════════════
# ROTAS DE CHAT
# ══════════════════════════════════════════════════════════════

def _dupla_id(id1: str, id2: str) -> str:
    """Chave canônica de um par de participantes (ordem alfabética)."""
    a, b = sorted([str(id1), str(id2)])
    return f"{a}_{b}"


@performance_bp.route("/chat/<desafio_id>/mensagem", methods=["POST"])
@_token_required
def enviar_mensagem(current_user_id, desafio_id):
    """
    Envia mensagem no chat de GRUPO do desafio.
    Profissional e todos os alunos inscritos e pagos podem enviar.
    """
    try:
        if mongo_db is None or not ObjectId.is_valid(desafio_id):
            return jsonify({"erro": "Inválido"}), 400

        dados = request.get_json(force=True)
        texto = str(dados.get("texto", "")).strip()
        if not texto:
            return jsonify({"erro": "Texto obrigatório"}), 400

        desafio = mongo_db["desafios"].find_one({"_id": ObjectId(desafio_id)})
        if not desafio:
            return jsonify({"erro": "Desafio não encontrado"}), 404

        prof_desafio = _obter_profissional(desafio.get("profissional_id", ""))
        if not _assinatura_prof_ativa(prof_desafio):
            return jsonify(_ERRO_CHAT_BLOQ), 403

        is_profissional = desafio.get("profissional_id") == current_user_id
        if not is_profissional:
            inscricao = mongo_db["inscricoes_desafio"].find_one({
                "desafio_id": desafio_id,
                "user_id": current_user_id,
                "status_pagamento": "PAGO",
            })
            if not inscricao:
                return jsonify({"erro": "Você precisa estar inscrito para enviar mensagens"}), 403

        memoria = carregar_memoria(current_user_id) or {}
        doc = obter_schema_padrao_mensagem_desafio(desafio_id, current_user_id)
        doc.update({
            "canal":          "grupo",
            "dupla_id":       None,
            "remetente_nome": memoria.get("nome", "Atleta"),
            "remetente_tipo": "profissional" if is_profissional else "aluno",
            "texto":          texto,
        })

        mongo_db["chat_desafios"].insert_one(doc)
        return jsonify({"sucesso": True}), 201

    except Exception as e:
        logger.error(f"[PERF] Erro enviar_mensagem: {e}")
        return jsonify({"erro": str(e)}), 500


@performance_bp.route("/chat/<desafio_id>/mensagens", methods=["GET"])
@_token_required
def listar_mensagens(current_user_id, desafio_id):
    """
    Retorna mensagens do chat de GRUPO.
    Profissional e alunos pagos veem todas as mensagens do grupo.
    Compatível com documentos legados (tipo_mensagem="broadcast", sem campo canal).
    """
    try:
        if mongo_db is None or not ObjectId.is_valid(desafio_id):
            return jsonify([]), 200

        desafio = mongo_db["desafios"].find_one({"_id": ObjectId(desafio_id)})
        if not desafio:
            return jsonify([]), 200

        is_profissional = desafio.get("profissional_id") == current_user_id
        if not is_profissional:
            inscricao = mongo_db["inscricoes_desafio"].find_one({
                "desafio_id": desafio_id,
                "user_id": current_user_id,
                "status_pagamento": "PAGO",
            })
            if not inscricao:
                return jsonify({"erro": "Você precisa estar inscrito para ver mensagens"}), 403

        # Documentos novos (canal="grupo") + legados (tipo_mensagem="broadcast" sem campo canal)
        filtro = {
            "desafio_id": desafio_id,
            "$or": [
                {"canal": "grupo"},
                {"tipo_mensagem": "broadcast", "canal": {"$exists": False}},
            ],
        }

        cursor = mongo_db["chat_desafios"].find(filtro).sort("enviada_em", 1).limit(300)
        msgs = []
        for m in cursor:
            m.pop("_id", None)
            msgs.append(m)

        return jsonify(msgs), 200

    except Exception as e:
        logger.error(f"[PERF] Erro listar_mensagens: {e}")
        return jsonify([]), 200


@performance_bp.route("/chat/<desafio_id>/privado/<aluno_id>/mensagem", methods=["POST"])
@_token_required
def enviar_mensagem_privada(current_user_id, desafio_id, aluno_id):
    """
    Envia mensagem no chat privado profissional↔aluno.
    Apenas o profissional do desafio ou o próprio aluno podem enviar.
    """
    try:
        if mongo_db is None or not ObjectId.is_valid(desafio_id):
            return jsonify({"erro": "Inválido"}), 400

        dados = request.get_json(force=True)
        texto = str(dados.get("texto", "")).strip()
        if not texto:
            return jsonify({"erro": "Texto obrigatório"}), 400

        desafio = mongo_db["desafios"].find_one({"_id": ObjectId(desafio_id)})
        if not desafio:
            return jsonify({"erro": "Desafio não encontrado"}), 404

        profissional_id = desafio.get("profissional_id", "")
        prof_desafio = _obter_profissional(profissional_id)
        if not _assinatura_prof_ativa(prof_desafio):
            return jsonify(_ERRO_CHAT_BLOQ), 403

        is_profissional = profissional_id == current_user_id
        is_aluno        = current_user_id == aluno_id

        if not is_profissional and not is_aluno:
            return jsonify({"erro": "Sem permissão para este chat"}), 403

        inscricao = mongo_db["inscricoes_desafio"].find_one({
            "desafio_id": desafio_id,
            "user_id":    aluno_id,
            "status_pagamento": "PAGO",
        })
        if not inscricao:
            return jsonify({"erro": "Aluno não está inscrito no desafio"}), 403

        dupla   = _dupla_id(profissional_id, aluno_id)
        memoria = carregar_memoria(current_user_id) or {}
        doc     = obter_schema_padrao_mensagem_desafio(desafio_id, current_user_id)
        doc.update({
            "canal":          "privado",
            "dupla_id":       dupla,
            "remetente_nome": memoria.get("nome", "Atleta"),
            "remetente_tipo": "profissional" if is_profissional else "aluno",
            "texto":          texto,
        })

        mongo_db["chat_desafios"].insert_one(doc)
        return jsonify({"sucesso": True}), 201

    except Exception as e:
        logger.error(f"[PERF] Erro enviar_mensagem_privada: {e}")
        return jsonify({"erro": str(e)}), 500


@performance_bp.route("/chat/<desafio_id>/privado/<aluno_id>/mensagens", methods=["GET"])
@_token_required
def listar_mensagens_privadas(current_user_id, desafio_id, aluno_id):
    """
    Retorna mensagens do chat privado entre profissional e um aluno específico.
    Acessível pelo profissional do desafio ou pelo próprio aluno.
    """
    try:
        if mongo_db is None or not ObjectId.is_valid(desafio_id):
            return jsonify([]), 200

        desafio = mongo_db["desafios"].find_one({"_id": ObjectId(desafio_id)})
        if not desafio:
            return jsonify([]), 200

        profissional_id = desafio.get("profissional_id", "")
        is_profissional = profissional_id == current_user_id
        is_aluno        = current_user_id == aluno_id

        if not is_profissional and not is_aluno:
            return jsonify({"erro": "Sem permissão para este chat"}), 403

        dupla  = _dupla_id(profissional_id, aluno_id)
        filtro = {"canal": "privado", "desafio_id": desafio_id, "dupla_id": dupla}

        cursor = mongo_db["chat_desafios"].find(filtro).sort("enviada_em", 1).limit(100)
        msgs = []
        for m in cursor:
            m.pop("_id", None)
            msgs.append(m)

        # Marca mensagens recebidas como lidas
        outro_id = aluno_id if is_profissional else profissional_id
        mongo_db["chat_desafios"].update_many(
            {**filtro, "remetente_id": outro_id, "lida": False},
            {"$set": {"lida": True}},
        )

        return jsonify(msgs), 200

    except Exception as e:
        logger.error(f"[PERF] Erro listar_mensagens_privadas: {e}")
        return jsonify([]), 200


# ── Função de limpeza exportada para o scheduler ────────────────────────────

def limpar_mensagens_chat() -> tuple:
    """
    Aplica os dois critérios de retenção independentemente por canal:
      - Grupo:  máx 300 mensagens OU 30 dias por desafio_id
      - Privado: máx 100 mensagens OU 30 dias por (desafio_id, dupla_id)
    Retorna (total_grupo_deletadas, total_privado_deletadas).
    """
    if mongo_db is None:
        return 0, 0

    limite_30d    = (datetime.now() - timedelta(days=30)).isoformat()
    total_grupo   = 0
    total_privado = 0

    # ── GRUPO ────────────────────────────────────────────────────────────────
    desafio_ids = mongo_db["chat_desafios"].distinct("desafio_id", {"canal": "grupo"})
    for did in desafio_ids:
        base = {"canal": "grupo", "desafio_id": did}

        # 1. Critério de data (30 dias)
        r = mongo_db["chat_desafios"].delete_many({**base, "enviada_em": {"$lt": limite_30d}})
        total_grupo += r.deleted_count

        # 2. Critério de contagem (300)
        if mongo_db["chat_desafios"].count_documents(base) > 300:
            cutoff = list(
                mongo_db["chat_desafios"]
                .find(base, {"enviada_em": 1})
                .sort("enviada_em", -1)
                .skip(300)
                .limit(1)
            )
            if cutoff:
                r2 = mongo_db["chat_desafios"].delete_many(
                    {**base, "enviada_em": {"$lte": cutoff[0]["enviada_em"]}}
                )
                total_grupo += r2.deleted_count

    # ── PRIVADO ──────────────────────────────────────────────────────────────
    pares = list(mongo_db["chat_desafios"].aggregate([
        {"$match": {"canal": "privado"}},
        {"$group": {"_id": {"desafio_id": "$desafio_id", "dupla_id": "$dupla_id"}}},
    ]))
    for par in pares:
        did  = par["_id"]["desafio_id"]
        duid = par["_id"]["dupla_id"]
        base = {"canal": "privado", "desafio_id": did, "dupla_id": duid}

        # 1. Critério de data (30 dias)
        r = mongo_db["chat_desafios"].delete_many({**base, "enviada_em": {"$lt": limite_30d}})
        total_privado += r.deleted_count

        # 2. Critério de contagem (100)
        if mongo_db["chat_desafios"].count_documents(base) > 100:
            cutoff = list(
                mongo_db["chat_desafios"]
                .find(base, {"enviada_em": 1})
                .sort("enviada_em", -1)
                .skip(100)
                .limit(1)
            )
            if cutoff:
                r2 = mongo_db["chat_desafios"].delete_many(
                    {**base, "enviada_em": {"$lte": cutoff[0]["enviada_em"]}}
                )
                total_privado += r2.deleted_count

    # ── CHAT_CLÃ ─────────────────────────────────────────────────────────────────
    # Critérios: 300 msgs/clã OU 30 dias. Campo de data: created_at
    cla_ids = mongo_db["chat_cla"].distinct("cla_id")
    total_cla = 0
    for cid in cla_ids:
        base = {"cla_id": cid}
        r = mongo_db["chat_cla"].delete_many({**base, "created_at": {"$lt": limite_30d}})
        total_cla += r.deleted_count
        if mongo_db["chat_cla"].count_documents(base) > 300:
            cutoff = list(
                mongo_db["chat_cla"]
                .find(base, {"created_at": 1})
                .sort("created_at", -1)
                .skip(300)
                .limit(1)
            )
            if cutoff:
                r2 = mongo_db["chat_cla"].delete_many(
                    {**base, "created_at": {"$lte": cutoff[0]["created_at"]}}
                )
                total_cla += r2.deleted_count

    return total_grupo, total_privado, total_cla


# ══════════════════════════════════════════════════════════════
# ROTAS DE AVALIAÇÃO
# ══════════════════════════════════════════════════════════════

@performance_bp.route("/inscricoes/<inscricao_id>/status", methods=["GET"])
@_token_required
def status_inscricao(current_user_id, inscricao_id):
    """
    Rota leve para polling de confirmação PIX.
    Retorna apenas status_pagamento e pago_em da inscrição.
    user_id no filtro garante que só o próprio inscrito pode checar.
    """
    try:
        if mongo_db is None or not ObjectId.is_valid(inscricao_id):
            return jsonify({"erro": "Inválido"}), 400

        inscricao = mongo_db["inscricoes_desafio"].find_one(
            {"_id": ObjectId(inscricao_id), "user_id": current_user_id},
            {"status_pagamento": 1, "pago_em": 1, "desafio_id": 1}
        )
        if not inscricao:
            return jsonify({"erro": "Inscrição não encontrada"}), 404

        return jsonify({
            "inscricao_id":    inscricao_id,
            "status_pagamento": inscricao.get("status_pagamento", "PENDING"),
            "pago_em":          inscricao.get("pago_em"),
            "desafio_id":       inscricao.get("desafio_id"),
        }), 200

    except Exception as e:
        logger.error(f"[PERF] Erro status_inscricao: {e}")
        return jsonify({"erro": str(e)}), 500


@performance_bp.route("/inscricoes/<inscricao_id>/retomar_pagamento", methods=["GET"])
@_token_required
def retomar_pagamento_desafio(current_user_id, inscricao_id):
    """
    Retorna dados do pagamento existente (QR PIX ou link cartão) sem criar nova cobrança.
    Disponível apenas enquanto status_pagamento == PENDING.
    """
    try:
        if mongo_db is None or not ObjectId.is_valid(inscricao_id):
            return jsonify({"erro": "Inválido"}), 400

        inscricao = mongo_db["inscricoes_desafio"].find_one(
            {"_id": ObjectId(inscricao_id), "user_id": current_user_id}
        )
        if not inscricao:
            return jsonify({"erro": "Inscrição não encontrada"}), 404

        if inscricao.get("status_pagamento") == "PAGO":
            return jsonify({"erro": "Pagamento já confirmado"}), 409

        asaas_id = inscricao.get("asaas_id", "")
        if not asaas_id:
            return jsonify({"erro": "Dados de pagamento não encontrados para esta inscrição"}), 404

        headers = {
            "Content-Type": "application/json",
            "access_token": os.getenv("ASAAS_ACCESS_TOKEN", ""),
        }
        metodo = inscricao.get("metodo_pagamento", "pix")

        if metodo == "pix":
            resp = _requests.get(
                f"https://www.asaas.com/api/v3/payments/{asaas_id}/pixQrCode",
                headers=headers,
                timeout=10,
            )
            if resp.status_code == 200:
                qr = resp.json()
                return jsonify({
                    "inscricao_id": inscricao_id,
                    "tipo": "pix",
                    "payload_pix": qr.get("payload"),
                    "imagem_qr":   qr.get("encodedImage"),
                    "asaas_id":    asaas_id,
                }), 200
            # QR vencido ou indisponível — cai no fallback abaixo

        # Cartão ou fallback de PIX sem QR: busca dados do pagamento para pegar invoiceUrl
        resp2 = _requests.get(
            f"https://www.asaas.com/api/v3/payments/{asaas_id}",
            headers=headers,
            timeout=10,
        )
        if resp2.status_code == 200:
            data = resp2.json()
            return jsonify({
                "inscricao_id":   inscricao_id,
                "tipo":           data.get("billingType", "cartao").lower(),
                "link_pagamento": data.get("invoiceUrl"),
                "asaas_id":       asaas_id,
            }), 200

        logger.warning(f"[PERF] Asaas retornou {resp2.status_code} para pagamento {asaas_id}")
        return jsonify({"erro": "Não foi possível recuperar os dados do pagamento no gateway"}), 404

    except Exception as e:
        logger.error(f"[PERF] Erro retomar_pagamento: {e}")
        return jsonify({"erro": str(e)}), 500


@performance_bp.route("/inscricoes/<inscricao_id>/avaliar", methods=["POST"])
@_token_required
def avaliar_desafio(current_user_id, inscricao_id):
    """Usuário avalia o desafio após conclusão."""
    try:
        if mongo_db is None or not ObjectId.is_valid(inscricao_id):
            return jsonify({"erro": "Inválido"}), 400

        dados = request.get_json(force=True)
        nota = int(dados.get("nota", 0))
        if nota < 1 or nota > 5:
            return jsonify({"erro": "Nota deve ser entre 1 e 5"}), 400

        inscricao = mongo_db["inscricoes_desafio"].find_one({"_id": ObjectId(inscricao_id)})
        if not inscricao or inscricao.get("user_id") != current_user_id:
            return jsonify({"erro": "Inscrição não encontrada"}), 404

        if inscricao.get("avaliacao") is not None:
            return jsonify({"erro": "Você já avaliou este desafio"}), 409

        comentario = str(dados.get("comentario", "")).strip()[:500]
        mongo_db["inscricoes_desafio"].update_one(
            {"_id": ObjectId(inscricao_id)},
            {"$set": {"avaliacao": nota, "comentario": comentario}}
        )

        # Recalcula média do desafio
        desafio_id = inscricao.get("desafio_id")
        pipeline = [
            {"$match": {"desafio_id": desafio_id, "avaliacao": {"$ne": None}}},
            {"$group": {"_id": None, "media": {"$avg": "$avaliacao"}, "total": {"$sum": 1}}}
        ]
        res = list(mongo_db["inscricoes_desafio"].aggregate(pipeline))
        if res:
            media = round(res[0]["media"], 1)
            total = res[0]["total"]
            mongo_db["desafios"].update_one(
                {"_id": ObjectId(desafio_id)},
                {"$set": {"avaliacao_media": media, "total_avaliacoes": total}}
            )
            # Recalcula média do profissional
            profissional_id = inscricao.get("profissional_id")
            if profissional_id:
                pipeline2 = [
                    {"$match": {"profissional_id": profissional_id, "avaliacao": {"$ne": None}}},
                    {"$group": {"_id": None, "media": {"$avg": "$avaliacao"}, "total": {"$sum": 1}}}
                ]
                res2 = list(mongo_db["inscricoes_desafio"].aggregate(pipeline2))
                if res2:
                    mongo_db["profissionais"].update_one(
                        {"user_id": profissional_id},
                        {"$set": {
                            "avaliacao_media": round(res2[0]["media"], 1),
                            "total_avaliacoes": res2[0]["total"],
                        }}
                    )

        return jsonify({"sucesso": True}), 200

    except Exception as e:
        logger.error(f"[PERF] Erro avaliar_desafio: {e}")
        return jsonify({"erro": str(e)}), 500


# ══════════════════════════════════════════════════════════════
# ROTA DE SAÚDE DO ALUNO — PROFISSIONAL (acesso via grant)
# ══════════════════════════════════════════════════════════════

@performance_bp.route("/alunos/<aluno_id>/saude", methods=["GET"])
@_token_required
def saude_do_aluno(current_user_id, aluno_id):
    """
    Profissional consulta os dados de saúde de um aluno específico.
    Só retorna algo se existir um grant ATIVO para profissional_id+aluno_id
    (índice composto profissional_id+aluno_id+status em grants_saude).
    """
    try:
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500
        if not ObjectId.is_valid(aluno_id):
            return jsonify({"erro": "Aluno inválido"}), 400

        prof = _obter_profissional(current_user_id)
        if not _assinatura_prof_ativa(prof):
            return jsonify(_ERRO_ASSINATURA), 403

        grant = mongo_db["grants_saude"].find_one({
            "profissional_id": current_user_id,
            "aluno_id":         aluno_id,
            "status":           "ativo",
        })
        if not grant:
            return jsonify({
                "erro": "Você não tem acesso ativo aos dados de saúde deste aluno."
            }), 403

        aluno = mongo_db["usuarios"].find_one({"_id": ObjectId(aluno_id)})
        if not aluno:
            return jsonify({"erro": "Aluno não encontrado"}), 404

        # Mesma migração reversa usada em carregar_memoria(): preenche o subdocumento
        # com os campos legados (peso_kg/altura_cm na raiz) se ele ainda não existir.
        perfil_saude = aluno.get("perfil_saude") or {}
        if not perfil_saude.get("peso_kg") and aluno.get("peso_kg") is not None:
            perfil_saude["peso_kg"] = aluno.get("peso_kg")
        if not perfil_saude.get("altura_cm") and aluno.get("altura_cm") is not None:
            perfil_saude["altura_cm"] = aluno.get("altura_cm")

        # Dados derivados da coleção "atividades" (não duplicados no perfil_saude).
        ha_7_dias = (datetime.now() - timedelta(days=7)).isoformat()
        treinos_completados_total = mongo_db["atividades"].count_documents({
            "user_id": aluno_id, "tipo": "Treino",
        })
        frequencia_treino_semanal = mongo_db["atividades"].count_documents({
            "user_id": aluno_id, "tipo": "Treino",
            "data_atividade": {"$gte": ha_7_dias},
        })

        def _campo_health(campo):
            """Retorna o subdocumento {valor, fonte, sincronizado_em} ou None."""
            v = perfil_saude.get(campo)
            if isinstance(v, dict):
                return v
            return None

        return jsonify({
            "aluno_id": aluno_id,
            "nome":     aluno.get("nome", "Atleta"),
            "perfil_saude": {
                "peso_kg":            perfil_saude.get("peso_kg"),
                "altura_cm":          perfil_saude.get("altura_cm"),
                "percentual_gordura": perfil_saude.get("percentual_gordura"),
                "atualizado_em":      perfil_saude.get("atualizado_em", ""),
                "fc_repouso":         _campo_health("fc_repouso"),
                "passos_diarios":     _campo_health("passos_diarios"),
                "calorias_ativas":    _campo_health("calorias_ativas"),
                "sono_horas":         _campo_health("sono_horas"),
            },
            "frequencia_treino_semanal": frequencia_treino_semanal,
            "treinos_completados_total": treinos_completados_total,
            "grant": {
                "desafio_id":      grant.get("desafio_id"),
                "data_concessao":  grant.get("data_concessao"),
                "data_expiracao":  grant.get("data_expiracao"),
            },
        }), 200

    except Exception as e:
        logger.error(f"[PERF] Erro saude_do_aluno: {e}")
        return jsonify({"erro": str(e)}), 500


# ══════════════════════════════════════════════════════════════
# ROTA DE PROGRESSO (aluno registra dia concluído)
# ══════════════════════════════════════════════════════════════

@performance_bp.route("/inscricoes/<inscricao_id>/progresso", methods=["POST"])
@_token_required
def registrar_progresso(current_user_id, inscricao_id):
    """Aluno registra que completou o treino do dia."""
    try:
        if mongo_db is None or not ObjectId.is_valid(inscricao_id):
            return jsonify({"erro": "Inválido"}), 400

        inscricao = mongo_db["inscricoes_desafio"].find_one({"_id": ObjectId(inscricao_id)})
        if not inscricao or inscricao.get("user_id") != current_user_id:
            return jsonify({"erro": "Inscrição não encontrada"}), 404

        duracao = 30
        try:
            d = mongo_db["desafios"].find_one({"_id": ObjectId(inscricao.get("desafio_id", ""))})
            if d:
                duracao = d.get("duracao_dias", 30)
        except Exception:
            pass

        progresso_atual = inscricao.get("progresso", {})
        ultimo_registro = progresso_atual.get("ultimo_registro")
        hoje = datetime.now().date().isoformat()

        ja_registrou_hoje = False
        if ultimo_registro:
            try:
                ja_registrou_hoje = datetime.fromisoformat(ultimo_registro).date().isoformat() == hoje
            except Exception:
                pass

        dias_completos = progresso_atual.get("dias_completos", 0)
        treinos_total = progresso_atual.get("treinos_total", 0) + 1

        if not ja_registrou_hoje:
            dias_completos += 1

        percentual = round((dias_completos / duracao) * 100, 1)
        agora = datetime.now().isoformat()

        novo_status = "concluido" if percentual >= 100 else "em_andamento"
        mongo_db["inscricoes_desafio"].update_one(
            {"_id": ObjectId(inscricao_id)},
            {"$set": {
                "progresso.dias_completos": dias_completos,
                "progresso.treinos_total": treinos_total,
                "progresso.percentual": percentual,
                "progresso.ultimo_registro": agora,
                "status_desafio": novo_status,
            }}
        )

        return jsonify({
            "sucesso": True,
            "dias_completos": dias_completos,
            "treinos_total": treinos_total,
            "percentual": percentual,
            "mesmo_dia": ja_registrou_hoje,
        }), 200

    except Exception as e:
        logger.error(f"[PERF] Erro registrar_progresso: {e}")
        return jsonify({"erro": str(e)}), 500
