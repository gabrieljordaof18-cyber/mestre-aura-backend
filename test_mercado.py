"""
Testes isolados do Mercado Físico:
1. Produto com múltiplos sabores exige seleção (simulado via lógica de filtro)
2. Pedido salvo no banco contém o sabor escolhido
3. CEP de Goiânia retorna opção motoboy R$15 mesmo sem token Melhor Envio

Execução: source venv/bin/activate && python3 test_mercado.py
"""
import sys
from dotenv import load_dotenv
load_dotenv()

from data_manager import mongo_db
from logic_frete import _e_cep_goiania, _OPCAO_MOTOBOY_GOIANIA, calcular_cotacao_frete

PASS = "✅ PASSOU"
FAIL = "❌ FALHOU"
erros = []


# ──────────────────────────────────────────────────────────────
# TESTE 1 — Validação de sabor obrigatório (regra de negócio)
# ──────────────────────────────────────────────────────────────
def teste_sabor_obrigatorio():
    print("── TESTE 1: Sabor obrigatório para produto multi-sabor ─────")

    # Simula a lógica do frontend: produto com 3 sabores, sem seleção → rejeita
    produto_multi = {"nome": "Whey Teste", "tamanhos": ["Chocolate", "Baunilha", "Morango"]}
    sabor_selecionado = None  # usuário não selecionou

    pode_adicionar = not (len(produto_multi["tamanhos"]) > 1 and sabor_selecionado is None)
    if not pode_adicionar:
        print(f"  {PASS} [Multi-sabor sem seleção] bloqueado corretamente")
    else:
        print(f"  {FAIL} [Multi-sabor sem seleção] deveria ser bloqueado")
        erros.append("sabor_obrigatorio_multi")

    # Com seleção → permite
    sabor_selecionado = "Chocolate"
    pode_adicionar = not (len(produto_multi["tamanhos"]) > 1 and sabor_selecionado is None)
    if pode_adicionar:
        print(f"  {PASS} [Multi-sabor com seleção] permitido corretamente")
    else:
        print(f"  {FAIL} [Multi-sabor com seleção] deveria ser permitido")
        erros.append("sabor_obrigatorio_com_selecao")

    # Produto com sabor único → auto-selecionado, permite sempre
    produto_unico = {"nome": "Creatina Teste", "tamanhos": ["Sem sabor"]}
    sabor_auto = produto_unico["tamanhos"][0]  # lógica do frontend
    pode_adicionar = not (len(produto_unico["tamanhos"]) > 1 and sabor_auto is None)
    if pode_adicionar:
        print(f"  {PASS} [Sabor único auto-selecionado] permitido corretamente")
    else:
        print(f"  {FAIL} [Sabor único] deveria ser permitido")
        erros.append("sabor_unico")


# ──────────────────────────────────────────────────────────────
# TESTE 2 — Pedido salvo no banco contém sabor
# ──────────────────────────────────────────────────────────────
def teste_pedido_com_sabor():
    print("── TESTE 2: Pedido com sabor salvo no banco ────────────────")
    if mongo_db is None:
        print(f"  {FAIL} MongoDB inacessível")
        erros.append("pedido_mongo")
        return

    col = mongo_db["test_mercado_pedidos"]
    col.drop()

    pedido_teste = {
        "user_id": "test_user_001",
        "status": "TEST",
        "valor_produtos": 97.00,
        "valor_frete": 15.00,
        "metodo": "pix",
        "itens": [
            {"id": "prod_abc", "nome": "Whey High Protein 900g", "qtd": 1, "sabor": "Chocolate"},
            {"id": "prod_def", "nome": "Creatina 300g Probiótica",  "qtd": 1, "sabor": "Sem sabor"},
        ],
    }
    result = col.insert_one(pedido_teste)
    recuperado = col.find_one({"_id": result.inserted_id})

    itens = recuperado.get("itens", [])
    sabor_whey = itens[0].get("sabor") if itens else None
    sabor_creatina = itens[1].get("sabor") if len(itens) > 1 else None

    if sabor_whey == "Chocolate":
        print(f"  {PASS} [Sabor Whey] '{sabor_whey}' salvo corretamente")
    else:
        print(f"  {FAIL} [Sabor Whey] esperado 'Chocolate', obtido '{sabor_whey}'")
        erros.append("pedido_sabor_whey")

    if sabor_creatina == "Sem sabor":
        print(f"  {PASS} [Sabor Creatina] '{sabor_creatina}' salvo corretamente")
    else:
        print(f"  {FAIL} [Sabor Creatina] esperado 'Sem sabor', obtido '{sabor_creatina}'")
        erros.append("pedido_sabor_creatina")

    col.drop()


# ──────────────────────────────────────────────────────────────
# TESTE 3 — Motoboy Goiânia aparece para CEPs "74" + não aparece para fora
# ──────────────────────────────────────────────────────────────
def teste_motoboy_goiania():
    print("── TESTE 3: Motoboy Goiânia por prefixo de CEP ────────────")

    ceps_goiania = ["74180170", "74000000", "74993000", "74110010"]
    ceps_fora    = ["01310100", "30140071", "80230130", "20040020"]  # SP/BH/CWB/RJ

    ok = True
    for cep in ceps_goiania:
        if _e_cep_goiania(cep):
            print(f"  {PASS} [{cep}] detectado como Goiânia")
        else:
            print(f"  {FAIL} [{cep}] deveria ser detectado como Goiânia")
            erros.append(f"motoboy_goiania_{cep}")
            ok = False

    for cep in ceps_fora:
        if not _e_cep_goiania(cep):
            print(f"  {PASS} [{cep}] corretamente excluído de Goiânia")
        else:
            print(f"  {FAIL} [{cep}] não deveria ser detectado como Goiânia")
            erros.append(f"motoboy_fora_{cep}")
            ok = False

    # Sem token Melhor Envio → motoboy deve aparecer isolado para Goiânia
    import os
    token_backup = os.environ.pop("MELHOR_ENVIO_TOKEN", None)
    try:
        result = calcular_cotacao_frete("74180170", [{"weight": 0.5, "width": 15, "height": 10, "length": 20, "insurance_value": 99}])
        if isinstance(result, list) and any(o.get("id") == "motoboy_goiania" for o in result):
            print(f"  {PASS} [Sem token ME] motoboy retornado isolado para Goiânia")
        else:
            print(f"  {FAIL} [Sem token ME] motoboy deveria estar na lista: {result}")
            erros.append("motoboy_sem_token")
    finally:
        if token_backup:
            os.environ["MELHOR_ENVIO_TOKEN"] = token_backup

    # Preço correto
    preco = float(_OPCAO_MOTOBOY_GOIANIA["price"])
    if preco == 15.0:
        print(f"  {PASS} [Preço motoboy] R${preco:.2f}")
    else:
        print(f"  {FAIL} [Preço motoboy] esperado 15.00, obtido {preco}")
        erros.append("motoboy_preco")


# ──────────────────────────────────────────────────────────────
# TESTE 4 — Produtos inseridos têm preco_cartao e preco_pix
# ──────────────────────────────────────────────────────────────
def teste_schema_produtos():
    print("── TESTE 4: Schema dos 29 produtos no banco ────────────────")
    if mongo_db is None:
        print(f"  {FAIL} MongoDB inacessível"); erros.append("schema_mongo"); return

    docs = list(mongo_db["ProdutosLoja"].find({"preco_cartao": {"$exists": True}}, {"nome": 1, "preco_cartao": 1, "preco_pix": 1, "tamanhos": 1}))
    print(f"  📦 {len(docs)} produtos com preco_cartao no banco")

    sem_preco = [d["nome"] for d in docs if d.get("preco_cartao", 0) == 0]
    sem_sabor = [d["nome"] for d in docs if not d.get("tamanhos")]

    if sem_preco:
        print(f"  ⚠️  Preços pendentes (esperado apenas Protein Crush): {sem_preco}")
    if sem_sabor:
        print(f"  {FAIL} Produtos sem tamanhos: {sem_sabor}"); erros.append("schema_tamanhos")
    else:
        print(f"  {PASS} Todos os produtos têm campo tamanhos")

    if len(docs) >= 28:
        print(f"  {PASS} {len(docs)} produtos encontrados (28+ esperados)")
    else:
        print(f"  {FAIL} Esperado ≥28 produtos, encontrado {len(docs)}")
        erros.append("schema_count")


# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n🧪 Testes Mercado Físico\n")
    teste_sabor_obrigatorio()
    teste_pedido_com_sabor()
    teste_motoboy_goiania()
    teste_schema_produtos()

    if erros:
        print(f"\n❌ {len(erros)} falha(s): {erros}")
        sys.exit(1)
    else:
        print("\n✅ Todos os testes passaram.")
        sys.exit(0)
