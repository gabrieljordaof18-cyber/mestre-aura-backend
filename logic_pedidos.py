import logging
from data_loja_backend import buscar_pedido_por_id, buscar_itens_do_pedido, atualizar_status_pedido

logger = logging.getLogger("AURA_LOGIC_LOJA")

# Cadastro de Parceiros (Simulado - No futuro pode vir do banco)
CONTATOS_PARCEIROS = {
    "Monster Suplementos": "pedidos@monstersuplementos.com.br",
    "Aura Wear": "logistica@aurawear.com",
    "Aura Original": "expedicao@ourapp.com"
}

def processar_venda_confirmada(pedido_id):
    """
    Função Mestra: Chamada quando o pagamento cai.
    1. Valida o pedido.
    2. Atualiza status para PAGO.
    3. Separa itens por loja.
    4. Notifica cada loja.
    """
    print(f"💰 [LOGICA] Iniciando processamento do pedido: {pedido_id}")
    
    # 1. Busca Dados
    pedido = buscar_pedido_por_id(pedido_id)
    if not pedido:
        logger.error("Pedido não encontrado no banco.")
        return False
        
    itens = buscar_itens_do_pedido(pedido_id)
    if not itens:
        logger.error("Pedido sem itens ou erro na busca.")
        return False

    print(f"📦 [LOGICA] Pedido de {pedido.get('cliente_nome')} contém {len(itens)} itens.")

    # 2. Atualiza Status
    atualizar_status_pedido(pedido_id, "Pago - Processando Envio")
    
    # 3. O Grande Split (Separação)
    pacotes_por_loja = {}
    
    for item in itens:
        parceiro = item.get('parceiro', 'Aura Original')
        
        if parceiro not in pacotes_por_loja:
            pacotes_por_loja[parceiro] = []
        
        pacotes_por_loja[parceiro].append(item)
        
    # 4. Disparo de Notificações
    for loja, lista_itens in pacotes_por_loja.items():
        email_destino = CONTATOS_PARCEIROS.get(loja, "admin@ourapp.com")
        
        # Aqui montamos a "Carta" para o lojista
        enviar_notificacao_logistica(loja, email_destino, pedido, lista_itens)
        
    return True

def enviar_notificacao_logistica(loja, email, pedido, itens):
    """
    Por enquanto, apenas imprime no console para validarmos a lógica.
    Depois trocaremos por envio real de e-mail.
    """
    print("\n" + "="*60)
    print(f"🚀 ENVIANDO PEDIDO PARA: {loja.upper()}")
    print(f"📧 Destino: {email}")
    print("-" * 60)
    print(f"CLIENTE: {pedido.get('cliente_nome')}")
    print(f"ENDEREÇO: {pedido.get('endereco_rua')}, {pedido.get('endereco_numero')} - {pedido.get('endereco_bairro')}")
    print(f"CEP: {pedido.get('endereco_cep')}")
    print("-" * 60)
    print("ITENS PARA SEPARAR:")
    for item in itens:
        print(f" - [ {item.get('quantidade')}x ] {item.get('produto_nome')}")
    print("="*60 + "\n")