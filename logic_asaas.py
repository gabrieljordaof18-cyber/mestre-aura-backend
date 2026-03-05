import os
import requests
import re
import logging
from datetime import datetime, timedelta

# [AURA FIX] Importação explícita do mongo_db para garantir sincronização com o Render
from data_manager import mongo_db

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AURA_FINANCEIRO")

# URL de Produção do Asaas
ASAAS_URL = "https://www.asaas.com/api/v3"

def get_headers():
    token = os.getenv("ASAAS_ACCESS_TOKEN")
    if not token:
        logger.error("❌ ASAAS_ACCESS_TOKEN não configurado no .env do Render")
    
    return {
        "Content-Type": "application/json",
        "access_token": token or ""
    }

# ======================================================
# 🛠️ UTILITÁRIOS (SANITIZAÇÃO)
# ======================================================

def _limpar_apenas_numeros(texto: str) -> str:
    """Remove tudo que não for dígito (para CPF e Telefone)."""
    if not texto: return ""
    return re.sub(r'\D', '', str(texto))

# ======================================================
# 👤 GESTÃO DE CLIENTES (ASAAS)
# ======================================================

def criar_ou_buscar_cliente(usuario_dados: dict) -> str:
    """
    Verifica se o cliente já existe no Asaas pelo CPF ou Email.
    Se não, cria um novo. Retorna o customer_id (cus_xxx).
    """
    headers = get_headers()
    
    # [AURA FIX] Sanitização rigorosa para evitar que o Asaas recuse o payload
    cpf_limpo = _limpar_apenas_numeros(usuario_dados.get('cpf', ''))
    email = usuario_dados.get('email', '').strip().lower()
    
    # 1. Tenta buscar por CPF (Mais seguro para evitar duplicidade)
    if cpf_limpo:
        try:
            busca = requests.get(f"{ASAAS_URL}/customers?cpfCnpj={cpf_limpo}", headers=headers)
            if busca.status_code == 200:
                dados = busca.json().get('data', [])
                if dados:
                    logger.info(f"✅ Cliente Asaas encontrado via CPF: {dados[0]['id']}")
                    return dados[0]['id']
        except Exception as e:
            logger.error(f"Erro ao buscar cliente Asaas por CPF: {e}")

    # 2. Se falhar ou não tiver CPF, tenta buscar por Email
    if email:
        try:
            busca = requests.get(f"{ASAAS_URL}/customers?email={email}", headers=headers)
            if busca.status_code == 200:
                dados = busca.json().get('data', [])
                if dados:
                    logger.info(f"✅ Cliente Asaas encontrado via Email: {dados[0]['id']}")
                    return dados[0]['id']
        except Exception as e:
            logger.error(f"Erro ao buscar cliente por email: {e}")
    
    # 3. Se não existir em nenhum lugar, cria um novo no Asaas
    payload = {
        "name": usuario_dados.get('nome', 'Atleta Aura'),
        "cpfCnpj": cpf_limpo,
        "email": email,
        "mobilePhone": _limpar_apenas_numeros(usuario_dados.get('telefone', '')),
        "notificationDisabled": False
    }
    
    try:
        criacao = requests.post(f"{ASAAS_URL}/customers", json=payload, headers=headers)
        
        if criacao.status_code == 200:
            novo_id = criacao.json()['id']
            logger.info(f"🆕 Novo cliente Asaas criado com sucesso: {novo_id}")
            return novo_id
        else:
            logger.error(f"❌ Erro Asaas (Criar Cliente): {criacao.text}")
            return None
    except Exception as e:
        logger.error(f"❌ Erro de conexão Asaas ao criar cliente: {e}")
        return None

# ======================================================
# 💳 GERAÇÃO DE COBRANÇA & PERSISTÊNCIA
# ======================================================

def criar_cobranca(dados_pagamento: dict) -> dict:
    """
    Gera a cobrança (PIX ou Cartão) e SALVA NO MONGODB.
    """
    headers = get_headers()
    
    # [AURA FIX] Limpeza do user_id para garantir busca correta no MongoDB
    user_id = str(dados_pagamento.get('user_id', '')).strip()
    if not user_id:
        logger.warning("⚠️ Tentativa de criar cobrança sem user_id vinculado.")

    # 1. Identificar ou Criar Cliente no Asaas
    usuario_info = dados_pagamento.get('usuario', {})
    customer_id = criar_ou_buscar_cliente(usuario_info)
    
    if not customer_id:
        return {"erro": "Falha ao registrar dados no gateway de pagamento. Verifique CPF/Email."}

    # 2. Configurar Detalhes da Cobrança
    metodo = str(dados_pagamento.get('metodo', 'pix')).lower()
    billing_type = "PIX" if metodo == 'pix' else "CREDIT_CARD"
    
    try:
        valor_float = float(dados_pagamento.get('valor', 0))
    except ValueError:
        return {"erro": "Valor de pagamento inválido."}
    
    # Ajuste: Vencimento para o dia seguinte para evitar erros de processamento noturno
    vencimento = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    payload = {
        "customer": customer_id,
        "billingType": billing_type,
        "value": valor_float,
        "dueDate": vencimento,
        "description": f"Aura OS: {dados_pagamento.get('descricao', 'Produtos Performance')}",
        "externalReference": user_id # Vinculamos o ID do MongoDB para o Webhook futuro
    }

    # 3. Enviar solicitação para o Asaas
    try:
        response = requests.post(f"{ASAAS_URL}/payments", json=payload, headers=headers)
        
        if response.status_code != 200:
            logger.error(f"❌ Resposta Asaas Erro ({response.status_code}): {response.text}")
            erro_msg = response.json().get('errors', [{'description': 'Erro na API do Asaas'}])[0]['description']
            return {"erro": f"Pagamento recusado: {erro_msg}"}
        
        data_asaas = response.json()
        payment_id = data_asaas['id']

        # 4. PERSISTÊNCIA (Sincronização com MongoDB Atlas)
        # [AURA FIX] Comparação explícita com None para evitar erro de bool() no PyMongo
        if mongo_db is not None and user_id:
            try:
                novo_pedido = {
                    "user_id": user_id,
                    "asaas_id": payment_id,
                    "customer_id": customer_id,
                    "valor": valor_float,
                    "metodo": metodo,
                    "status": "PENDING",
                    "descricao": dados_pagamento.get('descricao', 'Pedido Aura'),
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
                # Salvamos na coleção 'pedidos' para controle financeiro
                mongo_db["pedidos"].insert_one(novo_pedido)
                logger.info(f"📦 Pedido {payment_id} registrado no MongoDB para o usuário {user_id}")
            except Exception as mongo_err:
                logger.error(f"⚠️ Erro ao persistir pedido no MongoDB: {mongo_err}")
                # Não retornamos erro aqui para não travar o pagamento se o banco falhar momentaneamente

        # 5. Formatação de Retorno para o Frontend (Base44)
        if billing_type == "PIX":
            # Para PIX, precisamos buscar o QR Code em um endpoint separado do Asaas
            qr_response = requests.get(f"{ASAAS_URL}/payments/{payment_id}/pixQrCode", headers=headers)
            if qr_response.status_code == 200:
                qr_data = qr_response.json()
                return {
                    "sucesso": True,
                    "id_pagamento": payment_id,
                    "tipo": "pix",
                    "payload_pix": qr_data.get('payload'),
                    "imagem_qr": qr_data.get('encodedImage'),
                    "vencimento": vencimento
                }
        
        # Para Cartão ou Link, retornamos a URL da fatura
        return {
            "sucesso": True,
            "id_pagamento": payment_id,
            "tipo": "cartao",
            "link_pagamento": data_asaas.get('invoiceUrl'),
            "vencimento": vencimento
        }

    except Exception as e:
        logger.error(f"❌ Erro crítico no fluxo de pagamento Asaas: {e}")
        return {"erro": "Falha de comunicação com o sistema financeiro. Tente novamente."}