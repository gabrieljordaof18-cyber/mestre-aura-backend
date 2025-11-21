from data_user import carregar_memoria # Funções de memória local

# ======================================================
# 🧭 FUNÇÃO — Gerar Feedback Emocional Inteligente
# ======================================================
def gerar_feedback_emocional(memoria=None):
    """
    Gera uma mensagem curta, empática e acionável com base na energia,
    sono, HRV e humor do jogador. Não altera histórico.
    """
    memoria = memoria or carregar_memoria()
    jogador = memoria.get("jogador", {})
    dados = memoria.get("dados_fisiologicos", {})

    # extrai valores com fallback
    energia = int(dados.get("energia", {}).get("nivel", jogador.get("energia", 100)))
    sono = float(dados.get("sono", {}).get("horas", memoria.get("jogador",{}).get("preferencias",{}).get("sono_medio", "7").split("h")[0] or 7) or 7)
    hrv_val = None
    try:
        hrv_val = int(dados.get("hrv", {}).get("valor", dados.get("variabilidade_hrv", 0)))
    except Exception:
        hrv_val = None

    # heurísticas simples e seguras (determinísticas)
    partes = []

    # energia
    if energia >= 90:
        partes.append("Energia ótima — aproveite para um treino técnico e pesado hoje.")
    elif energia >= 75:
        partes.append("Boa energia — foque em qualidade de execução.")
    elif energia >= 60:
        partes.append("Energia moderada — priorize movimentos compostos controlados.")
    else:
        partes.append("Baixa energia — considere recuperação ativa e sono extra.")

    # sono
    if sono >= 8:
        partes.append("Sono restaurador — recuperação muscular favorecida.")
    elif sono >= 7:
        partes.append("Sono aceitável — mantenha hidratação e proteína pós-treino.")
    else:
        partes.append("Sono abaixo do ideal — evite treinos extremamente intensos hoje.")

    # HRV como indicador de recuperação
    if hrv_val:
        if hrv_val >= 80:
            partes.append("HRV alta — estado de recuperação excelente.")
        elif hrv_val >= 60:
            partes.append("HRV estável — tendência neutra/positiva.")
        else:
            partes.append("HRV baixa — cuidado com sobrecarga, dê atenção à recuperação.")

    # sintetiza em uma frase curta para o front-end
    mensagem = " ".join(partes[:3])
    # garante tamanho razoável
    if len(mensagem) > 220:
        mensagem = mensagem[:217] + "..."

    return mensagem