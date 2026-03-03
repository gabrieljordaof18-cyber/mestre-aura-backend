import logging
from datetime import datetime
from typing import Dict, Any, Optional

# Importações da Nova Arquitetura
from data_user import carregar_memoria, salvar_memoria
# O módulo 'sensores' será refatorado a seguir (Passo 19 da nossa lista)
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
    4. Realiza o merge seguro com o Schema 2.0[cite: 78].
    """
    if not user_id:
        logger.warning("⚠️ Tentativa de obter dados sem user_id.")
        return {}

    # 1. Carrega Perfil para obter Tokens de Integração
    usuario = carregar_memoria(user_id)
    if not usuario:
        logger.error(f"❌ Usuário {user_id} não encontrado para sync de sensores.")
        return {}

    # Pegamos o cache atual para fallback em caso de erro na API externa
    dados_atuais = usuario.get("dados_fisiologicos", {})
    integracoes = usuario.get("integracoes", {})

    try:
        # 2. Coleta Real (Passando o contexto de integração do usuário)
        # O módulo 'sensores.py' usará esses tokens para falar com Strava/Apple Health
        novos_dados = coletar_dados(user_id, integracoes)
        
        # Se não houver dados novos (ex: API fora do ar ou sem treinos novos)
        if not novos_dados:
            logger.info(f"ℹ️ Sem novos dados de sensores para o usuário {user_id}.")
            return dados_atuais

        # 3. Atualização de Estado (Merge Inteligente com Schema 2.0)
        # Garante que a chave existe antes de atualizar [cite: 78]
        if "dados_fisiologicos" not in usuario:
            usuario["dados_fisiologicos"] = {}

        # Fazemos o update apenas dos campos que vieram (passos, sono, fc, etc) [cite: 79]
        usuario["dados_fisiologicos"].update(novos_dados)
        
        # Padronização de data para ISO (Harmonia com o Resto do Backend)
        usuario["dados_fisiologicos"]["ultima_sincronizacao"] = datetime.now().isoformat()
        
        # 4. Persistência no MongoDB [cite: 85]
        # Removemos o _id internamente no salvar_memoria para evitar erros de imutabilidade
        sucesso = salvar_memoria(user_id, usuario)
        
        if sucesso:
            logger.info(f"✅ Bio-status atualizado com sucesso para {user_id}.")
        
        return usuario["dados_fisiologicos"]

    except Exception as e:
        logger.error(f"❌ Erro crítico no orquestrador de sensores ({user_id}): {e}")
        # Segurança: Nunca retorne vazio se houver cache, para não 'zerar' o app do usuário
        return dados_atuais