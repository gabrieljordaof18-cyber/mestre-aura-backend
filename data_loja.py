# data_loja.py

def obter_catalogo_loja():
    """
    Retorna a lista de produtos da Loja Física (Marketplace).
    Simulando o Banco de Dados com imagens hospedadas externamente.
    """
    return [
        {
            "id": 101,
            "nome": "Whey Protein Gold Standard",
            "descricao": "Proteína isolada de alta absorção para recuperação muscular máxima.",
            "preco": 129.90,
            "categoria": "Suplementos",
            "loja": "Monster Suplementos",
            "foto": "https://i.postimg.cc/7hFKQ9t0/Chat-GPT-Image-16-de-dez-de-2025-18-27-14.png",
            "destaque": True
        },
        {
            "id": 102,
            "nome": "Creatina Monohidratada",
            "descricao": "Pura e micronizada. Aumente sua força explosiva nos treinos.",
            "preco": 99.90,
            "categoria": "Suplementos",
            "loja": "Monster Suplementos",
            "foto": "https://i.postimg.cc/xTKrVNGC/Chat-GPT-Image-16-de-dez-de-2025-18-31-32.png",
            "destaque": False
        },
        {
            "id": 103,
            "nome": "Camiseta Aura Dry-Fit",
            "descricao": "Tecido tecnológico respirável. Design minimalista para alta performance.",
            "preco": 79.90,
            "categoria": "Vestuário",
            "loja": "Aura Wear",
            "foto": "https://i.postimg.cc/WzzRP5nR/Chat-GPT-Image-16-de-dez-de-2025-18-15-33.png",
            "destaque": True
        },
        {
            "id": 104,
            "nome": "Pré-Treino Psychotic",
            "descricao": "Foco laser e energia extrema para seus treinos mais pesados.",
            "preco": 119.90,
            "categoria": "Suplementos",
            "loja": "Monster Suplementos",
            "foto": "https://i.postimg.cc/CxsVkndX/Chat-GPT-Image-16-de-dez-de-2025-18-29-21.png",
            "destaque": False
        },
        {
            "id": 105,
            "nome": "Shorts de Compressão",
            "descricao": "Ideal para corrida e funcional. Bolso interno e ajuste perfeito.",
            "preco": 69.90,
            "categoria": "Vestuário",
            "loja": "Aura Wear",
            "foto": "https://i.postimg.cc/JnhYyGBS/Chat-GPT-Image-16-de-dez-de-2025-18-19-58.png",
            "destaque": False
        },
        {
            "id": 106,
            "nome": "Garrafa Térmica Aura",
            "descricao": "Mantém a temperatura por 12h. Design robusto e à prova de vazamentos.",
            "preco": 29.90,
            "categoria": "Equipamentos",
            "loja": "Aura Equipaments",
            "foto": "https://i.postimg.cc/R0pyL79B/Chat-GPT-Image-16-de-dez-de-2025-18-33-02.png",
            "destaque": True
        }
    ]