# data_loja.py

def obter_catalogo_loja():
    """
    Retorna a lista de produtos da Loja Física (Marketplace).
    No futuro, isso virá do Banco de Dados.
    """
    return [
        {
            "id": 101,
            "nome": "Whey Protein Gold Standard",
            "descricao": "Proteína isolada de alta absorção. Sabor Chocolate.",
            "preco": 249.90,
            "categoria": "Suplementos",
            "loja": "Monster Suplementos",
            "foto": "https://m.media-amazon.com/images/I/61JSj6668QL._AC_SX679_.jpg",
            "destaque": True
        },
        {
            "id": 102,
            "nome": "Creatina Monohidratada",
            "descricao": "Pura e micronizada para força explosiva. 300g.",
            "preco": 119.90,
            "categoria": "Suplementos",
            "loja": "Monster Suplementos",
            "foto": "https://m.media-amazon.com/images/I/61X-2a6k7JL._AC_SX679_.jpg",
            "destaque": False
        },
        {
            "id": 103,
            "nome": "Camiseta Aura Dry-Fit",
            "descricao": "Tecido tecnológico que não retém suor. Preta.",
            "preco": 89.90,
            "categoria": "Vestuário",
            "loja": "Aura Wear",
            "foto": "https://m.media-amazon.com/images/I/61b610J5C2L._AC_SX569_.jpg",
            "destaque": False
        },
        {
            "id": 104,
            "nome": "Pré-Treino Psychotic",
            "descricao": "Foco e energia extrema para treinos pesados.",
            "preco": 189.90,
            "categoria": "Suplementos",
            "loja": "Monster Suplementos",
            "foto": "https://m.media-amazon.com/images/I/71wI-g1FmNL._AC_SX679_.jpg",
            "destaque": True
        },
        {
            "id": 105,
            "nome": "Shorts de Compressão",
            "descricao": "Ideal para corrida e MMA. Bolso interno.",
            "preco": 69.90,
            "categoria": "Vestuário",
            "loja": "Aura Wear",
            "foto": "https://m.media-amazon.com/images/I/51H8g6-k-cL._AC_SX569_.jpg",
            "destaque": False
        }
    ]