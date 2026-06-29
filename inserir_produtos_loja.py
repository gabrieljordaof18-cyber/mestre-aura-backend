"""
Script de cadastro inicial dos 29 produtos da Loja Física AURA.
Execução: source venv/bin/activate && python3 inserir_produtos_loja.py

Atenção:
- "Protein Crush Under Labz Refil 900g" está com preco_cartao=0 e preco_pix=0
  pois os preços foram omitidos na tabela original. Atualize manualmente depois.
- Dimensões e pesos usam defaults do schema (atualizar em sessão futura com medidas reais).
- Imagens em branco (inserir URLs depois).
"""

import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from data_manager import mongo_db

COLECAO = "ProdutosLoja"

DEFAULTS = {
    "preco_original": 0.0,
    "custo_moedas": 0,
    "nivel_minimo": 1,
    "imagem_url": "",
    "descricao": "",
    "estoque": True,
    "peso_kg": 0.5,
    "largura_cm": 15,
    "altura_cm": 10,
    "comprimento_cm": 20,
    "cep_origem": "74180170",
    "criado_em": datetime.now().isoformat(),
}

PRODUTOS = [
    # ── WHEY / PROTEÍNAS ────────────────────────────────────────────────────────
    {
        "nome": "Whey High Protein 900g - Absolut Nutrition",
        "marca": "Absolut Nutrition",
        "custo": 79.90,
        "preco_cartao": 99.00,
        "preco_pix": 97.00,
        "preco_aura": 99.00,
        "tamanhos": ["Baunilha", "Chocolate", "Morango"],
        "categoria": "Suplementos",
        "destaque": True,
    },
    {
        "nome": "Whey Concentrado YumiPro Canibal Inc 900g",
        "marca": "Canibal Inc",
        "custo": 99.90,
        "preco_cartao": 121.90,
        "preco_pix": 119.40,
        "preco_aura": 121.90,
        "tamanhos": ["Chocolate", "Leite", "Morango"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        "nome": "JoyPro Protein Pote 900g Shark Pro",
        "marca": "Shark Pro",
        "custo": 99.90,
        "preco_cartao": 121.90,
        "preco_pix": 119.40,
        "preco_aura": 121.90,
        "tamanhos": ["Brigadeiro", "Paçoca", "Banana com Canela", "Iogurte de Morango"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        "nome": "Whey Concentrado Max Titanium 900g",
        "marca": "Max Titanium",
        "custo": 144.90,
        "preco_cartao": 173.40,
        "preco_pix": 169.90,
        "preco_aura": 173.40,
        "tamanhos": ["Baunilha", "Chocolate", "Leite"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        "nome": "Whey Protein Isolado DUX 900g",
        "marca": "DUX Nutrition",
        "custo": 304.90,
        "preco_cartao": 356.70,
        "preco_pix": 349.50,
        "preco_aura": 356.70,
        "tamanhos": ["Baunilha", "Chocolate", "Neutro", "Chocolate Branco"],
        "categoria": "Suplementos",
        "destaque": True,
    },
    {
        "nome": "Whey Protein Concentrado DUX 900g",
        "marca": "DUX Nutrition",
        "custo": 179.90,
        "preco_cartao": 213.50,
        "preco_pix": 209.20,
        "preco_aura": 213.50,
        "tamanhos": ["Baunilha", "Chocolate"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        "nome": "Sport Protein Dobro 450g",
        "marca": "Sport Science",
        "custo": 152.91,
        "preco_cartao": 182.60,
        "preco_pix": 178.90,
        "preco_aura": 182.60,
        "tamanhos": ["Choco e Avelã", "Croc Belga"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        # ATENÇÃO: precos cartao/pix ausentes na tabela original — atualize manualmente
        "nome": "Protein Crush Under Labz Refil 900g",
        "marca": "Under Labz",
        "custo": 164.30,
        "preco_cartao": 0.00,
        "preco_pix": 0.00,
        "preco_aura": 0.00,
        "tamanhos": ["Vitamina de Frutas", "Alpine Milkbear", "Dulce de Leche", "Swiss Chocobear", "Strawbear Swiss"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    # ── CREATINAS ───────────────────────────────────────────────────────────────
    {
        "nome": "Creatina 300g Probiótica",
        "marca": "Probiótica",
        "custo": 59.90,
        "preco_cartao": 76.10,
        "preco_pix": 74.50,
        "preco_aura": 76.10,
        "tamanhos": ["Sem sabor"],
        "categoria": "Suplementos",
        "destaque": True,
    },
    {
        "nome": "Creatina 100% Pura Hardcore Integralmédica 300g",
        "marca": "Integralmédica",
        "custo": 89.00,
        "preco_cartao": 109.40,
        "preco_pix": 107.20,
        "preco_aura": 109.40,
        "tamanhos": ["Sem sabor"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        "nome": "Creatina Monohidratada Shark Pro 300g",
        "marca": "Shark Pro",
        "custo": 49.90,
        "preco_cartao": 64.60,
        "preco_pix": 63.30,
        "preco_aura": 64.60,
        "tamanhos": ["Natural"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        "nome": "Creatina Monohidratada DUX 300g",
        "marca": "DUX Nutrition",
        "custo": 99.90,
        "preco_cartao": 121.90,
        "preco_pix": 119.40,
        "preco_aura": 121.90,
        "tamanhos": ["Sem sabor"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        "nome": "Creatina 100% Pura 300g Under Labz",
        "marca": "Under Labz",
        "custo": 39.90,
        "preco_cartao": 53.20,
        "preco_pix": 52.10,
        "preco_aura": 53.20,
        "tamanhos": ["Sem sabor"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    # ── PRÉ-TREINOS ─────────────────────────────────────────────────────────────
    {
        "nome": "Pré Treino V9 Pump Shark Pro 300g",
        "marca": "Shark Pro",
        "custo": 107.91,
        "preco_cartao": 131.10,
        "preco_pix": 128.40,
        "preco_aura": 131.10,
        "tamanhos": ["Energético", "Laranja", "Limão", "Maracujá", "Tangerina"],
        "categoria": "Suplementos",
        "destaque": True,
    },
    {
        "nome": "BT 400 Nitrato Isolado 220g",
        "marca": "BT Nutrition",
        "custo": 233.91,
        "preco_cartao": 275.40,
        "preco_pix": 269.80,
        "preco_aura": 275.40,
        "tamanhos": ["Sem sabor"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        "nome": "Viking Valhalla Pote 450g",
        "marca": "Viking",
        "custo": 109.90,
        "preco_cartao": 133.40,
        "preco_pix": 130.70,
        "preco_aura": 133.40,
        "tamanhos": ["Limão", "Abacaxi com Gengibre", "Maçã Verde"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        "nome": "Pré Workout Warzone Under Labz 300g",
        "marca": "Under Labz",
        "custo": 119.90,
        "preco_cartao": 144.80,
        "preco_pix": 141.90,
        "preco_aura": 144.80,
        "tamanhos": ["Purple Green Bomb", "Purple Blood Battle"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        "nome": "C4 Beta Pump New Millen Pote 225g",
        "marca": "New Millen",
        "custo": 84.90,
        "preco_cartao": 104.70,
        "preco_pix": 102.60,
        "preco_aura": 104.70,
        "tamanhos": ["Tangerina", "Melancia", "Maçã Verde", "Limão", "Frutas Roxas"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        "nome": "Pré Treino Hium Pote 300g",
        "marca": "Hium",
        "custo": 119.90,
        "preco_cartao": 144.80,
        "preco_pix": 141.90,
        "preco_aura": 144.80,
        "tamanhos": ["Frutas Vermelhas", "Limão Yuzu"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    # ── OUTROS SUPLEMENTOS ──────────────────────────────────────────────────────
    {
        "nome": "Albumina Naturovos Refil 420g",
        "marca": "Naturovos",
        "custo": 39.90,
        "preco_cartao": 53.20,
        "preco_pix": 52.10,
        "preco_aura": 53.20,
        "tamanhos": ["Natural"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        "nome": "Palatinose Ocean Drop Pote 300g",
        "marca": "Ocean Drop",
        "custo": 62.91,
        "preco_cartao": 79.50,
        "preco_pix": 77.90,
        "preco_aura": 79.50,
        "tamanhos": ["Sem sabor"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        "nome": "Arginine 100% Pura Adaptogen 100g",
        "marca": "Adaptogen",
        "custo": 44.91,
        "preco_cartao": 58.90,
        "preco_pix": 57.70,
        "preco_aura": 58.90,
        "tamanhos": ["Sem sabor"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        "nome": "Eletrolitos Ocean Drop 180g",
        "marca": "Ocean Drop",
        "custo": 89.91,
        "preco_cartao": 110.50,
        "preco_pix": 108.20,
        "preco_aura": 110.50,
        "tamanhos": ["Limão"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        "nome": "D-Ribose Dynlab 300g",
        "marca": "Dynlab",
        "custo": 89.91,
        "preco_cartao": 110.50,
        "preco_pix": 108.20,
        "preco_aura": 110.50,
        "tamanhos": ["Sem sabor"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        "nome": "Supercoffee 3.0 380g",
        "marca": "Caffeine Army",
        "custo": 206.91,
        "preco_cartao": 244.50,
        "preco_pix": 239.60,
        "preco_aura": 244.50,
        "tamanhos": ["Original", "Doce de Leite", "Choconilla", "Língua de Gato", "Vanilla Latte"],
        "categoria": "Suplementos",
        "destaque": True,
    },
    # ── SAÚDE & BEM-ESTAR ───────────────────────────────────────────────────────
    {
        "nome": "True Calm & Relax True Source 90caps",
        "marca": "True Source",
        "custo": 103.50,
        "preco_cartao": 126.00,
        "preco_pix": 123.40,
        "preco_aura": 126.00,
        "tamanhos": ["Cápsulas"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        "nome": "Melatonin Duo Essential 120caps",
        "marca": "Essential Nutrition",
        "custo": 59.90,
        "preco_cartao": 76.10,
        "preco_pix": 74.50,
        "preco_aura": 76.10,
        "tamanhos": ["Menta"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        "nome": "Omega Fish Oil DUX 120caps",
        "marca": "DUX Nutrition",
        "custo": 99.90,
        "preco_cartao": 121.90,
        "preco_pix": 119.40,
        "preco_aura": 121.90,
        "tamanhos": ["Cápsulas"],
        "categoria": "Suplementos",
        "destaque": False,
    },
    {
        "nome": "Coenzima Q10 500mg Ocean Drop 60caps",
        "marca": "Ocean Drop",
        "custo": 89.90,
        "preco_cartao": 110.50,
        "preco_pix": 108.50,
        "preco_aura": 110.50,
        "tamanhos": ["Cápsulas"],
        "categoria": "Suplementos",
        "destaque": False,
    },
]


def main():
    if mongo_db is None:
        print("❌ MongoDB inacessível. Verifique MONGODB_URI no .env")
        sys.exit(1)

    col = mongo_db[COLECAO]
    inseridos = 0
    ignorados = 0

    for p in PRODUTOS:
        doc = {**DEFAULTS, **p}
        # Garante que preco_aura espelha preco_cartao (legado)
        doc["preco_aura"] = doc.get("preco_cartao", 0.0)

        existing = col.find_one({"nome": doc["nome"]})
        if existing:
            print(f"  ⏭  Já existe: {doc['nome']}")
            ignorados += 1
            continue

        result = col.insert_one(doc)
        print(f"  ✅ Inserido [{str(result.inserted_id)[-6:]}]: {doc['nome']}")
        inseridos += 1

    print(f"\n📦 Concluído: {inseridos} inseridos, {ignorados} já existiam.")
    pendentes = [p["nome"] for p in PRODUTOS if p.get("preco_cartao", 1) == 0.0]
    if pendentes:
        print(f"\n⚠️  PREÇO PENDENTE (preco_cartao=0): {pendentes}")


if __name__ == "__main__":
    main()
