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

    # [AURA FIX] Mapeamento Unificado de Chaves para garantir cubagem
    # Adicionando os produtos do carrinho ao cálculo de cubagem
    for item in itens_carrinho:
        # Prioriza os campos específicos do Melhor Envio, depois os do schema, depois genéricos
        payload["products"].append({
            "id": str(item.get("id") or item.get("_id", "prod_aura")),
            "width": float(item.get("width") or item.get("largura_cm") or item.get("largura") or 15),
            "height": float(item.get("height") or item.get("altura_cm") or item.get("altura") or 10),
            "length": float(item.get("length") or item.get("comprimento_cm") or item.get("comprimento") or 20),
            "weight": float(item.get("weight") or item.get("peso_kg") or item.get("peso") or 0.5),
            "insurance_value": float(item.get("insurance_value") or item.get("preco_aura") or item.get("preco") or 0),
            "quantity": int(item.get("quantity") or item.get("quantidade") or 1)
        })

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Aura Performance App (contato@auraperformance.com.br)"
    }

    try:
        # Registra o envio dos dados para monitoramento interno no Render
        logger.info(f"🚚 Enviando cotação para Melhor Envio - CEP Destino: {cep_destino}")
        
        response = requests.post(MELHOR_ENVIO_URL, json=payload, headers=headers)
        
        if response.status_code == 200:
            # Retorna a lista de serviços (Jadlog, Sedex, etc.)
            return response.json()
        else:
            logger.error(f"❌ Erro Melhor Envio ({response.status_code}): {response.text}")
            return {"erro": "Não foi possível calcular o frete para este CEP."}
            
    except Exception as e:
        logger.error(f"🔥 Falha na conexão com Melhor Envio: {e}")
        return {"erro": "Erro de conexão com o servidor de frete."}