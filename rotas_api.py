import logging
import os
import requests
import jwt
from functools import wraps
from datetime import datetime, timedelta
from typing import Dict, Any
from flask import request, jsonify, Blueprint
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash

# --- IMPORTAÇÕES DA NOVA ARQUITETURA ---
from data_user import carregar_memoria, salvar_memoria, gastar_moedas
from data_manager import (
    obter_ranking_global, ler_plano, mongo_db,
    buscar_usuario_por_email, criar_novo_usuario, atualizar_usuario
)
from logic_gamificacao import (
    gerar_missoes_diarias, aplicar_xp, normalizar_ofensiva,
    registrar_conclusao_missao, ativar_seguro_ofensiva
)
from logic_equilibrio import calcular_e_atualizar_equilibrio
from logic import processar_comando 
from logic_feedback import gerar_feedback_emocional
from logic_asaas import criar_cobranca

# [AURA LOGISTICS] Importação do novo serviço de frete
from logic_frete import calcular_cotacao_frete

# Configuração de Logs
logger = logging.getLogger("AURA_API_ROTAS")

# [AURA FIX 404] Blueprint SEM prefixo interno para não duplicar com o registro no app.py
api_bp = Blueprint('api_bp', __name__)

# ===================================================
# 🔐 JWT — CONFIGURAÇÃO E HELPERS
# ===================================================

JWT_SECRET    = os.getenv("JWT_SECRET", "aura-mude-esta-chave-em-producao")
JWT_ALGORITHM = "HS256"
JWT_EXP_DAYS  = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_DAYS", 7))

def gerar_token_jwt(user_id: str) -> str:
    """Gera um token JWT assinado. Validade lida de JWT_ACCESS_TOKEN_EXPIRES_DAYS no .env."""
    payload = {
        "user_id": str(user_id),
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(days=JWT_EXP_DAYS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

# ===================================================
# 🔐 MIDDLEWARE DE AUTENTICAÇÃO (JWT NATIVO)
# ===================================================

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({"erro": "Token mal formatado"}), 401

        if not token:
            return jsonify({"erro": "Token ausente"}), 401

        try:
            # Tenta decodificar como JWT nativo
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            current_user_id = payload.get("user_id")
            if not current_user_id:
                return jsonify({"erro": "Token inválido: user_id ausente"}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({"erro": "Sessão expirada. Faça login novamente."}), 401
        except jwt.InvalidTokenError:
            # Compatibilidade retroativa: aceita ID direto durante migração do Base44
            logger.warning("Token não-JWT recebido — usando como ID direto (modo migração).")
            current_user_id = str(token).strip().replace('"', '').replace("'", "")

        return f(current_user_id, *args, **kwargs)
    return decorated

# ===================================================
# 🔐 AUTENTICAÇÃO NATIVA — REGISTER / LOGIN
# ===================================================

@api_bp.route('/auth/register', methods=['POST', 'OPTIONS'])
def registrar_usuario():
    """
    Cadastra novo usuário com email/senha e retorna JWT.
    [AURA FIX] Aceita OPTIONS explicitamente para evitar 404 no handshake do iOS.
    """
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    try:
        dados = request.get_json(force=True)
        email = dados.get('email', '').strip().lower()
        senha = dados.get('senha', '')
        nome  = dados.get('nome', 'Atleta Aura').strip()

        if not email or not senha:
            return jsonify({"erro": "Email e senha são obrigatórios"}), 400

        if len(senha) < 6:
            return jsonify({"erro": "Senha deve ter ao menos 6 caracteres"}), 400

        if buscar_usuario_por_email(email):
            return jsonify({"erro": "Este e-mail já está cadastrado"}), 409

        novo_user = criar_novo_usuario(email=email, nome=nome, auth_provider="email")
        if not novo_user:
            return jsonify({"erro": "Falha ao criar usuário. Tente novamente."}), 500

        atualizar_usuario(novo_user["_id"], {"senha_hash": generate_password_hash(senha)})

        token = gerar_token_jwt(novo_user["_id"])
        logger.info(f"🆕 Novo usuário registrado nativamente: {email}")

        seguro_ativo = False
        try:
            if dados.get("seguro_expira_em"):
                seguro_ativo = datetime.fromisoformat(str(dados.get("seguro_expira_em"))) >= datetime.now()
        except Exception:
            seguro_ativo = False

        return jsonify({
            "sucesso": True,
            "token": token,
            "user_id": str(novo_user["_id"]),
            "nome": nome,
            "email": email
        }), 201

    except Exception as e:
        logger.error(f"Erro no registro: {e}")
        return jsonify({"erro": "Falha interna no cadastro"}), 500


@api_bp.route('/auth/login', methods=['POST', 'OPTIONS'])
def login_usuario():
    """
    Autentica usuário com email/senha e retorna JWT.
    [AURA FIX] Aceita OPTIONS explicitamente para evitar 404 no handshake do iOS.
    """
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    try:
        dados = request.get_json(force=True)
        email = dados.get('email', '').strip().lower()
        senha = dados.get('senha', '')

        if not email or not senha:
            return jsonify({"erro": "Email e senha são obrigatórios"}), 400

        usuario = buscar_usuario_por_email(email)
        if not usuario:
            return jsonify({"erro": "Credenciais inválidas"}), 401

        senha_hash = usuario.get('senha_hash', '')
        if not senha_hash or not check_password_hash(senha_hash, senha):
            return jsonify({"erro": "Credenciais inválidas"}), 401

        token = gerar_token_jwt(str(usuario["_id"]))
        logger.info(f"✅ Login bem-sucedido: {email}")

        return jsonify({
            "sucesso": True,
            "token": token,
            "user_id": str(usuario["_id"]),
            "nome": usuario.get("nome", "Atleta"),
            "email": email,
            "plano": usuario.get("plano", "free")
        })

    except Exception as e:
        logger.error(f"Erro no login: {e}")
        return jsonify({"erro": "Falha interna no login"}), 500

# ===================================================
# 👤 STATUS E PROGRESSÃO (MULTIJOGADOR + IAP READY)
# ===================================================

@api_bp.route('/usuario/status', methods=['GET'])
@token_required
def get_status_jogador(current_user_id):
    try:
        dados = carregar_memoria(current_user_id)
        if not dados: 
            return jsonify({"erro": "Perfil não encontrado no Atlas"}), 404

        # Aplica regra de quebra da ofensiva antes de devolver status
        status_ofensiva = normalizar_ofensiva(current_user_id)
        dados = carregar_memoria(current_user_id)
        if not dados:
            return jsonify({"erro": "Perfil não encontrado no Atlas"}), 404
            
        # [AURA FIX] Inicialização correta das variáveis conforme o schema 3.0
        xp_total = int(dados.get("xp_total", 0))
        nivel_atual = int(dados.get("nivel", 1))
        nome_atleta = dados.get("nome", "Atleta Aura")
        cristais = int(dados.get("saldo_cristais", 0))
        
        # [AURA NEW] Novos campos exigidos pela App Store / RevenueCat
        plano = dados.get("plano", "free")
        status_assinatura = dados.get("status_assinatura", "inativo")
        vencimento = dados.get("data_vencimento", "")
        
        # Lógica de Barra de Progresso
        XP_BASE = 1000
        xp_prox = XP_BASE * nivel_atual
        xp_anterior = XP_BASE * (nivel_atual - 1)
        range_nivel = xp_prox - xp_anterior
        xp_no_nivel = xp_total - xp_anterior
        
        progresso = int((xp_no_nivel / range_nivel) * 100) if range_nivel > 0 else 0

        # Calcula seguro_ativo com segurança (campo pode estar ausente em usuários antigos)
        seguro_ativo = False
        try:
            seguro_val = dados.get("seguro_expira_em", "")
            if seguro_val:
                seguro_ativo = datetime.fromisoformat(str(seguro_val)) >= datetime.now()
        except Exception:
            seguro_ativo = False

        return jsonify({
            # Identidade
            "id":       current_user_id,
            "user_id":  current_user_id,
            "email":    dados.get("email", ""),
            "nome":     nome_atleta,
            "foto":     dados.get("foto_perfil", ""),
            # Progressão
            "xp_total":         xp_total,
            "moedas":           int(dados.get("moedas", xp_total)),
            "saldo_cristais":   cristais,
            "nivel":            nivel_atual,
            "barra_progresso":  max(0, min(100, progresso)),
            "xp_falta":         max(0, range_nivel - xp_no_nivel),
            "objetivo":         dados.get("objetivo", "Performance"),
            "ofensiva_atual":   int(dados.get("ofensiva_atual", 0)),
            "ultima_missao_data": dados.get("ultima_missao_data", ""),
            "seguro_expira_em": dados.get("seguro_expira_em", ""),
            "seguro_ativo":     seguro_ativo,
            # Regra de Ouro: controla o fluxo Login → Onboarding → Home
            "onboarding_completo": dados.get("onboarding_completo", False),
            # Assinatura
            "plano":              plano,
            "status_assinatura":  status_assinatura,
            "vencimento":         vencimento,
            "ofensiva_quebrada":  status_ofensiva.get("quebrada", False)
        })
    except Exception as e:
        logger.error(f"Erro status para o user {current_user_id}: {e}")
        return jsonify({"erro": "Falha ao sincronizar perfil"}), 500

# ===================================================
# 🍎 CONSULTA DE PLANOS (ROBUSTEZ HÍBRIDA)
# ===================================================

@api_bp.route('/usuario/plano/treino', methods=['GET'])
@token_required
def get_plano_treino(current_user_id):
    """Retorna o último treino híbrido gerado pela IA."""
    try:
        plano = ler_plano(current_user_id, "treino")
        if not plano:
            return jsonify({"mensagem": "Nenhum treino ativo. Peça ao Mestre para montar um!"}), 200
        return jsonify(plano)
    except Exception as e:
        logger.error(f"Erro ao ler treino: {e}")
        return jsonify({"erro": "Erro ao carregar treino"}), 500

@api_bp.route('/usuario/plano/dieta', methods=['GET'])
@token_required
def get_plano_dieta(current_user_id):
    """Retorna a última dieta estruturada gerada pela IA."""
    try:
        plano = ler_plano(current_user_id, "dieta")
        if not plano:
            return jsonify({"mensagem": "Nenhuma dieta ativa. Peça ao Mestre para montar uma!"}), 200
        return jsonify(plano)
    except Exception as e:
        logger.error(f"Erro ao ler dieta: {e}")
        return jsonify({"erro": "Erro ao carregar dieta"}), 500

@api_bp.route('/usuario/gastar_moedas', methods=['POST'])
@token_required
def endpoint_gastar_moedas(current_user_id):
    """Debita Moedas do saldo gastável sem afetar o XP histórico."""
    try:
        dados = request.get_json(force=True)
        quantidade = int(dados.get("quantidade", 0))
        resultado = gastar_moedas(current_user_id, quantidade)
        if resultado["sucesso"]:
            return jsonify(resultado)
        return jsonify(resultado), 400
    except Exception as e:
        logger.error(f"Erro ao gastar moedas para {current_user_id}: {e}")
        return jsonify({"erro": str(e)}), 500


@api_bp.route('/usuario/atualizar_biometria', methods=['POST'])
@token_required
def atualizar_biometria(current_user_id):
    """Atualiza dados físicos e origem da conta (Apple/Google) para App Store compliance."""
    try:
        dados = request.get_json(force=True)
        
        # [AURA FIX] Payload estendido para incluir metadados de autenticação
        update_payload = {
            "peso_kg": float(dados.get("peso", 70)),
            "altura_cm": float(dados.get("altura", 170)),
            "idade": int(dados.get("idade", 25)),
            "objetivo": dados.get("objetivo", "Performance")
        }
        
        # Se vierem dados de provedor_auth (Apple/Google) do Onboarding.jsx
        if dados.get("provedor_auth"):
            update_payload["provedor_auth"] = dados.get("provedor_auth")
        if dados.get("email"):
            update_payload["email"] = dados.get("email")

        sucesso = salvar_memoria(current_user_id, update_payload)
        return jsonify({"sucesso": sucesso})
    except Exception as e:
        logger.error(f"Erro ao atualizar biometria/auth para {current_user_id}: {e}")
        return jsonify({"erro": str(e)}), 500


@api_bp.route('/usuario/configurar_onboarding', methods=['POST'])
@token_required
def configurar_onboarding(current_user_id):
    """Salva todos os dados do Onboarding e marca onboarding_completo: true."""
    try:
        dados = request.get_json(force=True)

        update_payload = {
            "onboarding_completo": True,
        }

        if dados.get("nome"):
            update_payload["nome"] = str(dados["nome"]).strip()
        if dados.get("peso_kg") is not None:
            update_payload["peso_kg"] = float(dados["peso_kg"])
        if dados.get("altura_cm") is not None:
            update_payload["altura_cm"] = float(dados["altura_cm"])
        if dados.get("idade") is not None:
            update_payload["idade"] = int(dados["idade"])
        if dados.get("objetivo"):
            update_payload["objetivo"] = dados["objetivo"]
        if dados.get("esportes_favoritos"):
            update_payload["esportes_favoritos"] = dados["esportes_favoritos"]
        if dados.get("foto_perfil"):
            update_payload["foto_perfil"] = dados["foto_perfil"]

        sucesso = salvar_memoria(current_user_id, update_payload)
        logger.info(f"Onboarding concluído para {current_user_id}")
        return jsonify({"sucesso": sucesso, "onboarding_completo": True})
    except Exception as e:
        logger.error(f"Erro ao configurar onboarding para {current_user_id}: {e}")
        return jsonify({"erro": str(e)}), 500


# ===================================================
# ⚔️ CLÃS E RANKING (SOCIAL)
# ===================================================

@api_bp.route('/cla/ranking', methods=['GET'])
def get_ranking_cla():
    try:
        ranking = obter_ranking_global(limite=50)
        return jsonify({"ranking": ranking})
    except Exception as e:
        logger.error(f"Erro ao buscar ranking: {e}")
        return jsonify({"ranking": []})


@api_bp.route('/cla/criar', methods=['POST'])
@token_required
def criar_cla(current_user_id):
    """Cria um novo clã e define o criador como líder (owner). Gratuito."""
    try:
        dados = request.get_json(force=True)
        nome = str(dados.get("nome", "")).strip()
        if not nome:
            return jsonify({"erro": "Nome do clã é obrigatório"}), 400

        if mongo_db is None:
            return jsonify({"erro": "Banco de dados indisponível"}), 500

        # Garante unicidade do nome (case-insensitive)
        existente = mongo_db["Clas"].find_one({"nome": {"$regex": f"^{nome}$", "$options": "i"}})
        if existente:
            return jsonify({"erro": "Já existe um clã com esse nome"}), 409

        agora = datetime.now().isoformat()
        doc_cla = {
            "nome":               nome,
            "descricao":          str(dados.get("descricao", "")).strip(),
            "emblema":            str(dados.get("emblema", "shield")),
            "cor":                str(dados.get("cor", "#FFD700")),
            "tags":               list(dados.get("tags", [])),
            "lider_id":           current_user_id,
            "membros": [{
                "user_id":        current_user_id,
                "cargo":          "owner",
                "xp_contribuicao": 0,
                "joined_at":      agora
            }],
            "nivel":              1,
            "total_xp":           0,
            "missao_ativa_tipo":  (dados.get("tags") or ["Híbrido"])[0].split(" ")[0] if dados.get("tags") else "Híbrido",
            "missao_progresso":   0,
            "missao_meta":        50,
            "ativo":              True,
            "data_criacao":       agora,
            "updated_at":         agora
        }

        resultado = mongo_db["Clas"].insert_one(doc_cla)
        cla_id = str(resultado.inserted_id)

        # Atualiza o usuário com o ID do clã recém criado
        salvar_memoria(current_user_id, {"cla_atual_id": cla_id})

        doc_cla["id"] = cla_id
        doc_cla.pop("_id", None)
        logger.info(f"🏰 Clã '{nome}' criado por {current_user_id}")
        return jsonify(doc_cla), 201

    except Exception as e:
        logger.error(f"Erro ao criar clã para {current_user_id}: {e}")
        return jsonify({"erro": str(e)}), 500


@api_bp.route('/cla/listar', methods=['GET'])
def listar_clas():
    """Retorna todos os clãs ativos (público)."""
    try:
        if mongo_db is None:
            return jsonify([]), 200
        cursor = mongo_db["Clas"].find(
            {"ativo": True},
            {"_id": 1, "nome": 1, "descricao": 1, "emblema": 1, "cor": 1,
             "tags": 1, "nivel": 1, "total_xp": 1, "membros": 1}
        ).sort("total_xp", -1).limit(50)
        clans = []
        for d in cursor:
            d["id"] = str(d.pop("_id"))
            d["num_membros"] = len(d.get("membros", []))
            d.pop("membros", None)
            clans.append(d)
        return jsonify(clans), 200
    except Exception as e:
        logger.error(f"Erro ao listar clãs: {e}")
        return jsonify([]), 200


@api_bp.route('/cla/entrar', methods=['POST'])
@token_required
def entrar_cla(current_user_id):
    """Adiciona o usuário a um clã existente."""
    try:
        dados = request.get_json(force=True)
        cla_id = str(dados.get("cla_id", "")).strip()
        if not cla_id or not ObjectId.is_valid(cla_id):
            return jsonify({"erro": "ID do clã inválido"}), 400
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        cla = mongo_db["Clas"].find_one({"_id": ObjectId(cla_id), "ativo": True})
        if not cla:
            return jsonify({"erro": "Clã não encontrado"}), 404

        # Verifica se já é membro
        membros = cla.get("membros", [])
        if any(m["user_id"] == current_user_id for m in membros):
            return jsonify({"erro": "Você já é membro deste clã"}), 409

        agora = datetime.now().isoformat()
        mongo_db["Clas"].update_one(
            {"_id": ObjectId(cla_id)},
            {"$push": {"membros": {
                "user_id": current_user_id,
                "cargo": "member",
                "xp_contribuicao": 0,
                "joined_at": agora
            }}, "$set": {"updated_at": agora}}
        )
        salvar_memoria(current_user_id, {"cla_atual_id": cla_id})
        return jsonify({"sucesso": True}), 200
    except Exception as e:
        logger.error(f"Erro ao entrar no clã: {e}")
        return jsonify({"erro": str(e)}), 500


@api_bp.route('/cla/sair', methods=['POST'])
@token_required
def sair_cla(current_user_id):
    """Remove o usuário do clã."""
    try:
        dados = request.get_json(force=True)
        cla_id = str(dados.get("cla_id", "")).strip()
        if not cla_id or not ObjectId.is_valid(cla_id):
            return jsonify({"erro": "ID do clã inválido"}), 400
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        agora = datetime.now().isoformat()
        mongo_db["Clas"].update_one(
            {"_id": ObjectId(cla_id)},
            {"$pull": {"membros": {"user_id": current_user_id}},
             "$set": {"updated_at": agora}}
        )
        salvar_memoria(current_user_id, {"cla_atual_id": None})
        return jsonify({"sucesso": True}), 200
    except Exception as e:
        logger.error(f"Erro ao sair do clã: {e}")
        return jsonify({"erro": str(e)}), 500


@api_bp.route('/cla/chat', methods=['POST'])
@token_required
def enviar_chat_cla(current_user_id):
    """Salva uma mensagem no chat do clã."""
    try:
        dados = request.get_json(force=True)
        cla_id = str(dados.get("cla_id", "")).strip()
        message = str(dados.get("message", "")).strip()
        if not cla_id or not message:
            return jsonify({"erro": "cla_id e message são obrigatórios"}), 400
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        doc_msg = {
            "cla_id":    cla_id,
            "user_id":   current_user_id,
            "user_name": str(dados.get("user_name", "Membro")),
            "message":   message,
            "created_at": datetime.now().isoformat()
        }
        mongo_db["chat_cla"].insert_one(doc_msg)
        doc_msg["id"] = str(doc_msg.pop("_id"))
        return jsonify(doc_msg), 201
    except Exception as e:
        logger.error(f"Erro no chat do clã: {e}")
        return jsonify({"erro": str(e)}), 500


# Rotas com parâmetro de ID devem ficar APÓS as rotas fixas para evitar conflitos
@api_bp.route('/cla/<cla_id>', methods=['GET'])
@token_required
def get_cla(current_user_id, cla_id):
    """Retorna os dados de um clã pelo ID."""
    try:
        if mongo_db is None or not ObjectId.is_valid(cla_id):
            return jsonify({"erro": "ID inválido"}), 400
        cla = mongo_db["Clas"].find_one({"_id": ObjectId(cla_id)})
        if not cla:
            return jsonify({"erro": "Clã não encontrado"}), 404
        cla["id"] = str(cla.pop("_id"))
        return jsonify(cla), 200
    except Exception as e:
        logger.error(f"Erro ao buscar clã {cla_id}: {e}")
        return jsonify({"erro": str(e)}), 500


@api_bp.route('/cla/<cla_id>/membros', methods=['GET'])
@token_required
def get_membros_cla(current_user_id, cla_id):
    """Retorna os membros de um clã com dados básicos do usuário."""
    try:
        if mongo_db is None or not ObjectId.is_valid(cla_id):
            return jsonify([]), 200
        cla = mongo_db["Clas"].find_one({"_id": ObjectId(cla_id)}, {"membros": 1})
        if not cla:
            return jsonify([]), 200

        membros_raw = cla.get("membros", [])
        membros_out = []
        for m in membros_raw:
            uid = m.get("user_id", "")
            user_doc = {}
            if ObjectId.is_valid(uid):
                user_doc = mongo_db["usuarios"].find_one(
                    {"_id": ObjectId(uid)},
                    {"nome": 1, "nivel": 1, "foto_perfil": 1, "xp_total": 1}
                ) or {}
            cargo_key = m.get("cargo", "member")
            membros_out.append({
                "id":       uid,
                "nome":     user_doc.get("nome", "Atleta"),
                "nivel":    user_doc.get("nivel", 1),
                "foto":     user_doc.get("foto_perfil", ""),
                "xp":       m.get("xp_contribuicao", user_doc.get("xp_total", 0)),
                "roleKey":  cargo_key,
                "cargo":    {"owner": "Líder", "co-leader": "Co-Líder", "member": "Membro"}.get(cargo_key, "Membro"),
                "joined_at": m.get("joined_at", "")
            })
        # Ordena: líder primeiro, depois por XP
        membros_out.sort(key=lambda x: (0 if x["roleKey"] == "owner" else 1, -x["xp"]))
        return jsonify(membros_out), 200
    except Exception as e:
        logger.error(f"Erro ao buscar membros do clã {cla_id}: {e}")
        return jsonify([]), 200


@api_bp.route('/cla/<cla_id>/chat', methods=['GET'])
@token_required
def get_chat_cla(current_user_id, cla_id):
    """Retorna as últimas 100 mensagens do chat do clã."""
    try:
        if mongo_db is None:
            return jsonify([]), 200
        cursor = mongo_db["chat_cla"].find(
            {"cla_id": cla_id},
            {"_id": 1, "cla_id": 1, "user_id": 1, "user_name": 1, "message": 1, "created_at": 1}
        ).sort("created_at", 1).limit(100)
        msgs = []
        for m in cursor:
            m["id"] = str(m.pop("_id"))
            msgs.append(m)
        return jsonify(msgs), 200
    except Exception as e:
        logger.error(f"Erro ao buscar chat do clã {cla_id}: {e}")
        return jsonify([]), 200


# ===================================================
# 🧠 COMANDO DO MESTRE (IA HÍBRIDA)
# ===================================================

@api_bp.route('/comando', methods=['POST'])
@token_required
def comando(current_user_id):
    try:
        dados = request.get_json(force=True) 
        msg = dados.get('comando', '').strip()
        if not msg: return jsonify({"resposta": "O Mestre aguarda suas palavras..."})
        
        # O processar_comando no logic.py agora lida com os 10 exercícios e híbridos
        resposta = processar_comando(current_user_id, msg)
        return jsonify({"resposta": resposta})
    except Exception as e:
        logger.error(f"Erro no comando IA para {current_user_id}: {e}")
        return jsonify({"resposta": "⚠️ O Mestre está meditando em silêncio. Tente novamente."})

# ===================================================
# 🎮 MISSÕES E GAMIFICAÇÃO
# ===================================================

@api_bp.route('/missoes', methods=['GET'])
@token_required
def listar_missoes(current_user_id):
    return jsonify({"missoes": gerar_missoes_diarias(current_user_id)})

@api_bp.route('/concluir_missao', methods=['POST'])
@token_required
def concluir_missao(current_user_id):
    try:
        dados = request.get_json(force=True)
        missao_id = dados.get("id")
        missao_tipo = str(dados.get("tipo", "")).strip().lower()
        
        memoria = carregar_memoria(current_user_id)
        gamificacao = memoria.get("gamificacao", {})
        missoes = gamificacao.get("missoes_ativas", [])
        
        for m in missoes:
            id_match = missao_id and m.get("id") == missao_id
            tipo_match = missao_tipo and (
                str(m.get("categoria", "")).strip().lower() == missao_tipo
                or str(m.get("tipo", "")).strip().lower() == missao_tipo
                or str(m.get("titulo", "")).strip().lower() == missao_tipo
            )
            if (id_match or tipo_match) and not m.get("concluida"):
                m["concluida"] = True
                salvar_memoria(current_user_id, memoria)
                
                resultado = aplicar_xp(current_user_id, m.get("xp", 0))
                dados_ofensiva = registrar_conclusao_missao(current_user_id)
                return jsonify({
                    "sucesso": True, 
                    "xp_ganho": m.get("xp", 0),
                    "novo_nivel": resultado["novo_nivel"],
                    "novo_xp": resultado["novo_xp"],
                    "cristais_ganhos": resultado.get("cristais_ganhos", 0),
                    "ofensiva_atual": dados_ofensiva.get("ofensiva_atual", 0),
                    "seguro_expira_em": dados_ofensiva.get("seguro_expira_em", "")
                })
                
        return jsonify({"erro": "Missão inválida ou já concluída"}), 400
    except Exception as e:
        return jsonify({"erro": "Falha ao concluir missão"}), 500


@api_bp.route('/usuario/ofensiva/ativar_seguro', methods=['POST'])
@token_required
def ativar_seguro_streak(current_user_id):
    """
    Ativa o Seguro Ofensiva por 7 dias e debita cristais.
    Custo padrão: 200 cristais (item p2 do Mercado).
    """
    try:
        dados = request.get_json(force=True) or {}
        custo = int(dados.get("custo_cristais", 200))
        dias = int(dados.get("dias", 7))
        if custo <= 0:
            return jsonify({"erro": "Custo inválido"}), 400

        memoria = carregar_memoria(current_user_id)
        if not memoria:
            return jsonify({"erro": "Usuário não encontrado"}), 404

        saldo = int(memoria.get("saldo_cristais", 0))
        if saldo < custo:
            return jsonify({"erro": "Cristais insuficientes"}), 400

        memoria["saldo_cristais"] = saldo - custo
        if not salvar_memoria(current_user_id, memoria):
            return jsonify({"erro": "Falha ao debitar cristais"}), 500

        resultado = ativar_seguro_ofensiva(current_user_id, dias=dias)
        if not resultado.get("sucesso"):
            return jsonify({"erro": resultado.get("erro", "Falha ao ativar seguro")}), 500

        return jsonify({
            "sucesso": True,
            "saldo_cristais": saldo - custo,
            "ofensiva_atual": int(memoria.get("ofensiva_atual", 0)),
            "seguro_expira_em": resultado.get("seguro_expira_em", "")
        }), 200
    except Exception as e:
        logger.error(f"Erro ao ativar seguro ofensiva para {current_user_id}: {e}")
        return jsonify({"erro": "Falha ao ativar seguro de ofensiva"}), 500

# ===================================================
# ⚕️ BIOHACKING E SINCRONIZAÇÃO
# ===================================================

@api_bp.route('/sincronizar_dinamico', methods=['POST'])
@token_required
def sincronizar_dinamico(current_user_id):
    from data_sensores import obter_dados_fisiologicos
    novos_dados = obter_dados_fisiologicos(current_user_id)
    calcular_e_atualizar_equilibrio(current_user_id)
    return jsonify({"status": "Sincronizado", "dados": novos_dados})

@api_bp.route('/feedback', methods=['GET'])
@token_required
def feedback(current_user_id):
    return jsonify({"texto": gerar_feedback_emocional(current_user_id)})

# ===================================================
# 💳 PAGAMENTOS E WEBHOOKS (ASAAS + REVENUECAT)
# ===================================================

@api_bp.route('/webhook/revenuecat', methods=['POST'])
def webhook_revenuecat():
    """
    Webhook oficial para o RevenueCat. 
    Lida com o ciclo de vida das assinaturas Apple/Google.
    """
    try:
        dados = request.get_json(force=True)
        evento = dados.get("event", {})
        tipo = evento.get("type")
        app_user_id = evento.get("app_user_id") # Este é o aura_user_id do Base44

        if not app_user_id:
            return jsonify({"status": "ignorado", "motivo": "sem app_user_id"}), 200

        # Mapeamento de planos baseado no Product ID do RevenueCat
        product_id = evento.get("product_id", "").lower()
        novo_plano = "pro" if "pro" in product_id else "plus"

        # 1. Compra ou Renovação com sucesso
        if tipo in ["INITIAL_PURCHASE", "RENEWAL", "SUBSCRIBER_ALIAS"]:
            vencimento = (datetime.now() + timedelta(days=32)).isoformat()
            mongo_db["usuarios"].update_one(
                {"_id": ObjectId(app_user_id)},
                {"$set": {
                    "plano": novo_plano,
                    "status_assinatura": "ativo",
                    "data_vencimento": vencimento,
                    "updated_at": datetime.now().isoformat()
                }}
            )
            logger.info(f"💰 Assinatura {novo_plano} ATIVADA para o usuário {app_user_id}")

        # 2. Cancelamento ou Expiração
        elif tipo in ["CANCELLATION", "EXPIRATION"]:
            mongo_db["usuarios"].update_one(
                {"_id": ObjectId(app_user_id)},
                {"$set": {
                    "plano": "free",
                    "status_assinatura": "expirado",
                    "updated_at": datetime.now().isoformat()
                }}
            )
            logger.info(f"🚫 Assinatura FINALIZADA para o usuário {app_user_id}")

        return jsonify({"status": "recebido"}), 200
    except Exception as e:
        logger.error(f"Erro no Webhook RevenueCat: {e}")
        return jsonify({"erro": "Erro interno no processamento do webhook"}), 500

@api_bp.route('/pagamento/criar', methods=['POST'])
@token_required
def criar_pagamento(current_user_id):
    dados = request.get_json(force=True)
    dados['user_id'] = current_user_id
    return jsonify(criar_cobranca(dados))

# ===================================================
# 💳 PIX QR CODE — CONSULTA POR PAGAMENTO ASAAS
# ===================================================

@api_bp.route('/pagamento/pix/qrcode/<asaas_id>', methods=['GET'])
@token_required
def buscar_qrcode_pix(current_user_id, asaas_id):
    """Busca o QR Code PIX de um pagamento Asaas pelo seu ID."""
    try:
        headers = {
            "Content-Type": "application/json",
            "access_token": os.getenv("ASAAS_ACCESS_TOKEN", "")
        }
        resp = requests.get(
            f"https://www.asaas.com/api/v3/payments/{asaas_id}/pixQrCode",
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            return jsonify(resp.json()), 200
        logger.warning(f"Asaas QR Code não disponível para {asaas_id}: {resp.status_code}")
        return jsonify({"erro": "QR Code não disponível para este pagamento."}), 404
    except Exception as e:
        logger.error(f"Erro ao buscar QR Code Asaas: {e}")
        return jsonify({"erro": "Falha ao comunicar com o gateway."}), 500

# ===================================================
# 🏃 ATIVIDADES DO USUÁRIO
# ===================================================

@api_bp.route('/atividades', methods=['GET'])
@token_required
def listar_atividades(current_user_id):
    """Retorna o histórico de atividades registradas pelo usuário."""
    try:
        if mongo_db is None:
            return jsonify({"atividades": []}), 200
        cursor = mongo_db["atividades"].find(
            {"user_id": current_user_id},
            {"_id": 0}
        ).sort("data_atividade", -1).limit(100)
        return jsonify({"atividades": list(cursor)}), 200
    except Exception as e:
        logger.error(f"Erro ao listar atividades de {current_user_id}: {e}")
        return jsonify({"atividades": []}), 200

@api_bp.route('/registrar_atividade', methods=['POST'])
@token_required
def registrar_atividade(current_user_id):
    """Registra uma nova atividade e concede XP ao usuário."""
    try:
        dados = request.get_json(force=True)
        xp_atividade = int(dados.get("xp", 0))

        doc_atividade = {
            "user_id":         current_user_id,
            "titulo":          dados.get("titulo", "Atividade"),
            "tipo":            dados.get("tipo", "Treino"),
            "duracao":         dados.get("duracao", ""),
            "valor":           dados.get("valor", 0),
            "unidade":         dados.get("unidade", ""),
            "evidencia_url":   dados.get("evidencia_url", ""),
            "xp_concedido":    xp_atividade,
            "coins_ganhos":    xp_atividade,
            "cristais_ganhos": xp_atividade // 10,
            "data_atividade":  dados.get("data_atividade", datetime.now().isoformat()),
            "created_at":      datetime.now().isoformat()
        }

        if mongo_db is not None:
            mongo_db["atividades"].insert_one(doc_atividade)

        resultado_xp = {}
        if xp_atividade > 0:
            resultado_xp = aplicar_xp(current_user_id, xp_atividade)

        return jsonify({"sucesso": True, "dados_xp": resultado_xp}), 201
    except Exception as e:
        logger.error(f"Erro ao registrar atividade para {current_user_id}: {e}")
        return jsonify({"erro": str(e)}), 500

# ===================================================
# 🛍️ MARKETPLACE — PRODUTOS E PEDIDOS
# ===================================================

@api_bp.route('/produtos/listar', methods=['GET'])
def listar_produtos():
    """Lista todos os produtos disponíveis na loja física (público)."""
    try:
        if mongo_db is None:
            return jsonify([]), 200
        campos = {
            "_id": 1, "nome": 1, "marca": 1, "preco_aura": 1, "preco_original": 1,
            "custo_moedas": 1, "nivel_minimo": 1, "imagem_url": 1, "categoria": 1,
            "estoque": 1, "peso_kg": 1, "largura_cm": 1, "altura_cm": 1,
            "comprimento_cm": 1, "destaque": 1, "descricao": 1, "parceiro": 1,
            "tamanhos": 1, "cep_origem": 1
        }
        # Retorna todos os produtos cadastrados (não filtra por estoque para não
        # exibir tela vazia quando o campo ainda não foi populado nos documentos)
        docs = list(mongo_db["ProdutosLoja"].find({}, campos))
        for d in docs:
            d["id"] = str(d.pop("_id"))
        return jsonify(docs), 200
    except Exception as e:
        logger.error(f"Erro ao listar produtos: {e}")
        return jsonify([]), 200

@api_bp.route('/pedidos', methods=['GET'])
@token_required
def listar_pedidos(current_user_id):
    """Retorna o histórico de pedidos do usuário logado."""
    try:
        if mongo_db is None:
            return jsonify({"pedidos": []}), 200
        cursor = mongo_db["pedidos"].find(
            {"user_id": current_user_id},
            {"_id": 0}
        ).sort("created_at", -1).limit(50)
        return jsonify({"pedidos": list(cursor)}), 200
    except Exception as e:
        logger.error(f"Erro ao listar pedidos de {current_user_id}: {e}")
        return jsonify({"pedidos": []}), 200

# ===================================================
# 🚚 FRETE — COTAÇÃO MELHOR ENVIO
# ===================================================

# [AURA FIX 404] Rota mapeada via app.py
@api_bp.route('/frete/cotar', methods=['POST'])
@token_required
def rota_cotar_frete(current_user_id):
    """
    Endpoint ultra-robusto para cotação de frete no Melhor Envio.
    Garante processamento mesmo em caso de falha na busca por ID no Atlas.
    """
    try:
        dados = request.get_json(force=True)
        cep_destino = dados.get("cep")
        itens_checkout = dados.get("itens", [])

        if not cep_destino or not itens_checkout:
            return jsonify({"erro": "CEP de destino ou itens do carrinho ausentes."}), 400

        produtos_detalhes = []
        for item in itens_checkout:
            try:
                # [AURA FIX] Limpeza do ID do produto para consulta
                prod_id = str(item.get("id")).strip()
                prod_doc = None
                
                # Tenta buscar no banco, mas ignora falhas se o ID for inválido
                if ObjectId.is_valid(prod_id):
                    prod_doc = mongo_db["ProdutosLoja"].find_one({"_id": ObjectId(prod_id)})
                
                # [AURA ROBUST FALLBACK] Prioriza dados do Banco, mas usa o Payload como segurança
                item_traduzido = {
                    "id": prod_id,
                    "quantidade": int(item.get("quantidade") or 1),
                    "weight": float(prod_doc.get("peso_kg") if prod_doc else item.get("weight", 0.5)),
                    "width": float(prod_doc.get("largura_cm") if prod_doc else item.get("width", 15)),
                    "height": float(prod_doc.get("altura_cm") if prod_doc else item.get("height", 10)),
                    "length": float(prod_doc.get("comprimento_cm") if prod_doc else item.get("length", 20)),
                    "insurance_value": float(prod_doc.get("preco_aura") if prod_doc else item.get("insurance_value", 10))
                }
                produtos_detalhes.append(item_traduzido)
            except Exception as inner_e:
                logger.warning(f"Aviso ao processar item {item.get('id')}: {inner_e}")

        if not produtos_detalhes:
            return jsonify({"erro": "Nenhum produto válido encontrado para cotação."}), 404

        # Chama o motor logístico logic_frete com os campos normalizados
        opcoes = calcular_cotacao_frete(cep_destino, produtos_detalhes)
        return jsonify(opcoes)

    except Exception as e:
        logger.error(f"Erro crítico ao cotar frete para {current_user_id}: {e}")
        return jsonify({"erro": "Falha interna no motor de logística."}), 500

@api_bp.route('/webhook/asaas', methods=['POST'])
def webhook_asaas():
    """
    Webhook para receber confirmações de pagamento do Asaas.
    Rota pública — não usa @token_required (chamada feita pelo servidor Asaas).
    """
    try:
        dados = request.get_json(force=True)
        evento  = dados.get("event")
        payment = dados.get("payment", {})

        if evento in ["PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"]:
            payment_id = payment.get("id")
            if not payment_id:
                return jsonify({"status": "ignorado", "motivo": "sem payment_id"}), 200

            pedido = mongo_db["pedidos"].find_one({"asaas_id": payment_id})
            if pedido:
                mongo_db["pedidos"].update_one(
                    {"asaas_id": payment_id},
                    {"$set": {
                        "status": "PAGO",
                        "pago_em": datetime.now().isoformat(),
                        "updated_at": datetime.now().isoformat()
                    }}
                )
                logger.info(f"✅ Pedido {payment_id} atualizado para PAGO no Atlas.")
            else:
                logger.warning(f"⚠️ Webhook Asaas: pedido {payment_id} não encontrado no Atlas.")

        return jsonify({"status": "received"}), 200

    except Exception as e:
        logger.error(f"Erro no webhook Asaas: {e}")
        return jsonify({"erro": "Internal Error"}), 500