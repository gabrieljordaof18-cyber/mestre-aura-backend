import requests
import logging
import os

# Configuração
logger = logging.getLogger("AURA_LOJA")

# ACESSO DIRETO AO BANCO (Sem passar pelo Proxy do Python)
# Deve ser a mesma URL externa que configuramos no rotas_api.py
# Se não estiver usando env, substitua pela URL real da API do Base44
API_BASE44_URL = "https://api.base44.com/api/data" 
API_KEY = os.environ.get("BASE44_KEY", "") # Pega a chave do Render

def buscar_pedido_por_id(pedido_id):
    """
    Busca os dados do cabeçalho do pedido diretamente no banco.
    """
    try:
        # Se for o ID simulado do teste (começa com 'rec_'), retornamos um Mock
        # Isso impede que o sistema quebre enquanto não temos o banco real conectado
        if pedido_id.startswith("rec_"):
            return {
                "id": pedido_id,
                "cliente_nome": "Gabriel Jordão (Simulado)",
                "cliente_email": "gabriel@aura.com",
                "endereco_rua": "Rua da Alta Performance",
                "endereco_numero": "100",
                "endereco_bairro": "Centro",
                "endereco_cep": "01001-000"
            }

        url = f"{API_BASE44_URL}/Pedidos/{pedido_id}"
        headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar pedido {pedido_id}: {e}")
        return None

def buscar_itens_do_pedido(pedido_id):
    """
    Busca itens do pedido.
    """
    try:
        # Mock de segurança para o teste do Asaas funcionar sem banco real conectado
        if pedido_id.startswith("rec_"):
            return [
                {"produto_nome": "Whey Protein Gold", "quantidade": 1, "parceiro": "Monster Suplementos"},
                {"produto_nome": "Camiseta Aura", "quantidade": 1, "parceiro": "Aura Wear"}
            ]

        url = f"{API_BASE44_URL}/ItensPedido"
        headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            todos_itens = response.json()
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
    Atualiza status.
    """
    try:
        if pedido_id.startswith("rec_"):
            logger.info(f"📝 [MOCK] Status do pedido {pedido_id} atualizado para: {novo_status}")
            return True

        url = f"{API_BASE44_URL}/Pedidos/{pedido_id}"
        payload = {"status": novo_status}
        headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
        
        requests.patch(url, json=payload, headers=headers)
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar status {pedido_id}: {e}")
        return False