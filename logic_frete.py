import os
import requests
import logging

# Configuração de Logs
logger = logging.getLogger("AURA_LOGISTICA")

# URLs do Melhor Envio (Atualizado para Produção)
MELHOR_ENVIO_URL = "https://www.melhorenvio.com.br/api/v2/me/shipment/calculate"

_PREFIXOS_GOIANIA = {"74"}

def _e_cep_goiania(cep_destino: str) -> bool:
    """CEPs de Goiânia-GO: 74000-000 a 74994-999 (prefixo "74")."""
    cep_limpo = str(cep_destino).replace("-", "").replace(" ", "").strip()
    return len(cep_limpo) >= 2 and cep_limpo[:2] in _PREFIXOS_GOIANIA

_OPCAO_MOTOBOY_GOIANIA = {
    "id": "motoboy_goiania",
    "name": "Motoboy — Goiânia",
    "company": {"id": 99, "name": "Motoboy Aura", "picture": ""},
    "price": "15.00",
    "delivery_range": {"min": 1, "max": 1},
    "delivery_time": 1,
    "currency": "BRL",
    "packages": [],
    "additional_services": {},
    "error": None,
}


def calcular_cotacao_frete(cep_destino, itens_carrinho):
    """
    Calcula as opções de frete no Melhor Envio.
    Para CEPs de Goiânia (prefixo 74), inclui opção de motoboy a R$15,00.
    itens_carrinho deve ser uma lista de objetos com: peso, largura, altura, comprimento.
    """
    token = os.getenv("MELHOR_ENVIO_TOKEN")
    # CEP de Origem puxado do Environment Variable do Render
    cep_origem = os.getenv("CEP_ORIGEM_AURA", "74180170")

    motoboy = [_OPCAO_MOTOBOY_GOIANIA] if _e_cep_goiania(cep_destino) else []

    if not token:
        logger.error("❌ Token do Melhor Envio não configurado no Render.")
        if motoboy:
            return motoboy
        return {"erro": "Serviço de frete temporariamente indisponível."}

    # Montando o payload para o Melhor Envio
    payload = {
        "from": { "postal_code": cep_origem },
        "to": { "postal_code": cep_destino },
        "products": []
    }

    # [AURA FIX] Mapeamento Triplo Unificado para garantir cubagem
    # Este bloco garante que, independente do nome da chave (vinda do banco ou frontend), 
    # o Melhor Envio receba o parâmetro técnico correto.
    for item in itens_carrinho:
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
            opcoes_me = response.json()
            if isinstance(opcoes_me, list):
                return motoboy + opcoes_me
            # Resposta inesperada mas válida: retorna só o motoboy se houver
            return motoboy if motoboy else opcoes_me
        else:
            logger.error(f"❌ Erro Melhor Envio ({response.status_code}): {response.text}")
            if motoboy:
                return motoboy
            return {"erro": "Não foi possível calcular o frete para este CEP."}

    except Exception as e:
        logger.error(f"🔥 Falha na conexão com Melhor Envio: {e}")
        if motoboy:
            return motoboy
        return {"erro": "Erro de conexão com o servidor de frete."}