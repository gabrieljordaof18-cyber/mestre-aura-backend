import os
import json
import logging
from typing import List, Dict, Any
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

# Importações da Nova Arquitetura
from data_user import carregar_memoria
# [AURA FIX] Importação explícita para garantir sincronização com Render/Atlas
from data_manager import mongo_db, DESCENDING, salvar_plano

# Carrega variáveis do .env
load_dotenv()

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AURA_BRAIN")

# Configuração da OpenAI
client = None
api_key = os.getenv("OPENAI_API_KEY")

if api_key:
    try:
        # timeout=60s evita o erro de 'Mestre Meditando' por timeout do Render (30s padrão)
        # O Render tem limite de 30s de resposta HTTP; a OpenAI responde em até ~45s em prompts
        # densos — aumentamos o timeout do cliente para evitar que o SDK cancele antes.
        client = OpenAI(api_key=api_key, timeout=60.0)
        logger.info("✅ Mestre da Aura inicializado via OpenAI (timeout=60s).")
    except Exception as e:
        logger.error(f"⚠️ Falha crítica ao iniciar Mestre da Aura: {e}")
else:
    logger.warning("⚠️ OPENAI_API_KEY ausente no .env do Render. O chat ficará offline.")

# ======================================================
# 🛠️ FERRAMENTAS DO MESTRE (DIETAS, TREINOS E LOGÍSTICA)
# ======================================================

SCHEMA_EXERCICIO = {
    "type": "object",
    "properties": {
        "exercicio": {"type": "string", "description": "Nome do exercício ou atividade (Ex: Supino Reto, Corrida na Esteira, Natação)"},
        "tipo": {"type": "string", "enum": ["forca", "cardio", "endurance", "flexibilidade"]},
        "periodo": {"type": "string", "enum": ["unico", "manha", "tarde", "noite"]},
        "bloco": {"type": "string", "description": "Opcional: aquecimento, principal, finalizador, acessório"},
        "series": {"type": "string", "description": "Número de séries (Ex: 4)"},
        "reps": {"type": "string", "description": "Repetições ou tempo (Ex: 10-12 ou 45 seg)"},
        "descanso": {"type": "string", "description": "Intervalo entre séries (Ex: 90s, 2min)"},
        "rpe": {"type": "string", "description": "Percepção de esforço (Ex: RPE 7-8)"},
        "distancia": {"type": "string", "description": "Para cardios (Ex: 5, 500, 2.5)"},
        "unidade": {"type": "string", "enum": ["km", "m", "min", "reps"], "description": "Unidade da distância ou volume"},
        "detalhes": {"type": "string", "description": "Dicas técnicas, cadência, carga sugerida ou progressão"}
    },
    "required": ["exercicio", "tipo", "periodo"]
}

TOOLS_AURA = [
    {
        "type": "function",
        "function": {
            "name": "salvar_nova_dieta",
            "description": "ESTRUTURA e SALVA um plano alimentar detalhado. Use sempre que o usuário pedir orientações nutricionais.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resumo_objetivo": {"type": "string"},
                    "kcal_total": {"type": "string"},
                    "cafe_da_manha": {"type": "string"},
                    "almoco": {"type": "string"},
                    "lanche": {"type": "string"},
                    "jantar": {"type": "string"},
                    "suplementacao": {"type": "string"}
                },
                "required": ["resumo_objetivo", "cafe_da_manha", "almoco", "jantar"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "salvar_novo_treino",
            "description": "CRIA um cronograma SEMANAL ROBUSTO e EXTENSO. Use de 5 a 15+ exercícios por dia quando o protocolo exigir volume ou complexidade (periodizações avançadas, blocos híbridos, etc.). Deve integrar Musculação com os esportes favoritos do atleta (Corrida, Ciclismo, etc). Inclua aquecimento, bloco principal e finalizador quando relevante.",
            "parameters": {
                "type": "object",
                "properties": {
                    "foco_atual": {"type": "string", "description": "Ex: Hipertrofia com foco em Endurance"},
                    "dicas_tecnicas": {"type": "string", "description": "Conselhos gerais para a semana"},
                    "segunda": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "terca": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "quarta": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "quinta": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "sexta": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "sabado": {"type": "array", "items": SCHEMA_EXERCICIO},
                    "domingo": {"type": "array", "items": SCHEMA_EXERCICIO}
                },
                "required": ["foco_atual", "segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_mercado_aura",
            "description": "Busca produtos, suplementos ou equipamentos no Mercado Aura para o usuário. Use para informar preços e disponibilidade.",
            "parameters": {
                "type": "object",
                "properties": {
                    "termo_busca": {"type": "string", "description": "Ex: Creatina, Camiseta, Shaker"},
                    "categoria": {"type": "string", "enum": ["Suplementos", "Vestuário", "Equipamentos"]}
                },
                "required": ["termo_busca"]
            }
        }
    }
]

# ======================================================
# 💬 PROCESSAMENTO DE COMANDOS (IA CORE 3.3.0)
# ======================================================

def processar_comando(user_id: str, mensagem: str) -> str:
    """
    Interface principal de chat do Aura.
    Analisa contexto fisiológico, status de assinatura e decide ações.
    """
    if not user_id: return "⚠️ Erro de identificação do atleta."

    # 1. Carrega Contexto Real do MongoDB (Sincronizado com Render/Base44)
    memoria = carregar_memoria(user_id)
    if not memoria:
        return "⚠️ Não encontrei seu perfil. Certifique-se de estar logado corretamente."

    # Mapeamento de dados do Perfil e Assinatura
    nome_atleta = memoria.get("nome", "Iniciado")
    nivel_atleta = memoria.get("nivel", 1)
    status_plano = memoria.get("plano", "free").upper()
    objetivo_atleta = memoria.get("objetivo", "Performance Geral")
    esportes_atleta = memoria.get("esportes_favoritos", ["Musculação"])
    
    # Busca bio-status processado
    homeostase = memoria.get("homeostase", {})
    estado_bio = homeostase.get('estado', 'Estável')
    score_bio = homeostase.get('score', 50)
    
    # 2. Prompt do Sistema (Personalidade Evoluída do Mestre da Aura)
    prompt_sistema = {
        "role": "system", 
        "content": (
            f"Você é o MESTRE DA AURA. Inteligência central do Sistema Operacional de Performance Humana.\n"
            f"Atleta: {nome_atleta} | Nível: {nivel_atleta} | Plano: {status_plano}\n"
            f"Objetivo: {objetivo_atleta} | Esportes Favoritos: {', '.join(esportes_atleta)}\n"
            f"Estado Bio: {estado_bio} (Score: {score_bio})\n\n"
            f"DIRETRIZES DE ATENDIMENTO:\n"
            f"1. TOM: Técnico, estoico, motivador e focado em métricas de alto rendimento.\n"
            f"2. TREINOS NATIVOS: Planilhas semanais devem ser densas e extensas quando necessário (5 a 15+ exercícios/dia). Priorize volume, progressão e detalhamento técnico (séries, reps, carga, descanso, RPE). Se o plano for 'FREE', incentive o upgrade para o plano PRO para protocolos ilimitados.\n"
            f"3. LOGÍSTICA INTEGRADA: O Mercado Aura possui entrega em todo o Brasil. Informe que o cálculo de frete (Melhor Envio) é feito em tempo real no checkout.\n"
            f"4. TOOLS: Sempre use tools para salvar Treinos e Dietas. Após salvar, responda: 'Protocolo atualizado! Verifique a aba correspondente acima.'\n"
            f"5. PRIVACIDADE: Se questionado, confirme que os dados de biometria são criptografados e seguem a Política de Privacidade nativa do app.\n\n"
            f"REGRA CRÍTICA PARA TREINOS: Quando gerar um plano semanal, OBRIGATORIAMENTE inclua:\n"
            f"- Mínimo 5 exercícios por dia de treino (nunca menos)\n"
            f"- Estrutura ABC correta: Dia A=Peito+Tríceps+Ombro, Dia B=Costas+Bíceps, Dia C=Pernas+Core\n"
            f"- Upper/Lower: Upper=Peito+Costas+Ombros+Braços, Lower=Quadril+Posterior+Panturrilha+Core\n"
            f"- Sempre preencha os campos: series, reps, descanso, rpe, detalhes para cada exercício\n"
            f"- Dias de descanso SEMPRE como array vazio []\n"
            f"- NUNCA truncar o JSON — todos os 7 dias devem estar completos"
        )
    }

    # 3. Histórico e Mensagem Atual (limitado a 5 pares para evitar contexto saturado)
    historico = _buscar_historico(user_id, limite=5)
    mensagens = [prompt_sistema] + historico + [{"role": "user", "content": mensagem}]

    # 4. Execução OpenAI
    try:
        if client is None: return "⚠️ O Mestre está em meditação profunda (Sistema Offline)."

        # Detecta se é pedido de treino ou dieta
        eh_pedido_estruturado = any(p in mensagem.lower() for p in [
            "treino", "treinar", "exercício", "exercicio", "musculação", "musculacao",
            "academia", "dieta", "alimentação", "alimentacao", "protocolo", "plano",
            "semana", "segunda", "terca", "quarta", "quinta", "sexta", "sábado", "sabado"
        ])

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=mensagens,
            tools=TOOLS_AURA,
            tool_choice="required" if eh_pedido_estruturado else "auto",
            temperature=0.6,
            max_tokens=4096,
            parallel_tool_calls=False,
        )
        
        msg_ia = response.choices[0].message

        # Lógica de Ferramentas (Actions)
        if msg_ia.tool_calls:
            texto_resposta = _executar_ferramentas(user_id, msg_ia.tool_calls)
        else:
            texto_resposta = msg_ia.content.strip()

    except Exception as e:
        err_str = str(e).lower()
        logger.error(f"Erro OpenAI para o user {user_id}: {e}")
        if "timeout" in err_str or "timed out" in err_str or "read timeout" in err_str:
            texto_resposta = (
                "⏳ O Mestre levou mais tempo do que o esperado para processar seu protocolo — "
                "possivelmente por um prompt muito denso. Tente uma pergunta mais direta ou "
                "aguarde alguns instantes e tente novamente."
            )
        else:
            texto_resposta = "⚠️ O Mestre teve uma interrupção na conexão neural. Tente novamente."

    # 5. Salva Interação
    _salvar_chat(user_id, "user", mensagem)
    _salvar_chat(user_id, "assistant", texto_resposta)
    
    return texto_resposta


# ======================================================
# 📸 MESTRE DA AURA — MODO MULTIMODAL (ANÁLISE DE FOTOS)
# ======================================================

_PROMPT_ANALISE_IMAGEM = (
    "\n\nANÁLISE DE IMAGENS:\n"
    "Quando o usuário enviar uma foto, analise com atenção.\n"
    "Se for uma foto de lesão ou região do corpo com dor:\n"
    "  - Identifique a área afetada visualmente\n"
    "  - Sugira exercícios que NÃO agravem a lesão\n"
    "  - Sugira exercícios de reabilitação quando apropriado\n"
    "  - Oriente sobre execução correta de movimentos seguros\n"
    "  - Sempre recomende consultar um profissional de saúde para diagnóstico\n"
    "Se for uma foto de execução de exercício:\n"
    "  - Analise a postura e execução com base no que é visível\n"
    "  - Aponte melhorias específicas e objetivas\n"
    "  - Elogie os pontos corretos para motivar o atleta\n"
    "Se a imagem não for relacionada a performance ou saúde, responda com:\n"
    "  'Identifiquei a imagem, mas prefiro focar em performance e saúde. "
    "Como posso ajudar com seu treino?'"
)


def processar_comando_com_imagem(user_id: str, mensagem: str, imagem_base64: str) -> str:
    """
    Variante multimodal de processar_comando.
    Usa gpt-4o (com visão) para análise de fotos de lesões, execução de exercícios, etc.
    """
    if not user_id: return "⚠️ Erro de identificação do atleta."

    memoria = carregar_memoria(user_id)
    if not memoria:
        return "⚠️ Não encontrei seu perfil. Certifique-se de estar logado corretamente."

    nome_atleta     = memoria.get("nome", "Iniciado")
    nivel_atleta    = memoria.get("nivel", 1)
    status_plano    = memoria.get("plano", "free").upper()
    objetivo_atleta = memoria.get("objetivo", "Performance Geral")
    esportes_atleta = memoria.get("esportes_favoritos", ["Musculação"])
    homeostase      = memoria.get("homeostase", {})
    estado_bio      = homeostase.get("estado", "Estável")
    score_bio       = homeostase.get("score", 50)

    prompt_sistema = {
        "role": "system",
        "content": (
            f"Você é o MESTRE DA AURA. Inteligência central do Sistema Operacional de Performance Humana.\n"
            f"Atleta: {nome_atleta} | Nível: {nivel_atleta} | Plano: {status_plano}\n"
            f"Objetivo: {objetivo_atleta} | Esportes Favoritos: {', '.join(esportes_atleta)}\n"
            f"Estado Bio: {estado_bio} (Score: {score_bio})\n\n"
            f"DIRETRIZES DE ATENDIMENTO:\n"
            f"1. TOM: Técnico, estoico, motivador e focado em métricas de alto rendimento.\n"
            f"2. TOOLS: Use tools apenas quando o usuário pedir para salvar Treinos e Dietas — "
            f"não use tools em respostas de análise de imagem.\n"
            f"3. PRIVACIDADE: Os dados de biometria são criptografados."
            + _PROMPT_ANALISE_IMAGEM
        )
    }

    # Histórico reduzido para não sobrecarregar o contexto multimodal
    historico = _buscar_historico(user_id, limite=3)

    texto_msg = (mensagem.strip() or "Analise esta imagem.")
    content_usuario = [
        {"type": "text",      "text": texto_msg},
        {"type": "image_url", "image_url": {"url": imagem_base64, "detail": "high"}},
    ]

    mensagens = [prompt_sistema] + historico + [{"role": "user", "content": content_usuario}]

    try:
        if client is None:
            return "⚠️ O Mestre está em meditação profunda (Sistema Offline)."

        response = client.chat.completions.create(
            model="gpt-4o",          # Modelo com suporte a visão
            messages=mensagens,
            temperature=0.6,
            max_tokens=1500,
        )
        texto_resposta = response.choices[0].message.content.strip()

    except Exception as e:
        err_str = str(e).lower()
        logger.error(f"Erro OpenAI multimodal para {user_id}: {e}")
        if "timeout" in err_str or "timed out" in err_str:
            texto_resposta = (
                "⏳ O Mestre levou mais tempo do que o esperado para analisar a imagem. "
                "Tente novamente com uma foto menor ou uma pergunta direta."
            )
        elif "invalid" in err_str and ("image" in err_str or "url" in err_str):
            texto_resposta = (
                "⚠️ Não consegui processar a imagem enviada. "
                "Certifique-se de que é uma foto válida (JPEG ou PNG)."
            )
        else:
            texto_resposta = "⚠️ O Mestre teve uma interrupção ao analisar a imagem. Tente novamente."

    log_mensagem = f"[📸 Foto] {texto_msg}" if texto_msg != "Analise esta imagem." else "[📸 Foto enviada]"
    _salvar_chat(user_id, "user", log_mensagem)
    _salvar_chat(user_id, "assistant", texto_resposta)

    return texto_resposta


# --- Funções Internas de Apoio ---

def _executar_ferramentas(user_id: str, tool_calls: list) -> str:
    """Traduz as decisões da IA em ações reais no banco de dados."""
    respostas = []
    for tool in tool_calls:
        try:
            nome_func = tool.function.name
            args = json.loads(tool.function.arguments)
            
            if nome_func == "salvar_nova_dieta":
                if salvar_plano(user_id, "dieta", args):
                    respostas.append("Protocolo Nutricional atualizado! Verifique a aba correspondente acima.")
            
            elif nome_func == "salvar_novo_treino":
                if salvar_plano(user_id, "treino", args):
                    respostas.append("Protocolo de Treinamento atualizado! Verifique a aba correspondente acima.")
            
            elif nome_func == "consultar_mercado_aura":
                # [AURA FIX] Sincronizado com a coleção oficial de produtos do Marketplace
                termo = args.get("termo_busca")
                produtos = list(mongo_db["ProdutosLoja"].find({"nome": {"$regex": termo, "$options": "i"}}).limit(3))
                
                if produtos:
                    resp_prod = "📊 Localizei no Mercado Aura:\n"
                    for p in produtos:
                        # [AURA FIX] Prioriza preco_aura e menciona a logística nativa
                        preco = p.get("preco_aura") or p.get("preco_original") or 0
                        resp_prod += f"- {p['nome']}: R$ {preco:.2f} (Cotação de frete Melhor Envio no checkout)\n"
                    respostas.append(resp_prod)
                else:
                    respostas.append("Não localizei esse item exato no estoque agora. Sugiro verificar as categorias de 'Suplementos' no menu principal.")
                    
        except Exception as e:
            logger.error(f"Erro ao executar Tool {tool.function.name}: {e}")
            
    return "\n".join(respostas) if respostas else "⚠️ Falha ao registrar o protocolo. Tente novamente."

def _buscar_historico(user_id: str, limite: int) -> List[Dict]:
    if mongo_db is None: return []
    try:
        cursor = mongo_db["chats"].find({"user_id": str(user_id)}).sort("timestamp", DESCENDING).limit(limite)
        msgs = [{"role": doc["role"], "content": doc["content"]} for doc in cursor]
        return msgs[::-1]
    except Exception as e:
        logger.error(f"Erro ao buscar histórico: {e}")
        return []

def _salvar_chat(user_id: str, role: str, content: str):
    if mongo_db is not None:
        try:
            mongo_db["chats"].insert_one({
                "user_id": str(user_id),
                "role": role,
                "content": content,
                "timestamp": datetime.now()
            })
        except Exception as e:
            logger.error(f"Erro ao salvar mensagem no chat: {e}")