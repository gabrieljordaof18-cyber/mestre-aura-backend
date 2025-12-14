import os
import requests
import json
from datetime import datetime

# URL de Produção do Asaas
ASAAS_URL = "https://www.asaas.com/api/v3"

def get_headers():
    return {
        "Content-Type": "application/json",
        "access_token": os.getenv("ASAAS_API_KEY")
    }

def criar_ou_buscar_cliente(usuario_dados):
    """
    Verifica se o cliente já existe no Asaas pelo CPF ou Email.
    Se não, cria um novo.
    """
    headers = get_headers()
    
    # 1. Tenta buscar por CPF ou Email
    busca = requests.get(f"{ASAAS_URL}/customers?cpfCnpj={usuario_dados.get('cpf')}", headers=headers)
    
    if busca.status_code == 200 and busca.json()['data']:
        return busca.json()['data'][0]['id']
    
    # 2. Se não existir, cria um novo
    payload = {
        "name": usuario_dados.get('nome', 'Atleta Aura'),
        "cpfCnpj": usuario_dados.get('cpf', ''),
        "email": usuario_dados.get('email', 'email@exemplo.com'),
        "mobilePhone": usuario_dados.get('telefone', '')
    }
    
    criacao = requests.post(f"{ASAAS_URL}/customers", json=payload, headers=headers)
    
    if criacao.status_code == 200:
        return criacao.json()['id']
    else:
        print("Erro ao criar cliente:", criacao.text)
        return None

def criar_cobranca(dados_pagamento):
    """
    Gera a cobrança (PIX ou Cartão/Link)
    """
    headers = get_headers()
    
    # Garante que temos um cliente no Asaas
    customer_id = criar_ou_buscar_cliente(dados_pagamento['usuario'])
    if not customer_id:
        return {"erro": "Falha ao registrar cliente no Asaas"}

    # Define o tipo de pagamento
    billing_type = "PIX" if dados_pagamento['metodo'] == 'pix' else "CREDIT_CARD"
    
    # Payload da Cobrança
    payload = {
        "customer": customer_id,
        "billingType": billing_type,
        "value": float(dados_pagamento['valor']),
        "dueDate": datetime.now().strftime("%Y-%m-%d"), # Vence hoje
        "description": f"Pedido Aura: {dados_pagamento.get('descricao', 'Produtos Aura')}",
    }

    # CRIA A COBRANÇA
    response = requests.post(f"{ASAAS_URL}/payments", json=payload, headers=headers)
    
    if response.status_code != 200:
        return {"erro": response.text}
    
    data_asaas = response.json()
    payment_id = data_asaas['id']

    # SE FOR PIX: Precisamos pegar o QRCode e o "Copia e Cola"
    if billing_type == "PIX":
        qr_response = requests.get(f"{ASAAS_URL}/payments/{payment_id}/pixQrCode", headers=headers)
        if qr_response.status_code == 200:
            qr_data = qr_response.json()
            return {
                "sucesso": True,
                "id_pagamento": payment_id,
                "tipo": "pix",
                "payload_pix": qr_data['payload'],     # Código Copia e Cola
                "imagem_qr": qr_data['encodedImage']   # Imagem base64
            }
    
    # SE FOR CARTÃO: Retornamos o Link de Pagamento (Invoice Url)
    return {
        "sucesso": True,
        "id_pagamento": payment_id,
        "tipo": "cartao",
        "link_pagamento": data_asaas['invoiceUrl'] # Link seguro do Asaas
    }