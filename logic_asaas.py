import os
import requests
import re
import logging
from datetime import datetime, timedelta
from data_manager import mongo_db

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AURA_FINANCEIRO")

# URL de Produção do Asaas
ASAAS_URL = "https://www.asaas.com/api/v3"

def get_headers():
    token = os.getenv("ASAAS_ACCESS_TOKEN")
    if not token:
        logger.error("❌ ASAAS_ACCESS_TOKEN não configurado no .env")
    
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
    
    cpf_limpo = _limpar_apenas_numeros(usuario_dados.get('cpf', ''))
    email = usuario_dados.get('email', '')
    
    # 1. Tenta buscar por CPF (Mais seguro)
    if cpf_limpo:
        try:
            busca = requests.get(f"{ASAAS_URL}/customers?cpfCnpj={cpf_limpo}", headers=headers)
            if busca.status_code == 200:
                dados = busca.json().get('data', [])
                if dados:
                    return dados[0]['id']
        except Exception as e:
            logger.error(f"Erro ao buscar cliente Asaas por CPF: {e}")

    # 2. Se falhar, tenta buscar por Email
    if email:
        try:
            busca = requests.get(f"{ASAAS_URL}/customers?email={email}", headers=headers)
            if busca.status_code == 200:
                dados = busca.json().get('data', [])
                if dados:
                    return dados[0]['id']
        except Exception:
            pass
    
    # 3. Se não existir, cria um novo
    payload = {
        "name": usuario_dados.get('nome', 'Cliente Aura'),
        "cpfCnpj": cpf_limpo,
        "email": email,
        "mobilePhone": _limpar_apenas_numeros(usuario_dados.get('telefone', '')),
        "notificationDisabled": False
    }
    
    try:
        criacao = requests.post(f"{ASAAS_URL}/customers", json=payload, headers=headers)
        
        if criacao.status_code == 200:
            novo_id = criacao.json()['id']
            logger.info(f"🆕 Novo cliente Asaas criado: {novo_id}")
            return novo_id
        else:
            logger.error(f"❌ Erro Asaas (Criar Cliente): {criacao.text}")
            return None
    except Exception as e:
        logger.error(f"❌ Erro de conexão Asaas: {e}")
        return None

# ======================================================
# 💳 GERAÇÃO DE COBRANÇA & PERSISTÊNCIA
# ======================================================

def criar_cobranca(dados_pagamento: dict) -> dict:
    """
    Gera a cobrança (PIX ou Cartão) e SALVA NO MONGODB.
    """
    headers = get_headers()
    
    user_id = dados_pagamento.get('user_id')
    if not user_id:
        logger.warning("⚠️ Tentativa de criar cobrança sem user_id vinculado.")

    # 1. Identificar Cliente no Asaas
    usuario_info = dados_pagamento.get('usuario', {})
    customer_id = criar_ou_buscar_cliente(usuario_info)
    
    if not customer_id:
        return {"erro": "Falha ao registrar dados no gateway de pagamento."}

    # 2. Configurar Cobrança
    metodo = dados_pagamento.get('metodo', 'pix').lower()
    billing_type = "PIX" if metodo == 'pix' else "CREDIT_CARD"
    valor_float = float(dados_pagamento['valor'])
    
    # Ajuste: Vencimento para o dia seguinte para evitar erros de virada de lote
    vencimento = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    payload = {
        "customer": customer_id,
        "billingType": billing_type,
        "value": valor_float,
        "dueDate": vencimento,
        "description": f"Aura OS: {dados_pagamento.get('descricao', 'Produtos Performance')}",
        "externalReference": str(user_id)
    }

    # 3. Enviar para Asaas
    try:
        response = requests.post(f"{ASAAS_URL}/payments", json=payload, headers=headers)
        
        if response.status_code != 200:
            erro_msg = response.json().get('errors', [{'description': 'Erro desconhecido'}])[0]['description']
            logger.error(f"❌ Asaas recusou cobrança: {erro_msg}")
            return {"erro": f"Pagamento recusado: {erro_msg}"}
        
        data_asaas = response.json()
        payment_id = data_asaas['id']

        # 4. PERSISTÊNCIA (Harmonia com o Schema 2.0)
        if mongo_db is not None and user_id:
            novo_pedido = {
                "user_id": str(user_id),
                "asaas_id": payment_id,
                "customer_id": customer_id,
                "valor": valor_float,
                "metodo": metodo,
                "status": "PENDING",
                "descricao": dados_pagamento.get('descricao', ''),
                "created_at": datetime.now().isoformat(), # Padronizado ISO
                "updated_at": datetime.now().isoformat()
            }
            mongo_db["pedidos"].insert_one(novo_pedido)

        # 5. Retorno para o Frontend (Base44)
        if billing_type == "PIX":
            qr_response = requests.get(f"{ASAAS_URL}/payments/{payment_id}/pixQrCode", headers=headers)
            if qr_response.status_code == 200:
                qr_data = qr_response.json()
                return {
                    "sucesso": True,
                    "id_pagamento": payment_id,
                    "tipo": "pix",
                    "payload_pix": qr_data['payload'],
                    "imagem_qr": qr_data['encodedImage']
                }
        
        return {
            "sucesso": True,
            "id_pagamento": payment_id,
            "tipo": "cartao",
            "link_pagamento": data_asaas.get('invoiceUrl')
        }

    except Exception as e:
        logger.error(f"❌ Erro crítico no pagamento: {e}")
        return {"erro": "Falha de comunicação com o sistema financeiro."}