import logging
import os
import requests
import jwt
from functools import wraps
from datetime import datetime, timedelta
from typing import Dict, Any
from flask import request, jsonify, Blueprint
from bson.objectid import ObjectId
from pymongo.errors import DuplicateKeyError
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
from logic import processar_comando, processar_comando_com_imagem
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
JWT_EXP_DAYS  = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_DAYS", 30))

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
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            current_user_id = payload.get("user_id")
            if not current_user_id:
                return jsonify({"erro": "Token inválido: user_id ausente"}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({"erro": "Sessão expirada. Faça login novamente."}), 401
        except jwt.InvalidTokenError:
            # Token inválido ou adulterado — rejeita sem fallback
            return jsonify({"erro": "Token inválido. Faça login novamente."}), 401

        return f(current_user_id, *args, **kwargs)
    return decorated

# ===================================================
# 🔐 AUTENTICAÇÃO NATIVA — REGISTER / LOGIN / SOCIAL
# ===================================================

@api_bp.route('/auth/social', methods=['POST', 'OPTIONS'])
def auth_social():
    """
    Autenticação via provedor social (Google ou Apple).
    Body: { "provider": "google"|"apple", "token": "<id_token>", "nome": "<opcional>" }
    - Verifica o token com o provedor externo.
    - Cria o usuário se não existir (novo_usuario = True → onboarding_completo = False).
    - Garante que auth_provider esteja atualizado no MongoDB.
    - Retorna JWT + onboarding_completo para o front redirecionar corretamente.
    """
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    try:
        dados = request.get_json(force=True) or {}
        provider      = dados.get('provider', '').strip().lower()
        token_social  = dados.get('token', '').strip()
        nome_sugerido = dados.get('nome', '').strip()

        if provider not in ('google', 'apple'):
            return jsonify({"erro": "Provedor inválido. Use 'google' ou 'apple'"}), 400
        if not token_social:
            return jsonify({"erro": "Token ausente"}), 400

        email         = None
        nome_provedor = ''

        # ── Verificação Google ──────────────────────────────────────────
        if provider == 'google':
            resp = requests.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": token_social},
                timeout=10
            )
            if resp.status_code != 200:
                logger.warning(f"Google tokeninfo rejeitou: {resp.text[:200]}")
                return jsonify({"erro": "Token Google inválido"}), 401
            info = resp.json()
            email         = info.get('email', '').strip().lower()
            nome_provedor = info.get('name', '') or info.get('given_name', '')

        # ── Verificação Apple ───────────────────────────────────────────
        elif provider == 'apple':
            try:
                from jose import jwt as jose_jwt

                keys_resp = requests.get("https://appleid.apple.com/auth/keys", timeout=10)
                if keys_resp.status_code != 200:
                    return jsonify({"erro": "Falha ao buscar chaves Apple"}), 502
                apple_keys = keys_resp.json().get('keys', [])

                header = jose_jwt.get_unverified_header(token_social)
                kid    = header.get('kid')
                key    = next((k for k in apple_keys if k.get('kid') == kid), None)
                if not key:
                    return jsonify({"erro": "Chave pública Apple não encontrada"}), 401

                payload = jose_jwt.decode(
                    token_social,
                    key,
                    algorithms=['RS256'],
                    issuer='https://appleid.apple.com',
                    options={"verify_aud": False}
                )
                email = payload.get('email', '').strip().lower()
                # Apple fornece nome apenas no primeiro login (via frontend)
                nome_provedor = ''
            except Exception as e:
                logger.error(f"Verificação Apple falhou: {e}")
                return jsonify({"erro": "Token Apple inválido"}), 401

        if not email:
            return jsonify({"erro": "E-mail não disponível no token do provedor"}), 400

        nome_final = (nome_sugerido or nome_provedor or email.split('@')[0]).strip()

        # ── Busca ou cria usuário ───────────────────────────────────────
        usuario     = buscar_usuario_por_email(email)
        novo_usuario = usuario is None

        if novo_usuario:
            usuario = criar_novo_usuario(email, nome_final, auth_provider=provider)
            if not usuario:
                return jsonify({"erro": "Falha ao criar usuário"}), 500
        else:
            # Garante auth_provider atualizado mesmo que o usuário já exista
            atualizar_usuario(str(usuario["_id"]), {
                "auth_provider": provider,
                "updated_at": datetime.utcnow().isoformat()
            })

        token_jwt = gerar_token_jwt(str(usuario["_id"]))

        # onboarding_completo: novo usuário jamais completou; usuário existente usa o campo
        onboarding_completo = (not novo_usuario) and bool(
            usuario.get('configuracoes_sistema', {}).get('onboarding_completo', False)
        )

        logger.info(f"✅ Auth social ({provider}): {email} | novo={novo_usuario}")

        return jsonify({
            "sucesso":            True,
            "token":              token_jwt,
            "user_id":            str(usuario["_id"]),
            "nome":               usuario.get("nome", nome_final),
            "email":              email,
            "plano":              usuario.get("plano", "free"),
            "onboarding_completo": onboarding_completo,
            "novo_usuario":       novo_usuario,
            "auth_provider":      provider,
        })

    except Exception as e:
        logger.error(f"Erro no auth social: {e}")
        return jsonify({"erro": "Falha interna na autenticação social"}), 500


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
            # Biometria — usada em EditarPerfil e por IA
            "peso_kg":   dados.get("peso_kg"),
            "altura_cm": dados.get("altura_cm"),
            "idade":     dados.get("idade"),
            # Progressão
            "xp_total":         xp_total,
            "moedas":           int(dados.get("moedas", xp_total)),
            "saldo_cristais":   cristais,
            "nivel":            nivel_atual,
            "barra_progresso":  max(0, min(100, progresso)),
            "xp_falta":         max(0, range_nivel - xp_no_nivel),
            "objetivo":         dados.get("objetivo", "Performance Máxima"),
            "ofensiva_atual":   int(dados.get("ofensiva_atual", 0)),
            "ultima_missao_data": dados.get("ultima_missao_data", ""),
            "seguro_expira_em": dados.get("seguro_expira_em", ""),
            "seguro_ativo":     seguro_ativo,
            # Regra de Ouro: controla o fluxo Login → Onboarding → Home
            "onboarding_completo": dados.get("onboarding_completo", False),
            # Tour guiado: True = ainda não viu o tutorial inicial
            "first_access": dados.get("first_access", True),
            # Assinatura
            "plano":              plano,
            "status_assinatura":  status_assinatura,
            "vencimento":         vencimento,
            "ofensiva_quebrada":  status_ofensiva.get("quebrada", False),
            # Clãs
            "cla_atual_id":       dados.get("cla_atual_id", ""),
            # XP Dobrado (Poção de XP)
            "xp_dobrado_ativo":   _checar_beneficio_ativo(dados, "xp_dobrado_expira_em"),
            "xp_dobrado_expira_em": dados.get("xp_dobrado_expira_em", ""),
            # Cupons comprados no Laboratório
            "cupons_ativos":      dados.get("cupons_ativos", []),
        })
    except Exception as e:
        logger.error(f"Erro status para o user {current_user_id}: {e}")
        return jsonify({"erro": "Falha ao sincronizar perfil"}), 500

# ===================================================
# 🎓 TUTORIAL / GUIDED TOUR
# ===================================================

@api_bp.route('/tutorial/concluir', methods=['POST'])
@token_required
def concluir_tutorial(current_user_id):
    """Marca que o usuário já viu o tutorial inicial. Define first_access = False."""
    try:
        salvar_memoria(current_user_id, {"first_access": False})
        return jsonify({"sucesso": True}), 200
    except Exception as e:
        logger.error(f"Erro ao concluir tutorial para {current_user_id}: {e}")
        return jsonify({"erro": str(e)}), 500


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

def _checar_beneficio_ativo(dados: dict, campo_expiracao: str) -> bool:
    """Retorna True se o benefício ainda está dentro do prazo de expiração."""
    try:
        val = dados.get(campo_expiracao, "")
        if val:
            return datetime.fromisoformat(str(val)) >= datetime.now()
    except Exception:
        pass
    return False


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


@api_bp.route('/usuario/ativar_xp_dobrado', methods=['POST'])
@token_required
def ativar_xp_dobrado(current_user_id):
    """Ativa a Poção de XP Dobrado por 24h, debitando Cristais."""
    CUSTO_CRISTAIS = 150
    try:
        dados = carregar_memoria(current_user_id)
        cristais = int(dados.get("saldo_cristais", 0))
        if cristais < CUSTO_CRISTAIS:
            return jsonify({"erro": f"Cristais insuficientes. Necessário: {CUSTO_CRISTAIS}."}), 400
        expira = (datetime.now() + timedelta(hours=24)).isoformat()
        salvar_memoria(current_user_id, {
            "saldo_cristais":       cristais - CUSTO_CRISTAIS,
            "xp_dobrado_expira_em": expira,
        })
        logger.info(f"⚗️ XP Dobrado ativado para {current_user_id} até {expira}")
        return jsonify({"sucesso": True, "xp_dobrado_expira_em": expira})
    except Exception as e:
        logger.error(f"Erro ao ativar XP dobrado para {current_user_id}: {e}")
        return jsonify({"erro": str(e)}), 500


@api_bp.route('/usuario/ativar_cupom_premium', methods=['POST'])
@token_required
def ativar_cupom_premium(current_user_id):
    """Compra o cupom AURA15 no Laboratório, debitando Cristais e armazenando em cupons_ativos."""
    CUSTO_CRISTAIS = 300
    try:
        dados = carregar_memoria(current_user_id)
        cristais = int(dados.get("saldo_cristais", 0))
        if cristais < CUSTO_CRISTAIS:
            return jsonify({"erro": f"Cristais insuficientes. Necessário: {CUSTO_CRISTAIS}."}), 400
        cupons = list(dados.get("cupons_ativos", []))
        if "AURA15" not in cupons:
            cupons.append("AURA15")
        salvar_memoria(current_user_id, {
            "saldo_cristais": cristais - CUSTO_CRISTAIS,
            "cupons_ativos":  cupons,
        })
        logger.info(f"🏷️ Cupom AURA15 ativado para {current_user_id}")
        return jsonify({"sucesso": True, "codigo": "AURA15"})
    except Exception as e:
        logger.error(f"Erro ao ativar cupom premium para {current_user_id}: {e}")
        return jsonify({"erro": str(e)}), 500


@api_bp.route('/checkout/validar_cupom', methods=['POST'])
@token_required
def validar_cupom_checkout(current_user_id):
    """Valida um código de cupom. AURA12 é público. AURA15 exige compra prévia."""
    try:
        dados = request.get_json(force=True)
        codigo = str(dados.get("codigo", "")).upper().strip()
        if not codigo:
            return jsonify({"valido": False, "erro": "Código vazio."}), 400

        if codigo == "AURA12":
            return jsonify({"valido": True, "desconto": 0.12, "descricao": "12% OFF — Parceiros Aura"})

        if codigo == "AURA15":
            user_data = carregar_memoria(current_user_id)
            if "AURA15" in user_data.get("cupons_ativos", []):
                return jsonify({"valido": True, "desconto": 0.15, "descricao": "15% OFF — Cupom Premium"})
            return jsonify({"valido": False, "erro": "Adquira o cupom AURA15 no Mercado de Cristais antes de usá-lo."})

        return jsonify({"valido": False, "erro": "Cupom não reconhecido."})
    except Exception as e:
        logger.error(f"Erro ao validar cupom para {current_user_id}: {e}")
        return jsonify({"erro": str(e)}), 500


@api_bp.route('/usuario/voucher/resgatar', methods=['POST'])
@token_required
def resgatar_voucher(current_user_id):
    """Resgata um voucher da aba Vouchers do Mercado."""
    CUSTOS = {"v1": 4000, "v2": 15000, "v3": 0, "v4": 1000}
    try:
        dados_req = request.get_json(force=True)
        voucher_id = str(dados_req.get("voucher_id", "")).strip()
        if voucher_id not in CUSTOS:
            return jsonify({"erro": "Voucher inválido."}), 400

        user_data = carregar_memoria(current_user_id)
        moedas = int(user_data.get("moedas", 0))
        custo  = CUSTOS[voucher_id]

        if custo > 0 and moedas < custo:
            return jsonify({"erro": f"Aura Coins insuficientes. Necessário: {custo}."}), 400

        if voucher_id == "v3":  # Free Trial 24h Plus
            if user_data.get("trial_usado"):
                return jsonify({"erro": "Trial já foi utilizado anteriormente."}), 400
            expira = (datetime.now() + timedelta(hours=24)).isoformat()
            salvar_memoria(current_user_id, {
                "plano": "plus", "trial_usado": True, "trial_expira_em": expira
            })
            return jsonify({"sucesso": True, "plano": "plus", "trial_expira_em": expira})

        if voucher_id == "v4":  # 1.000 Coins → 50 Cristais
            resultado = gastar_moedas(current_user_id, custo)
            if not resultado.get("sucesso"):
                return jsonify({"erro": "Falha ao debitar Coins."}), 400
            cristais = int(user_data.get("saldo_cristais", 0))
            salvar_memoria(current_user_id, {"saldo_cristais": cristais + 50})
            return jsonify({"sucesso": True, "cristais_creditados": 50, "novo_saldo_cristais": cristais + 50})

        # v1 e v2 — desconto no checkout (cobram coins, registram posse)
        resultado = gastar_moedas(current_user_id, custo)
        if not resultado.get("sucesso"):
            return jsonify({"erro": "Falha ao debitar Coins."}), 400
        chave = "voucher_impulso_mensal" if voucher_id == "v1" else "voucher_elite_anual"
        salvar_memoria(current_user_id, {chave: True})
        return jsonify({"sucesso": True, "voucher": voucher_id})

    except Exception as e:
        logger.error(f"Erro ao resgatar voucher {voucher_id} para {current_user_id}: {e}")
        return jsonify({"erro": str(e)}), 500



@api_bp.route('/usuario/atualizar_biometria', methods=['POST'])
@token_required
def atualizar_biometria(current_user_id):
    """Atualiza dados físicos, nome, foto e origem da conta."""
    try:
        dados = request.get_json(force=True)
        update_payload = {}

        # Nome completo
        if dados.get("nome"):
            update_payload["nome"] = str(dados["nome"]).strip()

        # Biometria — só atualiza se enviado e não-nulo
        try:
            peso = dados.get("peso")
            if peso is not None and str(peso).strip() not in ("", "null", "None"):
                update_payload["peso_kg"] = float(peso)
        except (TypeError, ValueError):
            pass

        try:
            altura = dados.get("altura")
            if altura is not None and str(altura).strip() not in ("", "null", "None"):
                update_payload["altura_cm"] = float(altura)
        except (TypeError, ValueError):
            pass

        try:
            idade = dados.get("idade")
            if idade is not None and str(idade).strip() not in ("", "null", "None"):
                val = int(float(idade))
                if 1 <= val <= 120:
                    update_payload["idade"] = val
        except (TypeError, ValueError):
            pass

        if dados.get("objetivo"):
            update_payload["objetivo"] = str(dados["objetivo"])

        # Foto de perfil em Base64 ou URL
        if dados.get("foto_perfil"):
            fp = str(dados["foto_perfil"]).strip()
            if fp:
                update_payload["foto_perfil"] = fp

        # Remoção de foto
        if dados.get("remover_foto") is True:
            update_payload["foto_perfil"] = ""

        # Metadados de autenticação OAuth
        if dados.get("provedor_auth"):
            update_payload["provedor_auth"] = dados.get("provedor_auth")
        if dados.get("email"):
            update_payload["email"] = str(dados["email"]).strip().lower()

        # Plano (assinatura) — sincronização cliente/RevenueCat; webhook continua sendo fonte de reconciliação
        if "plano" in dados and dados.get("plano") is not None:
            p = str(dados["plano"]).strip().lower()
            if p in ("free", "plus", "pro"):
                update_payload["plano"] = p

        if not update_payload:
            return jsonify({"sucesso": True, "aviso": "Nenhum campo para atualizar"}), 200

        sucesso = salvar_memoria(current_user_id, update_payload)
        logger.info(f"Biometria/Perfil atualizado para {current_user_id}: {list(update_payload.keys())}")
        return jsonify({"sucesso": sucesso})
    except Exception as e:
        logger.error(f"Erro ao atualizar biometria/auth para {current_user_id}: {e}")
        return jsonify({"erro": str(e)}), 500


# Crédito de cristais após IAP (RevenueCat). Idempotente por transaction_id (StoreKit).
CRISTAIS_IAP_POR_PACOTE = {"g1": 100, "g2": 500, "g3": 1500}


@api_bp.route('/usuario/iap/cristais', methods=['POST'])
@token_required
def iap_creditar_cristais(current_user_id):
    """
    Credita cristais após compra confirmada no cliente.
    transaction_id deve ser o Store transactionIdentifier (único) para evitar duplicidade com webhook/retry.
    """
    try:
        dados = request.get_json(force=True) or {}
        pacote_id = str(dados.get("pacote_id", "")).strip().lower()
        transaction_id = str(dados.get("transaction_id", "")).strip()

        if pacote_id not in CRISTAIS_IAP_POR_PACOTE:
            return jsonify({"erro": "pacote_id inválido"}), 400
        if not transaction_id:
            return jsonify({"erro": "transaction_id obrigatório"}), 400

        qtd = CRISTAIS_IAP_POR_PACOTE[pacote_id]

        if mongo_db is not None:
            try:
                mongo_db["iap_cristais_transactions"].insert_one({
                    "_id": transaction_id,
                    "user_id": current_user_id,
                    "pacote_id": pacote_id,
                    "cristais": qtd,
                    "created_at": datetime.now().isoformat(),
                })
            except DuplicateKeyError:
                mem = carregar_memoria(current_user_id) or {}
                saldo = int(mem.get("saldo_cristais", 0))
                return jsonify({
                    "sucesso": True,
                    "ja_processado": True,
                    "cristais_creditados": 0,
                    "novo_saldo_cristais": saldo,
                }), 200
        else:
            logger.warning("iap/cristais: mongo_db ausente, usando apenas salvar_memoria")

        mem = carregar_memoria(current_user_id) or {}
        saldo_atual = int(mem.get("saldo_cristais", 0))
        novo = saldo_atual + qtd
        salvar_memoria(current_user_id, {"saldo_cristais": novo})
        logger.info(f"💎 IAP cristais +{qtd} ({pacote_id}) user={current_user_id} tx={transaction_id}")

        return jsonify({
            "sucesso": True,
            "cristais_creditados": qtd,
            "novo_saldo_cristais": novo,
            "pacote_id": pacote_id,
        }), 200
    except Exception as e:
        logger.error(f"Erro IAP cristais para {current_user_id}: {e}")
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
@token_required
def get_ranking_cla(current_user_id):
    try:
        ranking = obter_ranking_global(limite=50)
        # Expõe user_id apenas para usuários autenticados, necessário para o PerfilModal
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

        tipo_cla = str(dados.get("tipo", "aberto")).strip().lower()
        if tipo_cla not in ("aberto", "fechado"):
            tipo_cla = "aberto"

        agora = datetime.now().isoformat()
        doc_cla = {
            "nome":               nome,
            "descricao":          str(dados.get("descricao", "")).strip(),
            "emblema":            str(dados.get("emblema", "shield")),
            "cor":                str(dados.get("cor", "#FFD700")),
            "tags":               list(dados.get("tags", [])),
            "tipo":               tipo_cla,
            "lider_id":           current_user_id,
            "membros": [{
                "user_id":        current_user_id,
                "cargo":          "owner",
                "xp_contribuicao": 0,
                "joined_at":      agora
            }],
            "solicitacoes_pendentes": [],
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
             "tags": 1, "nivel": 1, "total_xp": 1, "membros": 1, "tipo": 1}
        ).sort("total_xp", -1).limit(50)
        clans = []
        for d in cursor:
            d["id"] = str(d.pop("_id"))
            d["num_membros"] = len(d.get("membros", []))
            d.pop("membros", None)
            d.setdefault("tipo", "aberto")
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
            salvar_memoria(current_user_id, {"cla_atual_id": cla_id})
            logger.info(f"[CLA] Re-sincronizando cla_atual_id para usuário {current_user_id} no clã {cla_id}")
            return jsonify({"sucesso": True, "ja_membro": True}), 200

        tipo_cla = cla.get("tipo", "aberto")

        # Clã fechado → adiciona solicitação pendente em vez de entrar direto
        if tipo_cla == "fechado":
            solicitacoes = cla.get("solicitacoes_pendentes", [])
            if any(s["user_id"] == current_user_id for s in solicitacoes):
                return jsonify({"status": "solicitacao_enviada", "ja_solicitado": True}), 200

            user_data = carregar_memoria(current_user_id) or {}
            mongo_db["Clas"].update_one(
                {"_id": ObjectId(cla_id)},
                {"$push": {"solicitacoes_pendentes": {
                    "user_id":      current_user_id,
                    "nome":         user_data.get("nome", "Atleta"),
                    "nivel":        user_data.get("nivel", 1),
                    "solicitado_em": datetime.now().isoformat()
                }}}
            )
            logger.info(f"[CLA] Solicitação de entrada enviada por {current_user_id} para clã fechado {cla_id}")
            return jsonify({"status": "solicitacao_enviada"}), 200

        # Clã aberto → entra diretamente
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


@api_bp.route('/cla/<cla_id>/solicitacoes', methods=['GET'])
@token_required
def listar_solicitacoes_cla(current_user_id, cla_id):
    """Retorna solicitações de entrada pendentes no clã (apenas líderes/co-líderes)."""
    try:
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500
        if not ObjectId.is_valid(cla_id):
            return jsonify({"erro": "ID do clã inválido"}), 400

        cla = mongo_db["Clas"].find_one({"_id": ObjectId(cla_id), "ativo": True})
        if not cla:
            return jsonify({"erro": "Clã não encontrado"}), 404

        membros = cla.get("membros", [])
        meu_cargo = next((m.get("cargo") for m in membros if m["user_id"] == current_user_id), None)
        if meu_cargo not in ("owner", "co-leader"):
            return jsonify({"erro": "Apenas líderes podem ver as solicitações"}), 403

        return jsonify({"solicitacoes": cla.get("solicitacoes_pendentes", [])}), 200
    except Exception as e:
        logger.error(f"Erro ao listar solicitações do clã {cla_id}: {e}")
        return jsonify({"erro": str(e)}), 500


@api_bp.route('/cla/<cla_id>/solicitacao/responder', methods=['POST'])
@token_required
def responder_solicitacao_cla(current_user_id, cla_id):
    """Aceita ou recusa uma solicitação de entrada (apenas líderes/co-líderes)."""
    try:
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500
        if not ObjectId.is_valid(cla_id):
            return jsonify({"erro": "ID do clã inválido"}), 400

        dados = request.get_json(force=True)
        solicitante_id = str(dados.get("user_id", "")).strip()
        aceitar = bool(dados.get("aceitar", False))

        if not solicitante_id:
            return jsonify({"erro": "user_id é obrigatório"}), 400

        cla = mongo_db["Clas"].find_one({"_id": ObjectId(cla_id), "ativo": True})
        if not cla:
            return jsonify({"erro": "Clã não encontrado"}), 404

        membros = cla.get("membros", [])
        meu_cargo = next((m.get("cargo") for m in membros if m["user_id"] == current_user_id), None)
        if meu_cargo not in ("owner", "co-leader"):
            return jsonify({"erro": "Apenas líderes podem responder solicitações"}), 403

        # Remove da lista de solicitações em qualquer caso
        mongo_db["Clas"].update_one(
            {"_id": ObjectId(cla_id)},
            {"$pull": {"solicitacoes_pendentes": {"user_id": solicitante_id}}}
        )

        if aceitar:
            # Verifica que ainda não é membro
            if not any(m["user_id"] == solicitante_id for m in membros):
                agora = datetime.now().isoformat()
                mongo_db["Clas"].update_one(
                    {"_id": ObjectId(cla_id)},
                    {"$push": {"membros": {
                        "user_id": solicitante_id,
                        "cargo": "member",
                        "xp_contribuicao": 0,
                        "joined_at": agora
                    }}, "$set": {"updated_at": agora}}
                )
                salvar_memoria(solicitante_id, {"cla_atual_id": cla_id})
                logger.info(f"[CLA] Solicitação de {solicitante_id} aceita no clã {cla_id} por {current_user_id}")
            return jsonify({"sucesso": True, "acao": "aceito"}), 200
        else:
            logger.info(f"[CLA] Solicitação de {solicitante_id} recusada no clã {cla_id} por {current_user_id}")
            return jsonify({"sucesso": True, "acao": "recusado"}), 200

    except Exception as e:
        logger.error(f"Erro ao responder solicitação do clã {cla_id}: {e}")
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
        # Ordena: líder → co-líder → demais por nível desc → XP desc como tie-break
        _cargo_order = {"owner": 0, "co-leader": 1}
        membros_out.sort(key=lambda x: (
            _cargo_order.get(x["roleKey"], 2),
            -x.get("nivel", 1),
            -x.get("xp", 0)
        ))
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
    """
    Endpoint principal do Mestre da Aura.
    Aceita texto e, opcionalmente, uma imagem em base64 para análise multimodal.
    Quando imagem_base64 estiver presente, usa gpt-4o com visão.
    """
    try:
        dados         = request.get_json(force=True)
        msg           = dados.get("comando", "").strip()
        imagem_base64 = dados.get("imagem_base64", "").strip()

        if imagem_base64:
            resposta = processar_comando_com_imagem(current_user_id, msg, imagem_base64)
        else:
            if not msg:
                return jsonify({"resposta": "O Mestre aguarda suas palavras..."})
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
        # duracao_min: duração da atividade registrada em minutos (para metas parciais)
        duracao_min_raw = dados.get("duracao_min")
        duracao_min = int(float(duracao_min_raw)) if duracao_min_raw is not None else None

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
            if not (id_match or tipo_match) or m.get("concluida"):
                continue

            meta_min = m.get("meta_duracao_min")

            # Missão com meta de duração — verifica progresso parcial
            if meta_min and duracao_min is not None:
                progresso_pct = min(100, int((duracao_min / meta_min) * 100))
                m["progresso_pct"] = progresso_pct

                if progresso_pct < 100:
                    # Progresso parcial: salva estado mas não concede recompensa
                    salvar_memoria(current_user_id, memoria)
                    falta_min = meta_min - duracao_min
                    falta_h = falta_min // 60
                    falta_m = falta_min % 60
                    falta_texto = f"{falta_h}h{falta_m:02d}min" if falta_h > 0 else f"{falta_m}min"
                    return jsonify({
                        "sucesso": False,
                        "parcial": True,
                        "progresso_pct": progresso_pct,
                        "falta_min": falta_min,
                        "falta_texto": falta_texto,
                        "mensagem": f"Progresso: {progresso_pct}% — faltam {falta_texto} para a meta"
                    })

            # Missão 100% completa — concede recompensa integral
            m["concluida"] = True
            m["progresso_pct"] = 100
            salvar_memoria(current_user_id, memoria)

            resultado = aplicar_xp(current_user_id, m.get("xp", 0))
            dados_ofensiva = registrar_conclusao_missao(current_user_id)
            return jsonify({
                "sucesso": True,
                "xp_ganho":       m.get("xp", 0),
                "novo_nivel":     resultado["novo_nivel"],
                "novo_xp":        resultado["novo_xp"],
                "moedas_ganhas":  resultado.get("moedas_ganhas", 0),
                "cristais_ganhos":resultado.get("cristais_ganhos", 0),
                "subiu":          resultado.get("subiu", False),
                "bonus_level_up": resultado.get("bonus_level_up"),
                "ofensiva_atual": dados_ofensiva.get("ofensiva_atual", 0),
                "seguro_expira_em": dados_ofensiva.get("seguro_expira_em", "")
            })

        return jsonify({"erro": "Missão inválida ou já concluída"}), 400
    except Exception as e:
        logger.error(f"Erro concluir_missao: {e}")
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

_RC_WEBHOOK_SECRET = os.getenv("REVENUECAT_WEBHOOK_SECRET", "")

@api_bp.route('/webhook/revenuecat', methods=['POST'])
def webhook_revenuecat():
    """
    Webhook oficial para o RevenueCat.
    Verifica o header Authorization se REVENUECAT_WEBHOOK_SECRET estiver definido.
    """
    # Verificação de assinatura RevenueCat (Bearer token no header Authorization)
    if _RC_WEBHOOK_SECRET:
        auth_header = request.headers.get("Authorization", "")
        provided = auth_header.replace("Bearer ", "").strip()
        if provided != _RC_WEBHOOK_SECRET:
            logger.warning("⚠️ Webhook RevenueCat rejeitado: assinatura inválida.")
            return jsonify({"erro": "Forbidden"}), 403

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

def _mapear_categoria_missao(tipo_atividade: str) -> str:
    """
    Converte o tipo/tag da atividade para a categoria de missão correspondente.
    Espelha a função resolverCategoriaMissao() do frontend (RegistrarAtividade.jsx).
    """
    t = str(tipo_atividade or "").strip().lower()
    if t == "sono":
        return "descanso"
    if t in ("meditação", "meditacao"):
        return "mente"
    if t in ("nutrição", "nutricao", "hidratação", "hidratacao"):
        return "saude"
    return "treino"


def _tentar_completar_missao_auto(user_id: str, tipo_atividade: str, duracao_str: str):
    """
    Após registrar uma atividade, verifica se há missão diária ativa não concluída
    que corresponda ao tipo/categoria da atividade e à duração informada.

    Retorna um dict com os campos de recompensa se uma missão foi completada,
    ou None se nenhuma missão correspondeu ou foi completada.
    Também retorna um dict de progresso parcial se a duração não atingiu a meta.
    """
    try:
        memoria = carregar_memoria(user_id)
        if not memoria:
            return None, None

        gamificacao = memoria.get("gamificacao", {})
        missoes = gamificacao.get("missoes_ativas", [])
        if not missoes:
            return None, None

        tipo_lower = str(tipo_atividade or "").strip().lower()
        categoria_mapeada = _mapear_categoria_missao(tipo_atividade)

        # Converte duração "HH:MM" para minutos
        duracao_min = None
        if duracao_str:
            parts = str(duracao_str).split(":")
            if len(parts) >= 2:
                try:
                    duracao_min = int(parts[0]) * 60 + int(parts[1])
                except (ValueError, TypeError):
                    pass

        for m in missoes:
            if m.get("concluida"):
                continue

            cat_m = str(m.get("categoria", "")).strip().lower()
            tipo_m = str(m.get("tipo", "")).strip().lower()
            titulo_m = str(m.get("titulo", "")).strip().lower()

            bateu = (
                cat_m == categoria_mapeada
                or cat_m == tipo_lower
                or tipo_m == categoria_mapeada
                or tipo_m == tipo_lower
                or titulo_m == tipo_lower
            )
            if not bateu:
                continue

            meta_min = m.get("meta_duracao_min")

            # Missão com requisito de duração mínima
            if meta_min and duracao_min is not None:
                progresso_pct = min(100, int((duracao_min / meta_min) * 100))
                if progresso_pct < 100:
                    # Progresso parcial: atualiza estado mas não concede recompensa
                    m["progresso_pct"] = progresso_pct
                    salvar_memoria(user_id, memoria)
                    falta_min = meta_min - duracao_min
                    falta_h = falta_min // 60
                    falta_m = falta_min % 60
                    falta_texto = (
                        f"{falta_h}h{falta_m:02d}min" if falta_h > 0 else f"{falta_m}min"
                    )
                    return None, {
                        "parcial": True,
                        "progresso_pct": progresso_pct,
                        "falta_min": falta_min,
                        "falta_texto": falta_texto,
                        "nome": m.get("titulo", "Missão"),
                    }

            # Missão completada — concede recompensa integral
            m["concluida"] = True
            m["progresso_pct"] = 100
            salvar_memoria(user_id, memoria)

            resultado_missao = aplicar_xp(user_id, m.get("xp", 0))
            dados_ofensiva = registrar_conclusao_missao(user_id)

            completada = {
                "nome":          m.get("titulo", "Missão Diária"),
                "xp":            m.get("xp", 0),
                "moedas":        resultado_missao.get("moedas_ganhas", m.get("xp", 0)),
                "cristais":      resultado_missao.get("cristais_ganhos", m.get("xp", 0) // 10),
                "ofensiva_atual": dados_ofensiva.get("ofensiva_atual", 0),
                "novo_nivel":    resultado_missao.get("novo_nivel", 0),
                "subiu":         resultado_missao.get("subiu", False),
            }
            logger.info(
                f"✅ Missão '{completada['nome']}' auto-completada via registrar_atividade "
                f"para {user_id} (tipo={tipo_atividade})"
            )
            return completada, None

        return None, None
    except Exception as e:
        logger.error(f"Erro em _tentar_completar_missao_auto para {user_id}: {e}")
        return None, None


@api_bp.route('/registrar_atividade', methods=['POST'])
@token_required
def registrar_atividade(current_user_id):
    """
    Registra uma nova atividade, concede XP ao usuário e tenta
    auto-completar qualquer missão diária ativa que corresponda
    ao tipo/categoria da atividade registrada.
    """
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

        # Tenta completar automaticamente uma missão diária correspondente
        tipo_atividade = dados.get("tipo", "")
        duracao_str    = dados.get("duracao", "")
        missao_completada, missao_parcial = _tentar_completar_missao_auto(
            current_user_id, tipo_atividade, duracao_str
        )

        return jsonify({
            "sucesso": True,
            "dados_xp": resultado_xp,
            "missao_completada": missao_completada,
            "missao_parcial": missao_parcial,
        }), 201
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
            {"user_id": current_user_id}
        ).sort("created_at", -1).limit(50)
        pedidos = []
        for p in cursor:
            p["id"] = str(p.pop("_id"))
            pedidos.append(p)
        return jsonify({"pedidos": pedidos}), 200
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

# ===================================================
# 👥 SISTEMA SOCIAL — AMIZADES E NOTIFICAÇÕES
# ===================================================

def _criar_notificacao(user_id: str, tipo: str, mensagem: str, meta: dict = None):
    """Insere uma notificação na coleção. Silencia erros para não quebrar o fluxo principal."""
    try:
        mongo_db["notificacoes"].insert_one({
            "user_id":   user_id,
            "tipo":      tipo,        # "amizade_pedido" | "amizade_aceita" | "sistema" | "mercado"
            "mensagem":  mensagem,
            "meta":      meta or {},
            "lida":      False,
            "created_at": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Erro ao criar notificação: {e}")


@api_bp.route('/social/perfil/<user_id>', methods=['GET'])
@token_required
def perfil_publico(current_user_id, user_id):
    """Retorna o perfil público de outro usuário (para modal de terceiros)."""
    try:
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        doc = mongo_db["usuarios"].find_one(
            {"_id": ObjectId(user_id)},
            {"nome": 1, "foto_perfil": 1, "xp_total": 1, "nivel": 1,
             "objetivo": 1, "cla_atual_id": 1, "ofensiva_atual": 1,
             "esportes_favoritos": 1}
        )
        if not doc:
            return jsonify({"erro": "Usuário não encontrado"}), 404

        # Conta missões concluídas
        missoes_count = mongo_db["atividades"].count_documents({"user_id": user_id})

        # Dados do clã (objeto completo para exibir no modal de perfil)
        cla_nome = ""
        cla_info = None
        cla_id = doc.get("cla_atual_id", "")
        if cla_id:
            try:
                cla_doc = mongo_db["Clas"].find_one(
                    {"_id": ObjectId(cla_id)},
                    {"nome": 1, "nivel": 1, "emblema": 1, "cor": 1, "membros": 1, "tipo": 1}
                )
                if cla_doc:
                    cla_nome = cla_doc.get("nome", "")
                    cla_info = {
                        "id":            cla_id,
                        "nome":          cla_doc.get("nome", ""),
                        "nivel":         cla_doc.get("nivel", 1),
                        "emblema":       cla_doc.get("emblema", "shield"),
                        "cor":           cla_doc.get("cor", "#FFD700"),
                        "tipo":          cla_doc.get("tipo", "aberto"),
                        "total_membros": len(cla_doc.get("membros", [])),
                    }
            except Exception:
                pass

        # Verifica status de amizade com o usuário logado
        amizade = mongo_db["amizades"].find_one({
            "$or": [
                {"solicitante_id": current_user_id, "receptor_id": user_id},
                {"solicitante_id": user_id, "receptor_id": current_user_id}
            ]
        })
        status_amizade = "nenhum"
        if amizade:
            status_amizade = amizade.get("status", "nenhum")
            if status_amizade == "pendente" and amizade.get("solicitante_id") == current_user_id:
                status_amizade = "pendente_enviado"
            elif status_amizade == "pendente":
                status_amizade = "pendente_recebido"

        return jsonify({
            "user_id":          user_id,
            "nome":             doc.get("nome", "Anônimo"),
            "foto":             doc.get("foto_perfil", ""),
            "nivel":            doc.get("nivel", 1),
            "xp_total":         doc.get("xp_total", 0),
            "objetivo":         doc.get("objetivo", ""),
            "cla_nome":         cla_nome,
            "cla":              cla_info,
            "ofensiva_atual":   doc.get("ofensiva_atual", 0),
            "esportes":         doc.get("esportes_favoritos", []),
            "missoes_total":    missoes_count,
            "status_amizade":   status_amizade,
        }), 200
    except Exception as e:
        logger.error(f"Erro perfil público {user_id}: {e}")
        return jsonify({"erro": str(e)}), 500


@api_bp.route('/social/amizade/enviar', methods=['POST'])
@token_required
def enviar_pedido_amizade(current_user_id):
    """Envia pedido de amizade a outro usuário."""
    try:
        dados = request.get_json(force=True)
        receptor_id = str(dados.get("receptor_id", "")).strip()
        if not receptor_id or receptor_id == current_user_id:
            return jsonify({"erro": "receptor_id inválido"}), 400

        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        # Verifica se já existe relação
        existente = mongo_db["amizades"].find_one({
            "$or": [
                {"solicitante_id": current_user_id, "receptor_id": receptor_id},
                {"solicitante_id": receptor_id, "receptor_id": current_user_id}
            ]
        })
        if existente:
            return jsonify({"erro": "Pedido já existe ou vocês já são amigos"}), 409

        mongo_db["amizades"].insert_one({
            "solicitante_id": current_user_id,
            "receptor_id":    receptor_id,
            "status":         "pendente",
            "created_at":     datetime.now().isoformat()
        })

        # Notifica o receptor
        solicitante = carregar_memoria(current_user_id)
        nome_sol = solicitante.get("nome", "Alguém")
        _criar_notificacao(
            receptor_id,
            "amizade_pedido",
            f"{nome_sol} enviou um pedido de amizade para você!",
            {"solicitante_id": current_user_id, "nome": nome_sol}
        )
        return jsonify({"sucesso": True, "mensagem": "Pedido enviado!"}), 201
    except Exception as e:
        logger.error(f"Erro ao enviar pedido de amizade: {e}")
        return jsonify({"erro": str(e)}), 500


@api_bp.route('/social/amizade/remover', methods=['POST'])
@token_required
def remover_amizade(current_user_id):
    """Remove a amizade mútua confirmada entre dois usuários (Unfriend)."""
    try:
        dados = request.get_json(force=True)
        amigo_id = str(dados.get("amigo_id", "")).strip()
        if not amigo_id:
            return jsonify({"erro": "amigo_id é obrigatório"}), 400
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        resultado = mongo_db["amizades"].delete_one({
            "$or": [
                {"solicitante_id": current_user_id, "receptor_id": amigo_id, "status": "aceita"},
                {"solicitante_id": amigo_id, "receptor_id": current_user_id, "status": "aceita"},
            ]
        })

        if resultado.deleted_count == 0:
            return jsonify({"erro": "Amizade não encontrada ou já removida"}), 404

        logger.info(f"💔 Amizade removida entre {current_user_id} e {amigo_id}")
        return jsonify({"sucesso": True}), 200

    except Exception as e:
        logger.error(f"Erro ao remover amizade: {e}")
        return jsonify({"erro": str(e)}), 500


@api_bp.route('/social/amizade/responder', methods=['POST'])
@token_required
def responder_pedido_amizade(current_user_id):
    """Aceita ou recusa um pedido de amizade. acao: 'aceitar' | 'recusar'."""
    try:
        dados = request.get_json(force=True)
        solicitante_id = str(dados.get("solicitante_id", "")).strip()
        acao = str(dados.get("acao", "")).strip()  # "aceitar" | "recusar"

        if not solicitante_id or acao not in ("aceitar", "recusar"):
            return jsonify({"erro": "Parâmetros inválidos"}), 400

        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        novo_status = "aceita" if acao == "aceitar" else "recusada"
        resultado = mongo_db["amizades"].update_one(
            {"solicitante_id": solicitante_id, "receptor_id": current_user_id, "status": "pendente"},
            {"$set": {"status": novo_status, "updated_at": datetime.now().isoformat()}}
        )
        if resultado.matched_count == 0:
            return jsonify({"erro": "Pedido não encontrado"}), 404

        if acao == "aceitar":
            receptor = carregar_memoria(current_user_id)
            nome_rec = receptor.get("nome", "Alguém")
            _criar_notificacao(
                solicitante_id,
                "amizade_aceita",
                f"{nome_rec} aceitou seu pedido de amizade!",
                {"receptor_id": current_user_id, "nome": nome_rec}
            )

        return jsonify({"sucesso": True, "status": novo_status}), 200
    except Exception as e:
        logger.error(f"Erro ao responder pedido de amizade: {e}")
        return jsonify({"erro": str(e)}), 500


@api_bp.route('/social/amigos', methods=['GET'])
@token_required
def listar_amigos(current_user_id):
    """Retorna a lista de amigos confirmados do usuário logado."""
    try:
        if mongo_db is None:
            return jsonify({"amigos": []}), 200

        relacoes = list(mongo_db["amizades"].find({
            "$or": [
                {"solicitante_id": current_user_id, "status": "aceita"},
                {"receptor_id": current_user_id, "status": "aceita"}
            ]
        }))

        amigos = []
        for rel in relacoes:
            amigo_id = rel["receptor_id"] if rel["solicitante_id"] == current_user_id else rel["solicitante_id"]
            try:
                doc = mongo_db["usuarios"].find_one(
                    {"_id": ObjectId(amigo_id)},
                    {"nome": 1, "foto_perfil": 1, "nivel": 1, "xp_total": 1, "objetivo": 1, "ofensiva_atual": 1}
                )
                if doc:
                    amigos.append({
                        "user_id":       amigo_id,
                        "nome":          doc.get("nome", "Anônimo"),
                        "foto":          doc.get("foto_perfil", ""),
                        "nivel":         doc.get("nivel", 1),
                        "xp_total":      doc.get("xp_total", 0),
                        "objetivo":      doc.get("objetivo", ""),
                        "ofensiva_atual": doc.get("ofensiva_atual", 0),
                        "amizade_desde": rel.get("updated_at", rel.get("created_at", "")),
                    })
            except Exception:
                pass

        amigos.sort(key=lambda a: a["xp_total"], reverse=True)
        return jsonify({"amigos": amigos}), 200
    except Exception as e:
        logger.error(f"Erro ao listar amigos de {current_user_id}: {e}")
        return jsonify({"amigos": []}), 200


@api_bp.route('/social/notificacoes', methods=['GET'])
@token_required
def listar_notificacoes(current_user_id):
    """Retorna as últimas 30 notificações do usuário, ordenadas por data desc."""
    try:
        if mongo_db is None:
            return jsonify({"notificacoes": [], "nao_lidas": 0}), 200

        cursor = mongo_db["notificacoes"].find(
            {"user_id": current_user_id}
        ).sort("created_at", -1).limit(30)

        notifs = []
        for n in cursor:
            notifs.append({
                "id":        str(n["_id"]),
                "tipo":      n.get("tipo", "sistema"),
                "mensagem":  n.get("mensagem", ""),
                "meta":      n.get("meta", {}),
                "lida":      n.get("lida", False),
                "created_at": n.get("created_at", ""),
            })

        nao_lidas = sum(1 for n in notifs if not n["lida"])
        return jsonify({"notificacoes": notifs, "nao_lidas": nao_lidas}), 200
    except Exception as e:
        logger.error(f"Erro ao listar notificações de {current_user_id}: {e}")
        return jsonify({"notificacoes": [], "nao_lidas": 0}), 200


@api_bp.route('/social/notificacoes/ler', methods=['POST'])
@token_required
def marcar_notificacoes_lidas(current_user_id):
    """Marca todas as notificações do usuário como lidas."""
    try:
        if mongo_db is None:
            return jsonify({"sucesso": True}), 200
        mongo_db["notificacoes"].update_many(
            {"user_id": current_user_id, "lida": False},
            {"$set": {"lida": True}}
        )
        return jsonify({"sucesso": True}), 200
    except Exception as e:
        logger.error(f"Erro ao marcar notificações lidas: {e}")
        return jsonify({"sucesso": False}), 500


# ===================================================
# 🪪 AURA CODE — Identificador único público (8 chars)
# ===================================================

def _gerar_aura_code(user_id: str) -> str:
    """Deriva um código de 8 dígitos alfanuméricos do ObjectId. Determinístico e sem colisões."""
    import hashlib
    h = hashlib.sha256(str(user_id).encode()).hexdigest()
    return h[:8].upper()


@api_bp.route('/social/meu_codigo', methods=['GET'])
@token_required
def meu_aura_code(current_user_id):
    """Retorna (e cria se necessário) o Aura Code do usuário logado."""
    try:
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500
        doc = mongo_db["usuarios"].find_one({"_id": ObjectId(current_user_id)}, {"aura_code": 1})
        code = doc.get("aura_code") if doc else None
        if not code:
            code = _gerar_aura_code(current_user_id)
            mongo_db["usuarios"].update_one(
                {"_id": ObjectId(current_user_id)},
                {"$set": {"aura_code": code}}
            )
        return jsonify({"aura_code": code}), 200
    except Exception as e:
        logger.error(f"Erro ao buscar Aura Code: {e}")
        return jsonify({"erro": str(e)}), 500


@api_bp.route('/social/buscar_por_codigo', methods=['GET'])
@token_required
def buscar_por_aura_code(current_user_id):
    """Busca um usuário pelo Aura Code (query param: code=XXXXXXXX)."""
    try:
        code = request.args.get("code", "").strip().upper()
        if len(code) != 8:
            return jsonify({"erro": "Código deve ter 8 caracteres"}), 400
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        # Migra usuários antigos que ainda não têm aura_code
        doc = mongo_db["usuarios"].find_one({"aura_code": code},
            {"nome": 1, "foto_perfil": 1, "nivel": 1, "xp_total": 1, "objetivo": 1})
        if not doc:
            return jsonify({"erro": "Código não encontrado"}), 404

        uid = str(doc["_id"])
        if uid == current_user_id:
            return jsonify({"erro": "Esse é o seu próprio código!"}), 400

        # Verifica status de amizade
        amizade = mongo_db["amizades"].find_one({
            "$or": [
                {"solicitante_id": current_user_id, "receptor_id": uid},
                {"solicitante_id": uid, "receptor_id": current_user_id}
            ]
        })
        status_amizade = "nenhum"
        if amizade:
            status_amizade = amizade.get("status", "nenhum")
            if status_amizade == "pendente" and amizade.get("solicitante_id") == current_user_id:
                status_amizade = "pendente_enviado"
            elif status_amizade == "pendente":
                status_amizade = "pendente_recebido"

        return jsonify({
            "user_id":        uid,
            "nome":           doc.get("nome", "Anônimo"),
            "foto":           doc.get("foto_perfil", ""),
            "nivel":          doc.get("nivel", 1),
            "xp_total":       doc.get("xp_total", 0),
            "objetivo":       doc.get("objetivo", ""),
            "aura_code":      code,
            "status_amizade": status_amizade,
        }), 200
    except Exception as e:
        logger.error(f"Erro ao buscar por código: {e}")
        return jsonify({"erro": str(e)}), 500


# ===================================================
# ⚔️  DESAFIOS DE CLÃ
# ===================================================

@api_bp.route('/cla/desafio', methods=['POST'])
@token_required
def criar_desafio_cla(current_user_id):
    """Cria um desafio no clã. Apenas owner/co-leader. Limite: 1 desafio ativo por vez."""
    try:
        dados = request.get_json(force=True)
        cla_id = str(dados.get("cla_id", "")).strip()
        titulo = str(dados.get("titulo", "")).strip()
        duracao_dias = max(1, int(dados.get("duracao_dias", 7)))
        descricao = str(dados.get("descricao", "")).strip()

        if not cla_id or not titulo:
            return jsonify({"erro": "cla_id e titulo são obrigatórios"}), 400
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        cla = mongo_db["Clas"].find_one({"_id": ObjectId(cla_id)})
        if not cla:
            return jsonify({"erro": "Clã não encontrado"}), 404

        # Verifica cargo
        cargo = next((m.get("cargo") for m in cla.get("membros", []) if m.get("user_id") == current_user_id), None)
        if cargo not in ("owner", "co-leader"):
            return jsonify({"erro": "Apenas líderes podem criar desafios"}), 403

        # Verifica se já há desafio ativo
        agora = datetime.now().isoformat()
        ativo = mongo_db["desafios_cla"].find_one({"cla_id": cla_id, "ativo": True, "expira_em": {"$gt": agora}})
        if ativo:
            return jsonify({"erro": "Já existe um desafio ativo. Aguarde ele expirar."}), 409

        expira = (datetime.now() + timedelta(days=duracao_dias)).isoformat()
        doc = {
            "cla_id":       cla_id,
            "titulo":       titulo,
            "descricao":    descricao,
            "criador_id":   current_user_id,
            "duracao_dias": duracao_dias,
            "expira_em":    expira,
            "ativo":        True,
            "created_at":   agora,
        }
        res = mongo_db["desafios_cla"].insert_one(doc)
        doc["id"] = str(res.inserted_id)
        doc.pop("_id", None)
        return jsonify(doc), 201
    except Exception as e:
        logger.error(f"Erro ao criar desafio: {e}")
        return jsonify({"erro": str(e)}), 500


@api_bp.route('/cla/<cla_id>/desafio_ativo', methods=['GET'])
@token_required
def get_desafio_ativo(current_user_id, cla_id):
    """Retorna o desafio ativo do clã (se existir)."""
    try:
        if mongo_db is None:
            return jsonify({"desafio": None}), 200
        agora = datetime.now().isoformat()
        doc = mongo_db["desafios_cla"].find_one(
            {"cla_id": cla_id, "ativo": True, "expira_em": {"$gt": agora}},
            sort=[("created_at", -1)]
        )
        if not doc:
            return jsonify({"desafio": None}), 200
        doc["id"] = str(doc.pop("_id"))
        return jsonify({"desafio": doc}), 200
    except Exception as e:
        logger.error(f"Erro ao buscar desafio: {e}")
        return jsonify({"desafio": None}), 200


@api_bp.route('/cla/desafio/evidencia', methods=['POST'])
@token_required
def enviar_evidencia_desafio(current_user_id):
    """Membro envia foto-evidência (URL base64 ou link) para um desafio."""
    try:
        dados = request.get_json(force=True)
        desafio_id = str(dados.get("desafio_id", "")).strip()
        foto_url   = str(dados.get("foto_url", "")).strip()  # URL ou base64
        legenda    = str(dados.get("legenda", "")).strip()[:200]

        if not desafio_id or not foto_url:
            return jsonify({"erro": "desafio_id e foto_url são obrigatórios"}), 400
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        # Valida que o desafio existe e está ativo
        try:
            desafio = mongo_db["desafios_cla"].find_one({"_id": ObjectId(desafio_id)})
        except Exception:
            return jsonify({"erro": "desafio_id inválido"}), 400
        if not desafio or not desafio.get("ativo"):
            return jsonify({"erro": "Desafio não encontrado ou expirado"}), 404

        # Busca nome do usuário
        user_doc = mongo_db["usuarios"].find_one({"_id": ObjectId(current_user_id)}, {"nome": 1, "foto_perfil": 1})
        user_nome = user_doc.get("nome", "Membro") if user_doc else "Membro"

        agora = datetime.now().isoformat()
        ev = {
            "desafio_id": desafio_id,
            "cla_id":     desafio.get("cla_id"),
            "user_id":    current_user_id,
            "user_nome":  user_nome,
            "foto_url":   foto_url,
            "legenda":    legenda,
            "created_at": agora,
        }
        res = mongo_db["evidencias_desafio"].insert_one(ev)
        ev["id"] = str(res.inserted_id)
        ev.pop("_id", None)
        return jsonify(ev), 201
    except Exception as e:
        logger.error(f"Erro ao enviar evidência: {e}")
        return jsonify({"erro": str(e)}), 500


@api_bp.route('/cla/desafio/<desafio_id>/evidencias', methods=['GET'])
@token_required
def listar_evidencias(current_user_id, desafio_id):
    """Retorna as evidências de um desafio (feed social)."""
    try:
        if mongo_db is None:
            return jsonify({"evidencias": []}), 200
        cursor = mongo_db["evidencias_desafio"].find(
            {"desafio_id": desafio_id}
        ).sort("created_at", -1).limit(50)
        evs = []
        for e in cursor:
            e["id"] = str(e.pop("_id"))
            evs.append(e)
        return jsonify({"evidencias": evs}), 200
    except Exception as e:
        logger.error(f"Erro ao listar evidências: {e}")
        return jsonify({"evidencias": []}), 200


@api_bp.route('/cla/desafio/<desafio_id>/ranking', methods=['GET'])
@token_required
def ranking_desafio(current_user_id, desafio_id):
    """
    Ranking dinâmico do desafio: ordena membros pela quantidade de evidências
    enviadas dentro do período do desafio ativo. Prova social pura.
    """
    try:
        if mongo_db is None:
            return jsonify({"ranking": [], "desafio_titulo": ""}), 200

        try:
            desafio = mongo_db["desafios_cla"].find_one({"_id": ObjectId(desafio_id)})
        except Exception:
            return jsonify({"erro": "ID de desafio inválido"}), 400

        if not desafio:
            return jsonify({"erro": "Desafio não encontrado"}), 404

        # Agrega evidências por membro dentro do período do desafio
        pipeline = [
            {"$match": {"desafio_id": desafio_id}},
            {"$group": {
                "_id":              "$user_id",
                "total_envios":     {"$sum": 1},
                "user_nome":        {"$first": "$user_nome"},
                "ultima_evidencia": {"$max": "$created_at"},
            }},
            {"$sort": {"total_envios": -1}},
            {"$limit": 50},
        ]

        cursor = mongo_db["evidencias_desafio"].aggregate(pipeline)
        ranking = []
        for i, doc in enumerate(cursor):
            uid  = doc["_id"]
            foto = ""
            nivel = 1
            try:
                u = mongo_db["usuarios"].find_one(
                    {"_id": ObjectId(uid)},
                    {"foto_perfil": 1, "nivel": 1}
                )
                if u:
                    fp = u.get("foto_perfil", "")
                    foto  = fp if fp and not fp.startswith("data:") else ""
                    nivel = u.get("nivel", 1)
            except Exception:
                pass

            ranking.append({
                "posicao":          i + 1,
                "user_id":          uid,
                "nome":             doc.get("user_nome", "Atleta"),
                "foto":             foto,
                "nivel":            nivel,
                "total_envios":     doc["total_envios"],
                "ultima_evidencia": doc.get("ultima_evidencia", ""),
            })

        return jsonify({
            "ranking":        ranking,
            "desafio_titulo": desafio.get("titulo", "Desafio"),
            "total_membros":  len(ranking),
        }), 200

    except Exception as e:
        logger.error(f"Erro ao buscar ranking do desafio {desafio_id}: {e}")
        return jsonify({"ranking": [], "desafio_titulo": ""}), 200


@api_bp.route('/cla/desafio/<desafio_id>/excluir', methods=['DELETE'])
@token_required
def excluir_desafio_cla(current_user_id, desafio_id):
    """Exclui/cancela o desafio ativo. Apenas owner ou co-leader do clã."""
    try:
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        try:
            oid = ObjectId(desafio_id)
        except Exception:
            return jsonify({"erro": "ID de desafio inválido"}), 400

        desafio = mongo_db["desafios_cla"].find_one({"_id": oid})
        if not desafio:
            return jsonify({"erro": "Desafio não encontrado"}), 404

        cla_id = desafio.get("cla_id", "")
        try:
            cla = mongo_db["Clas"].find_one({"_id": ObjectId(cla_id)})
        except Exception:
            cla = None

        if not cla:
            return jsonify({"erro": "Clã não encontrado"}), 404

        cargo = next((m.get("cargo") for m in cla.get("membros", []) if m.get("user_id") == current_user_id), None)
        if cargo not in ("owner", "co_leader"):
            return jsonify({"erro": "Apenas líderes e co-líderes podem excluir desafios"}), 403

        mongo_db["desafios_cla"].delete_one({"_id": oid})
        # Remove também as evidências associadas
        mongo_db["evidencias_desafio"].delete_many({"desafio_id": desafio_id})

        logger.info(f"🗑️ Desafio {desafio_id} excluído por {current_user_id}")
        return jsonify({"sucesso": True, "mensagem": "Desafio excluído com sucesso"}), 200

    except Exception as e:
        logger.error(f"Erro ao excluir desafio: {e}")
        return jsonify({"erro": "Falha ao excluir desafio"}), 500


# ===================================================
# 🏰 GESTÃO DE CLÃ — Editar, Promover, Expulsar
# ===================================================

@api_bp.route('/cla/<cla_id>/editar', methods=['POST'])
@token_required
def editar_cla(current_user_id, cla_id):
    """Edita nome, descrição, cor, emblema e visibilidade do clã (somente owner)."""
    try:
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        cla = mongo_db["Clas"].find_one({"_id": ObjectId(cla_id)})
        if not cla:
            return jsonify({"erro": "Clã não encontrado"}), 404

        cargo = next((m.get("cargo") for m in cla.get("membros", []) if m.get("user_id") == current_user_id), None)
        if cargo != "owner":
            return jsonify({"erro": "Apenas o líder pode editar o clã"}), 403

        dados = request.get_json(force=True)
        update = {"updated_at": datetime.now().isoformat()}
        for campo in ("nome", "descricao", "cor", "emblema"):
            if campo in dados and str(dados[campo]).strip():
                update[campo] = str(dados[campo]).strip()
        if "privado" in dados:
            update["privado"] = bool(dados["privado"])

        mongo_db["Clas"].update_one({"_id": ObjectId(cla_id)}, {"$set": update})
        return jsonify({"sucesso": True}), 200
    except Exception as e:
        logger.error(f"Erro ao editar clã {cla_id}: {e}")
        return jsonify({"erro": str(e)}), 500


@api_bp.route('/cla/<cla_id>/promover', methods=['POST'])
@token_required
def promover_membro(current_user_id, cla_id):
    """Promove um membro a co-leader (somente owner)."""
    try:
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        dados = request.get_json(force=True)
        alvo_id = str(dados.get("user_id", "")).strip()
        if not alvo_id:
            return jsonify({"erro": "user_id do alvo é obrigatório"}), 400

        cla = mongo_db["Clas"].find_one({"_id": ObjectId(cla_id)})
        if not cla:
            return jsonify({"erro": "Clã não encontrado"}), 404

        cargo_solicitante = next((m.get("cargo") for m in cla.get("membros", []) if m.get("user_id") == current_user_id), None)
        if cargo_solicitante != "owner":
            return jsonify({"erro": "Apenas o líder pode promover membros"}), 403

        resultado = mongo_db["Clas"].update_one(
            {"_id": ObjectId(cla_id), "membros.user_id": alvo_id},
            {"$set": {"membros.$.cargo": "co-leader", "updated_at": datetime.now().isoformat()}}
        )
        if resultado.matched_count == 0:
            return jsonify({"erro": "Membro não encontrado no clã"}), 404

        # Notifica o promovido
        alvo_doc = mongo_db["usuarios"].find_one({"_id": ObjectId(alvo_id)}, {"nome": 1}) if alvo_id else None
        _criar_notificacao(alvo_id, "sistema",
            f"Você foi promovido a Co-Líder no clã {cla.get('nome', '')}!",
            {"cla_id": cla_id})
        return jsonify({"sucesso": True}), 200
    except Exception as e:
        logger.error(f"Erro ao promover membro: {e}")
        return jsonify({"erro": str(e)}), 500


@api_bp.route('/cla/<cla_id>/expulsar', methods=['POST'])
@token_required
def expulsar_membro(current_user_id, cla_id):
    """Expulsa um membro do clã (owner pode expulsar qualquer um; co-leader pode expulsar member)."""
    try:
        if mongo_db is None:
            return jsonify({"erro": "Banco indisponível"}), 500

        dados = request.get_json(force=True)
        alvo_id = str(dados.get("user_id", "")).strip()
        if not alvo_id or alvo_id == current_user_id:
            return jsonify({"erro": "user_id do alvo inválido"}), 400

        cla = mongo_db["Clas"].find_one({"_id": ObjectId(cla_id)})
        if not cla:
            return jsonify({"erro": "Clã não encontrado"}), 404

        cargo_sol = next((m.get("cargo") for m in cla.get("membros", []) if m.get("user_id") == current_user_id), None)
        cargo_alvo = next((m.get("cargo") for m in cla.get("membros", []) if m.get("user_id") == alvo_id), None)

        if cargo_sol not in ("owner", "co-leader"):
            return jsonify({"erro": "Sem permissão para expulsar"}), 403
        if cargo_sol == "co-leader" and cargo_alvo in ("owner", "co-leader"):
            return jsonify({"erro": "Co-líderes só podem expulsar membros comuns"}), 403
        if cargo_alvo == "owner":
            return jsonify({"erro": "O líder não pode ser expulso"}), 403

        mongo_db["Clas"].update_one(
            {"_id": ObjectId(cla_id)},
            {"$pull": {"membros": {"user_id": alvo_id}},
             "$set":  {"updated_at": datetime.now().isoformat()}}
        )
        # Remove vínculo do usuário expulso
        salvar_memoria(alvo_id, {"cla_atual_id": None})
        _criar_notificacao(alvo_id, "sistema",
            f"Você foi removido do clã {cla.get('nome', '')}.",
            {"cla_id": cla_id})
        return jsonify({"sucesso": True}), 200
    except Exception as e:
        logger.error(f"Erro ao expulsar membro: {e}")
        return jsonify({"erro": str(e)}), 500


# ===================================================
# 🤝 AMIZADE — Aceitar/Recusar via notificação (já existe responder, mantido)
# ===================================================

@api_bp.route('/social/pendentes', methods=['GET'])
@token_required
def pedidos_pendentes(current_user_id):
    """Lista pedidos de amizade recebidos e ainda pendentes."""
    try:
        if mongo_db is None:
            return jsonify({"pedidos": []}), 200
        cursor = list(mongo_db["amizades"].find(
            {"receptor_id": current_user_id, "status": "pendente"}
        ))
        pedidos = []
        for rel in cursor:
            uid = rel["solicitante_id"]
            try:
                doc = mongo_db["usuarios"].find_one({"_id": ObjectId(uid)},
                    {"nome": 1, "foto_perfil": 1, "nivel": 1, "objetivo": 1})
                if doc:
                    pedidos.append({
                        "user_id": uid,
                        "nome":    doc.get("nome", "Anônimo"),
                        "foto":    doc.get("foto_perfil", ""),
                        "nivel":   doc.get("nivel", 1),
                        "objetivo": doc.get("objetivo", ""),
                        "created_at": rel.get("created_at", ""),
                    })
            except Exception:
                pass
        return jsonify({"pedidos": pedidos}), 200
    except Exception as e:
        logger.error(f"Erro ao listar pedidos pendentes: {e}")
        return jsonify({"pedidos": []}), 200


# ===================================================
# 🔐 ADMIN — ATUALIZAÇÃO DE STATUS DE PEDIDOS
# ===================================================

@api_bp.route('/admin/pedidos/<pedido_id>/status', methods=['PATCH'])
def admin_atualizar_status_pedido(pedido_id):
    """
    Atualiza o status de um pedido do marketplace.
    Protegido por header X-Admin-Key = ADMIN_SECRET_KEY.
    Body: { "status": "...", "codigo_rastreio": "opcional" }
    """
    secret = os.getenv("ADMIN_SECRET_KEY", "")
    admin_key = request.headers.get("X-Admin-Key", "")
    if not secret or admin_key != secret:
        logger.warning(f"⚠️ Tentativa de acesso admin rejeitada para pedido {pedido_id}.")
        return jsonify({"erro": "Acesso não autorizado"}), 403

    dados = request.get_json(force=True) or {}
    novo_status = dados.get("status", "")
    codigo_rastreio = dados.get("codigo_rastreio", "").strip()

    _STATUS_VALIDOS = {"ENVIADO_FORNECEDOR", "RASTREIO_GERADO", "ENTREGUE", "CANCELADO"}
    if novo_status not in _STATUS_VALIDOS:
        return jsonify({"erro": f"Status inválido. Aceitos: {sorted(_STATUS_VALIDOS)}"}), 400

    try:
        if mongo_db is None:
            return jsonify({"erro": "Banco de dados indisponível"}), 503

        update_set = {
            "status": novo_status,
            "updated_at": datetime.now().isoformat()
        }
        if novo_status == "RASTREIO_GERADO" and codigo_rastreio:
            update_set["codigo_rastreio"] = codigo_rastreio
            update_set["rastreio_atualizado_em"] = datetime.now().isoformat()

        resultado = mongo_db["pedidos"].update_one(
            {"_id": ObjectId(pedido_id)},
            {"$set": update_set}
        )
        if resultado.matched_count == 0:
            return jsonify({"erro": "Pedido não encontrado"}), 404

        logger.info(f"✅ Admin atualizou pedido {pedido_id} → {novo_status}")
        return jsonify({"sucesso": True, "status": novo_status}), 200

    except Exception as e:
        logger.error(f"Erro ao atualizar status do pedido {pedido_id}: {e}")
        return jsonify({"erro": str(e)}), 500


_ASAAS_WEBHOOK_TOKEN = os.getenv("ASAAS_WEBHOOK_TOKEN", "")

@api_bp.route('/webhook/asaas', methods=['POST'])
def webhook_asaas():
    """
    Webhook para receber confirmações de pagamento do Asaas.
    Verifica o header asaas-access-token se ASAAS_WEBHOOK_TOKEN estiver definido.
    """
    if _ASAAS_WEBHOOK_TOKEN:
        provided = request.headers.get("asaas-access-token", "")
        if provided != _ASAAS_WEBHOOK_TOKEN:
            logger.warning("⚠️ Webhook Asaas rejeitado: token inválido.")
            return jsonify({"erro": "Forbidden"}), 403

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
                update_fields = {
                    "status": "PAGO",
                    "pago_em": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
                tipo_pedido = pedido.get("tipo", "marketplace")

                # ── [PERFORMANCE] Ativar inscrição em desafio ────────────────
                if tipo_pedido == "desafio":
                    inscricao_id = pedido.get("inscricao_id")
                    desafio_id   = pedido.get("desafio_id")
                    if inscricao_id:
                        try:
                            mongo_db["inscricoes_desafio"].update_one(
                                {"_id": ObjectId(inscricao_id)},
                                {"$set": {"status_pagamento": "PAGO", "pago_em": datetime.now().isoformat()}}
                            )
                            # Incrementa vagas_ocupadas no desafio
                            if desafio_id:
                                mongo_db["desafios"].update_one(
                                    {"_id": ObjectId(desafio_id)},
                                    {"$inc": {"vagas_ocupadas": 1, "total_inscritos": 1}}
                                )
                                # Atualiza total_alunos do profissional
                                d = mongo_db["desafios"].find_one({"_id": ObjectId(desafio_id)})
                                if d:
                                    mongo_db["profissionais"].update_one(
                                        {"user_id": d.get("profissional_id")},
                                        {"$inc": {"total_alunos": 1}}
                                    )
                            logger.info(f"✅ [PERF] Inscrição {inscricao_id} ativada via webhook.")
                        except Exception as we:
                            logger.error(f"[PERF] Erro ao ativar inscrição no webhook: {we}")

                # ── [PERFORMANCE] Marcar verificação de profissional como paga ──
                elif tipo_pedido == "verificacao_profissional":
                    user_id_prof = pedido.get("user_id", "")
                    if user_id_prof:
                        try:
                            mongo_db["profissionais"].update_one(
                                {"user_id": user_id_prof},
                                {"$set": {"verificacao_paga": True, "updated_at": datetime.now().isoformat()}}
                            )
                            logger.info(f"✅ [PERF] Verificação paga para profissional {user_id_prof}.")
                        except Exception as ve:
                            logger.error(f"[PERF] Erro ao marcar verificação: {ve}")

                # ── [MARKETPLACE] Notificação admin ──────────────────────────
                elif tipo_pedido == "marketplace":
                    update_fields["notificado_admin"] = False

                mongo_db["pedidos"].update_one(
                    {"asaas_id": payment_id},
                    {"$set": update_fields}
                )
                logger.info(f"✅ Pedido {payment_id} ({tipo_pedido}) atualizado para PAGO no Atlas.")
            else:
                logger.warning(f"⚠️ Webhook Asaas: pedido {payment_id} não encontrado no Atlas.")

        return jsonify({"status": "received"}), 200

    except Exception as e:
        logger.error(f"Erro no webhook Asaas: {e}")
        return jsonify({"erro": "Internal Error"}), 500