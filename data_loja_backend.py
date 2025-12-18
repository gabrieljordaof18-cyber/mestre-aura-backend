import requests
import logging

# Configuração
# URL base do Base44 (Mestre Aura)
API_BASE44_URL = "https://mestre-aura.onrender.com/api/data" 

logger = logging.getLogger("AURA_LOJA")

def buscar_pedido_por_id(pedido_id):
    """
    Busca os dados do cabeçalho do pedido (Cliente, Endereço, Status).
    """
    try:
        # No Base44, buscamos pelo ID direto
        url = f"{API_BASE44_URL}/Pedidos/{pedido_id}"
        response = requests.get(url)
        
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar pedido {pedido_id}: {e}")
        return None

def buscar_itens_do_pedido(pedido_id):
    """
    Busca todos os itens atrelados a um pedido específico.
    Como o Base44 não tem filtro nativo simples na URL pública sem query complexa,
    vamos buscar os itens e filtrar no Python (para MVP é seguro e rápido).
    """
    try:
        url = f"{API_BASE44_URL}/ItensPedido"
        response = requests.get(url)
        
        if response.status_code == 200:
            todos_itens = response.json()
            # O Base44 pode retornar {items: []} ou direto []. Tratamos os dois.
            lista = todos_itens if isinstance(todos_itens, list) else todos_itens.get('items', [])
            
            # Filtra apenas os itens deste pedido
            itens_filtrados = [item for item in lista if item.get('pedido_id') == pedido_id]
            return itens_filtrados
            
        return []
    except Exception as e:
        logger.error(f"Erro ao buscar itens do pedido {pedido_id}: {e}")
        return []

def atualizar_status_pedido(pedido_id, novo_status):
    """
    Atualiza o status do pedido para 'Pago' ou 'Enviado'.
    """
    try:
        url = f"{API_BASE44_URL}/Pedidos/{pedido_id}"
        payload = {"status": novo_status}
        requests.patch(url, json=payload) # PATCH atualiza só o campo necessário
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar status {pedido_id}: {e}")
        return False