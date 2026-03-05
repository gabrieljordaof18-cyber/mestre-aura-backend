import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

# Importações da Nova Arquitetura
from data_user import carregar_memoria, salvar_memoria
# O módulo 'sensores' realiza a ponte com Strava/Apple Health
from sensores import coletar_dados 

# Configuração de Logs
logger = logging.getLogger("AURA_DATA_SENSORES")

# ======================================================
# ⚙️ ORQUESTRADOR DE DADOS FISIOLÓGICOS (BIOHACKING)
# ======================================================

def obter_dados_fisiologicos(user_id: str) -> Dict[str, Any]:
    """
    Orquestra a coleta de wearables e sensores.
    1. Carrega o perfil do usuário.
    2. Extrai tokens de integração (Strava, etc).
    3. Chama a coleta externa.
    4. Realiza o merge seguro com o Schema 2.0.
    5. Extrai contexto de treinos reais para a IA.
    """
    if not user_id:
        logger.warning("⚠️ Tentativa de obter dados sem user_id.")
        return {}

    # 1. Carrega Perfil para obter Tokens de Integração
    usuario = carregar_memoria(user_id)
    if not usuario:
        logger.error(f"❌ Usuário {user_id} não encontrado para sync de sensores.")
        return {}

    # [AURA FIX] Ajustado para 'status_atual' conforme estrutura oficial MongoDB Atlas
    dados_atuais = usuario.get("status_atual", {})
    integracoes = usuario.get("integracoes", {})

    try:
        # 2. Coleta Real (Wearables + Atividades de Endurance)
        # O módulo 'sensores.py' retorna bio-sensores e também tipos de esportes detectados
        novos_dados = coletar_dados(user_id, integracoes)
        
        # Se não houver dados novos (ex: APIs externas offline)
        if not novos_dados:
            logger.info(f"ℹ️ Sem novos dados de sensores para o usuário {user_id}. Usando cache.")
            return dados_atuais

        # 3. Extração de Contexto para Treino Híbrido
        # Buscamos o que o atleta fez nos últimos 3 dias para a IA não errar na dose
        resumo_atividades = novos_dados.get("resumo_esportes", [])
        if resumo_atividades:
            if "status_atual" not in usuario:
                usuario["status_atual"] = {}
            usuario["status_atual"]["historico_recente_esportes"] = resumo_atividades

        # 4. Atualização de Estado (Merge Inteligente)
        if "status_atual" not in usuario:
            usuario["status_atual"] = {}

        # Fazemos o update dos campos bio (passos, sono, fc_repouso, hrv, etc)
        usuario["status_atual"].update({k: v for k, v in novos_dados.items() if k != "resumo_esportes"})
        
        # Sincronismo de tempo unificado
        usuario["status_atual"]["ultima_sincronizacao"] = datetime.now().isoformat()
        
        # 5. Persistência no MongoDB
        sucesso = salvar_memoria(user_id, usuario)
        
        if sucesso:
            logger.info(f"✅ Bio-status e contexto híbrido atualizados para {user_id}.")
        
        return usuario["status_atual"]

    except Exception as e:
        logger.error(f"❌ Erro crítico no orquestrador de sensores ({user_id}): {e}")
        # Segurança: Retorna cache em caso de falha catastrófica
        return dados_atuais

def obter_contexto_atividades_recentes(user_id: str, dias: int = 7) -> List[Dict[str, Any]]:
    """
    Função auxiliar para o logic.py.
    Recupera o que o usuário realmente treinou no Strava/Relógio para 
    personalizar a geração da planilha semanal de 10 exercícios.
    """
    usuario = carregar_memoria(user_id)
    if not usuario:
        return []
    
    status = usuario.get("status_atual", {})
    return status.get("historico_recente_esportes", [])

def atualizar_homeostase_pos_treino(user_id: str, esforço_percebido: int):
    """
    Ajusta o score de recuperação após o registro de um novo treino híbrido.
    Isso evita que a IA sugira treinos intensos se você acabou de destruir no cardio.
    """
    try:
        usuario = carregar_memoria(user_id)
        if not usuario: return
        
        # Incremento de fadiga baseado no esforço
        fadiga_atual = usuario.get("status_atual", {}).get("fadiga", 20)
        nova_fadiga = min(100, fadiga_atual + (esforço_percebido * 2))
        
        usuario["status_atual"]["fadiga"] = nova_fadiga
        salvar_memoria(user_id, usuario)
        logger.info(f"⚡ Homeostase recalibrada após treino para {user_id}.")
    except Exception as e:
        logger.error(f"⚠️ Erro ao recalibrar homeostase pos-treino: {e}")