import os
import requests
import logging

# Configuração de Logs
logger = logging.getLogger("AURA_LOGISTICA")

# URLs do Melhor Envio (Atualizado para Produção)
MELHOR_ENVIO_URL = "https://www.melhorenvio.com.br/api/v2/me/shipment/calculate"

def calcular_cotacao_frete(cep_destino, itens_carrinho):
    """
    Calcula as opções de frete no Melhor Envio.
    itens_carrinho deve ser uma lista de objetos com: peso, largura, altura, comprimento.
    """
    token = os.getenv("MELHOR_ENVIO_TOKEN")
    # CEP de Origem puxado do Environment Variable do Render
    cep_origem = os.getenv("CEP_ORIGEM_AURA", "74886044") 

    if not token:
        logger.error("❌ Token do Melhor Envio não configurado no Render.")
        return {"erro": "Serviço de frete temporariamente indisponível."}

    # Montando o payload para o Melhor Envio
    payload = {
        "from": { "postal_code": cep_origem },
        "to": { "postal_code": cep_destino },
        "products": []
    }

    # Adicionando os produtos do carrinho ao cálculo de cubagem
    for item in itens_carrinho:
        # Prioriza os campos específicos do schema.py se disponíveis
        payload["products"].append({
            "id": str(item.get("id")),
            "width": item.get("largura_cm", item.get("largura", 15)),
            "height": item.get("altura_cm", item.get("altura", 10)),
            "length": item.get("comprimento_cm", item.get("comprimento", 20)),
            "weight": item.get("peso_kg", item.get("peso", 0.5)),
            "insurance_value": item.get("preco_final", item.get("preco", 0)),
            "quantity": item.get("quantidade", 1)
        })

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Aura Performance App (contato@auraperformance.com.br)"
    }

    try:
        response = requests.post(MELHOR_ENVIO_URL, json=payload, headers=headers)
        if response.status_code == 200:
            # Retorna a lista de serviços (Jadlog, Sedex, etc.)
            return response.json()
        else:
            logger.error(f"Erro Melhor Envio: {response.text}")
            return {"erro": "Não foi possível calcular o frete para este CEP."}
    except Exception as e:
        logger.error(f"Falha na conexão com Melhor Envio: {e}")
        return {"erro": "Erro de conexão com o servidor de frete."}