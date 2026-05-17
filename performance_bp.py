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


def _profissional_pode_criar(prof_doc: dict) -> bool:
    """Verifica se o plano do profissional está ativo."""
    if not prof_doc:
        return False
    if not prof_doc.get("plano_ativo"):
        return False
    expira = prof_doc.get("plano_expira", "")
    if expira and datetime.fromisoformat(expira) < datetime.now():
        return False
    return True


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
    Cria cobrança de R$99,90 via Asaas. Quando pago (webhook),
    o campo verificacao_paga é marcado como True.
    """
    try:
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        prof = _obter_profissional(current_user_id)
        if not prof:
            return jsonify({"erro": "Perfil profissional não encontrado"}), 404

        if prof.get("verificacao_paga"):
            return jsonify({"erro": "Verificação já foi paga. Análise em andamento."}), 409

        memoria = carregar_memoria(current_user_id) or {}
        dados_pag = {
            "user_id": current_user_id,
            "usuario": {
                "nome":     memoria.get("nome", "Profissional"),
                "email":    memoria.get("email", ""),
                "cpf":      memoria.get("cpf", ""),
                "telefone": memoria.get("telefone", ""),
            },
            "valor": 99.90,
            "valor_produtos": 99.90,
            "valor_frete": 0,
            "metodo": "pix",
            "descricao": "Verificação de Credenciais Profissionais AURA",
            "tipo": "verificacao_profissional",
            "itens": [{"nome": "Verificação CREF/CRN/CRM", "valor": 99.90}],
        }

        resultado = criar_cobranca(dados_pag)
        if "erro" in resultado:
            return jsonify(resultado), 400

        # Salva o payment_id para cruzar com o webhook
        mongo_db["profissionais"].update_one(
            {"user_id": current_user_id},
            {"$set": {
                "asaas_verificacao_id": resultado["id_pagamento"],
                "updated_at": datetime.now().isoformat()
            }}
        )

        return jsonify(resultado), 200

    except Exception as e:
        logger.error(f"[PERF] Erro solicitar_verificacao: {e}")
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

        if not _profissional_pode_criar(prof):
            return jsonify({"erro": "Plano profissional expirado. Assine para continuar criando desafios."}), 403

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

@performance_bp.route("/chat/<desafio_id>/mensagem", methods=["POST"])
@_token_required
def enviar_mensagem(current_user_id, desafio_id):
    """
    Envia mensagem no chat do desafio.
    Profissional pode enviar broadcast (destinatario_id=null) ou individual.
    Aluno só pode enviar mensagem individual para o profissional.
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

        is_profissional = desafio.get("profissional_id") == current_user_id
        # Verifica inscrição para alunos
        if not is_profissional:
            inscricao = mongo_db["inscricoes_desafio"].find_one({
                "desafio_id": desafio_id,
                "user_id": current_user_id,
                "status_pagamento": "PAGO"
            })
            if not inscricao:
                return jsonify({"erro": "Você precisa estar inscrito para enviar mensagens"}), 403

        memoria = carregar_memoria(current_user_id) or {}
        destinatario_id = dados.get("destinatario_id")

        # Aluno não pode fazer broadcast
        if not is_profissional and not destinatario_id:
            destinatario_id = desafio["profissional_id"]

        doc = obter_schema_padrao_mensagem_desafio(desafio_id, current_user_id)
        doc.update({
            "remetente_nome":  memoria.get("nome", "Atleta"),
            "remetente_tipo":  "profissional" if is_profissional else "aluno",
            "tipo_mensagem":   "broadcast" if not destinatario_id else "individual",
            "destinatario_id": destinatario_id,
            "texto":           texto,
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
    Retorna mensagens do chat.
    Aluno: broadcasts + suas mensagens individuais.
    Profissional: todas.
    """
    try:
        if mongo_db is None or not ObjectId.is_valid(desafio_id):
            return jsonify([]), 200

        desafio = mongo_db["desafios"].find_one({"_id": ObjectId(desafio_id)})
        if not desafio:
            return jsonify([]), 200

        is_profissional = desafio.get("profissional_id") == current_user_id

        if is_profissional:
            filtro = {"desafio_id": desafio_id}
        else:
            filtro = {
                "desafio_id": desafio_id,
                "$or": [
                    {"tipo_mensagem": "broadcast"},
                    {"remetente_id": current_user_id},
                    {"destinatario_id": current_user_id},
                ]
            }

        cursor = mongo_db["chat_desafios"].find(filtro).sort("enviada_em", 1).limit(200)
        msgs = []
        for m in cursor:
            m.pop("_id", None)
            msgs.append(m)

        # Marca mensagens do usuário como lidas
        mongo_db["chat_desafios"].update_many(
            {"desafio_id": desafio_id, "destinatario_id": current_user_id, "lida": False},
            {"$set": {"lida": True}}
        )

        return jsonify(msgs), 200

    except Exception as e:
        logger.error(f"[PERF] Erro listar_mensagens: {e}")
        return jsonify([]), 200


# ══════════════════════════════════════════════════════════════
# ROTAS DE AVALIAÇÃO
# ══════════════════════════════════════════════════════════════

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

        dias_completos = inscricao.get("progresso", {}).get("dias_completos", 0) + 1
        percentual = round((dias_completos / duracao) * 100, 1)
        agora = datetime.now().isoformat()

        novo_status = "concluido" if percentual >= 100 else "em_andamento"
        mongo_db["inscricoes_desafio"].update_one(
            {"_id": ObjectId(inscricao_id)},
            {"$set": {
                "progresso.dias_completos": dias_completos,
                "progresso.percentual": percentual,
                "progresso.ultimo_registro": agora,
                "status_desafio": novo_status,
            }}
        )

        return jsonify({"sucesso": True, "dias_completos": dias_completos, "percentual": percentual}), 200

    except Exception as e:
        logger.error(f"[PERF] Erro registrar_progresso: {e}")
        return jsonify({"erro": str(e)}), 500
