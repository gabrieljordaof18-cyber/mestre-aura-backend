import logging
from datetime import datetime
from typing import Dict, Any, Optional

# Importações da Nova Arquitetura
from data_user import carregar_memoria, salvar_memoria
# O módulo 'sensores' será refatorado a seguir para aceitar os argumentos novos
from sensores import coletar_dados 

# Configuração de Logs
logger = logging.getLogger("AURA_DATA_SENSORES")

# ======================================================
# ⚙️ ORQUESTRADOR DE DADOS FISIOLÓGICOS (SAAS)
# ======================================================

def obter_dados_fisiologicos(user_id: str) -> Dict[str, Any]:
    """
    1. Carrega o usuário.
    2. Pega os tokens de integração (Strava, etc).
    3. Chama a coleta externa.
    4. Atualiza o banco apenas se houver dados novos.
    """
    if not user_id:
        logger.warning("⚠️ Tentativa de obter dados sem user_id.")
        return {}

    # 1. Carrega Perfil para obter Tokens
    usuario = carregar_memoria(user_id)
    if not usuario:
        return {}

    dados_atuais = usuario.get("dados_fisiologicos", {})
    integracoes = usuario.get("integracoes", {})

    try:
        # 2. Coleta Real (Passando contexto do usuário)
        # A função coletar_dados agora receberá o ID e as configurações de integração
        novos_dados = coletar_dados(user_id, integracoes)
        
        # Se retornou None ou vazio, significa que não houve sincronização nova
        if not novos_dados:
            # Retorna o cache atual para não quebrar o frontend
            return dados_atuais

        # 3. Atualização de Estado (Merge Inteligente)
        if "dados_fisiologicos" not in usuario:
            usuario["dados_fisiologicos"] = {}

        # Atualiza apenas os campos retornados
        usuario["dados_fisiologicos"].update(novos_dados)
        usuario["dados_fisiologicos"]["ultima_sincronizacao"] = str(datetime.now())
        
        # 4. Salva no Banco (Sem logs internos inúteis)
        sucesso = salvar_memoria(user_id, usuario)
        
        if sucesso:
            logger.info(f"✅ Dados fisiológicos atualizados para user {user_id}")
        
        return usuario["dados_fisiologicos"]

    except Exception as e:
        logger.error(f"❌ Erro ao processar sensores para {user_id}: {e}")
        # Em caso de erro, Fallback para dados em cache (nunca inventar dados)
        return dados_atuais