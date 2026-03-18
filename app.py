import os
import logging
from flask import Flask, jsonify, request
from flask_cors import CORS

from rotas_api import api_bp
from rotas_strava import strava_bp

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AURA_APP")

app = Flask(__name__)

# ===================================================
# 🔐 CORS — CONFIGURAÇÃO ULTRA-ROBUSTA PARA IOS
# ===================================================
# Permitimos origins="*" temporariamente para garantir que o 
# handshake do Capacitor (OPTIONS) não retorne 404/403.

_CORS_HEADERS = [
    "Authorization",
    "Content-Type",
    "X-Requested-With",
    "X-Apple-IAP-Id",
    "X-RevenueCat-ETag"
]

CORS(app, resources={
    # Rotas de webhook abertas para servidores externos
    r"/api/webhook/*": {
        "origins": "*",
        "allow_headers": _CORS_HEADERS,
        "methods": ["POST", "OPTIONS"]
    },
    # Ajuste para garantir que o iPhone (capacitor://localhost) seja aceito
    r"/*": {
        "origins": "*",  # Em produção, o ideal é filtrar, mas para o Fix do Login usamos "*"
        "allow_headers": _CORS_HEADERS,
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "expose_headers": ["Content-Range", "X-Content-Range"],
        "supports_credentials": True
    }
})

# 2. Registro de Rotas (Blueprints)
# Registramos com o prefixo /api. 
# Se no rotas_api.py a rota for /auth/register, ela vira /api/auth/register
app.register_blueprint(api_bp, url_prefix='/api')
app.register_blueprint(strava_bp, url_prefix='/strava')

# [AURA DEBUG] Lista todas as rotas no log do Render ao iniciar
with app.app_context():
    logger.info("📍 Mapeamento de Rotas Ativo:")
    for rule in app.url_map.iter_rules():
        logger.info(f"Rota: {rule.rule} | Métodos: {rule.methods}")

# ===================================================
# 📄 PÁGINAS LEGAIS PÚBLICAS (Apple App Store)
# URLs: /privacidade  e  /termos
# ===================================================

_HTML_BASE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{title} — Aura Performance OS</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:#000;color:#e5e5e5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:0 0 60px}}
    header{{position:sticky;top:0;background:rgba(0,0,0,.95);border-bottom:1px solid rgba(255,215,0,.15);padding:16px 20px;display:flex;align-items:center;gap:12px;backdrop-filter:blur(12px);z-index:10}}
    header a{{color:#999;text-decoration:none;font-size:13px}}
    header a:hover{{color:#fff}}
    .badge{{font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:#666;margin-top:2px}}
    .hero{{max-width:680px;margin:0 auto;padding:32px 20px 0}}
    .hero-inner{{display:flex;gap:16px;align-items:flex-start;padding-bottom:24px;border-bottom:1px solid #111}}
    .icon-box{{width:56px;height:56px;background:rgba(255,215,0,.08);border:1px solid rgba(255,215,0,.2);border-radius:16px;display:flex;align-items:center;justify-content:center;font-size:24px;flex-shrink:0}}
    h1{{font-size:20px;font-weight:700;color:#fff}}
    .version{{font-size:9px;text-transform:uppercase;letter-spacing:.14em;color:#555;margin-top:4px}}
    .subtitle{{font-size:11px;color:#888;margin-top:8px;line-height:1.6}}
    .content{{max-width:680px;margin:0 auto;padding:0 20px}}
    .highlight{{background:rgba(255,215,0,.04);border:1px solid rgba(255,215,0,.15);border-radius:12px;padding:16px;margin:24px 0}}
    .highlight .label{{font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:#FFD700;font-weight:700;margin-bottom:6px}}
    .highlight p{{font-size:11px;color:#ccc;line-height:1.7}}
    .apple-box{{background:#111;border:1px solid #222;border-radius:12px;padding:16px;margin:0 0 24px;display:flex;gap:12px;align-items:flex-start}}
    .apple-box .ap-icon{{font-size:18px;flex-shrink:0;margin-top:2px}}
    .apple-box .ap-title{{font-size:11px;color:#ddd;font-weight:700;margin-bottom:4px}}
    .apple-box .ap-text{{font-size:10px;color:#666;line-height:1.6}}
    section{{margin:28px 0}}
    .sec-header{{display:flex;align-items:center;gap:8px;margin-bottom:10px}}
    .sec-icon{{font-size:13px;color:#FFD700}}
    h2{{font-size:13px;font-weight:700;color:#fff}}
    p,li{{font-size:11px;color:#888;line-height:1.75;white-space:pre-line}}
    ul{{padding-left:16px}}
    li{{margin:2px 0}}
    .contact-box{{background:#0a0a0a;border:1px solid rgba(255,215,0,.15);border-radius:12px;padding:20px;margin-top:32px}}
    .contact-label{{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:#FFD700;font-weight:700;margin-bottom:12px}}
    .contact-row{{display:flex;gap:8px;align-items:flex-start;margin:8px 0}}
    .contact-row .icon{{color:#555;font-size:13px;margin-top:1px}}
    .contact-row .ct{{font-size:11px;color:#888}}
    .contact-row .em{{font-size:11px;color:#fff;font-family:monospace}}
    .divider{{height:1px;background:#111;margin:8px 0}}
    .legal-note{{font-size:9px;color:#444;margin-top:8px}}
    footer{{text-align:center;font-size:9px;color:#333;margin-top:40px}}
  </style>
</head>
<body>
<header>
  <a href="/">← Aura Performance</a>
  <div style="flex:1"></div>
  <div style="text-align:right">
    <div style="font-size:12px;color:#fff;font-weight:700">{title}</div>
    <div class="badge">Aura Performance OS</div>
  </div>
</header>
{body}
<footer>© 2026 Aura Performance OS. Todos os direitos reservados.</footer>
</body>
</html>"""

_PRIVACY_BODY = """
<div class="hero">
  <div class="hero-inner">
    <div class="icon-box">🔒</div>
    <div>
      <h1>Política de Privacidade</h1>
      <div class="version">Versão 3.0 · Última atualização: Março de 2026</div>
      <p class="subtitle">Esta Política descreve como coletamos, usamos e protegemos seus dados em conformidade com a LGPD (Lei nº 13.709/2018) e as diretrizes da Apple App Store.</p>
    </div>
  </div>
</div>
<div class="content">
  <div class="highlight">
    <div class="label">Nosso Compromisso Fundamental</div>
    <p>A Aura Performance OS <strong style="color:#fff">não vende, não aluga e não compartilha</strong> seus dados pessoais com terceiros para fins comerciais ou publicitários. Seus dados existem para uma única finalidade: acelerar sua evolução.</p>
  </div>
  <div class="apple-box">
    <div class="ap-icon">🍎</div>
    <div>
      <div class="ap-title">Processamento de Pagamentos — Apple</div>
      <div class="ap-text">Todos os pagamentos de assinatura são processados exclusivamente pela Apple App Store. A Aura Performance <strong style="color:#ccc">não armazena dados de cartão de crédito, débito ou qualquer informação financeira</strong> do usuário.</div>
    </div>
  </div>
  <section><div class="sec-header"><span class="sec-icon">🌐</span><h2>1. Controlador dos Dados</h2></div><p>A controladora dos dados é a Aura Performance, com sede no Brasil.\nDPO: disponível via privacidade@auraperformance.app</p></section>
  <section><div class="sec-header"><span class="sec-icon">🗄️</span><h2>2. Dados que Coletamos</h2></div><p>Coletamos apenas o mínimo necessário:\n• Dados de conta: nome, e-mail e senha (hash bcrypt)\n• Dados biométricos voluntários: peso, altura, idade\n• Foto de perfil (opcional)\n• Dados de atividade: treinos, categorias, duração, datas\n• Dados de gamificação: XP, moedas, cristais, missões\n• Dados técnicos básicos para suporte</p></section>
  <section><div class="sec-header"><span class="sec-icon">👁️</span><h2>3. Como Usamos seus Dados</h2></div><p>Seus dados são usados exclusivamente para:\n• Autenticar sua conta com segurança (JWT)\n• Personalizar planos de treino e nutrição via IA\n• Calcular progresso, XP, nível e gamificação\n• Processar pedidos no Mercado Aura\n• Melhorar a experiência no aplicativo\n\nNão usamos dados para publicidade de terceiros.</p></section>
  <section><div class="sec-header"><span class="sec-icon">🌐</span><h2>4. Compartilhamento de Dados</h2></div><p>Compartilhamos apenas quando necessário:\n• Infraestrutura: MongoDB Atlas e Render.com (SOC 2)\n• Logística: endereço de entrega para transportadoras\n• Asaas (gateway PIX): nome, CPF e e-mail\n• Exigências legais por autoridade competente\n\nNunca vendemos dados. Nunca usamos para anúncios.</p></section>
  <section><div class="sec-header"><span class="sec-icon">🔒</span><h2>5. Segurança e Criptografia</h2></div><p>• Senhas com hash bcrypt (nunca em texto puro)\n• Comunicações via HTTPS/TLS 1.3\n• Tokens JWT com expiração automática\n• Banco de dados com criptografia em repouso</p></section>
  <section><div class="sec-header"><span class="sec-icon">🗄️</span><h2>6. Retenção de Dados</h2></div><p>• Dados ativos mantidos enquanto a conta estiver ativa\n• Conta excluída: remoção em até 30 dias\n• Dados de pedidos: retidos 5 anos (obrigação fiscal)\n• Backups: excluídos em até 90 dias após exclusão</p></section>
  <section><div class="sec-header"><span class="sec-icon">👁️</span><h2>7. Seus Direitos (LGPD — Art. 18)</h2></div><p>• Confirmação, acesso e correção dos seus dados\n• Anonimização ou exclusão de dados desnecessários\n• Portabilidade em formato legível\n• Revogação do consentimento a qualquer momento\n• Oposição ao tratamento em casos específicos\n\nContato: privacidade@auraperformance.app</p></section>
  <section><div class="sec-header"><span class="sec-icon">🗑️</span><h2>8. Exclusão de Conta</h2></div><p>Acesse: Perfil → Configurações → Excluir minha conta\nOu envie e-mail para: privacidade@auraperformance.app\nPrazo: dados removidos em até 30 dias.</p></section>
  <section><div class="sec-header"><span class="sec-icon">🌐</span><h2>9. Dados de Menores</h2></div><p>Não coletamos dados de menores de 16 anos. Se identificarmos tal situação, os dados serão excluídos imediatamente.</p></section>
  <section><div class="sec-header"><span class="sec-icon">👁️</span><h2>10. Cookies e Rastreamento</h2></div><p>Usamos apenas localStorage para manter sessão ativa (token JWT). Sem cookies publicitários, sem SDKs de rastreamento de terceiros.</p></section>
  <section><div class="sec-header"><span class="sec-icon">🌐</span><h2>11. Transferência Internacional</h2></div><p>Dados podem ser processados em servidores nos EUA (MongoDB Atlas / Render.com), ambos com certificações compatíveis com a LGPD.</p></section>
  <div class="contact-box">
    <div class="contact-label">Contato &amp; DPO</div>
    <div class="contact-row"><span class="icon">✉️</span><div><div class="ct">Privacidade:</div><div class="em">privacidade@auraperformance.app</div></div></div>
    <div class="contact-row"><span class="icon">✉️</span><div><div class="ct">Suporte geral:</div><div class="em">suporte@auraperformance.app</div></div></div>
    <div class="divider"></div>
    <div class="legal-note">Prazo de resposta: até 15 dias úteis — Art. 18, §3º da LGPD.</div>
  </div>
</div>
"""

_TERMS_BODY = """
<div class="hero">
  <div class="hero-inner">
    <div class="icon-box">🛡️</div>
    <div>
      <h1>Termos de Uso (EULA)</h1>
      <div class="version">Versão 3.0 · Última atualização: Março de 2026</div>
      <p class="subtitle">Este Contrato de Licença de Usuário Final ("EULA") regula o uso do aplicativo Aura Performance OS. Ao instalar ou usar o aplicativo, você concorda integralmente com estes termos.</p>
    </div>
  </div>
</div>
<div class="content">
  <div class="apple-box" style="margin-top:24px">
    <div class="ap-icon">🍎</div>
    <div>
      <div class="ap-title">Distribuído via Apple App Store</div>
      <div class="ap-text">Este aplicativo é distribuído pela Apple App Store. A Apple Inc. não é parte deste contrato e não tem responsabilidade pelo conteúdo ou suporte do aplicativo.</div>
    </div>
  </div>
  <section><div class="sec-header"><span class="sec-icon">📄</span><h2>1. Concessão de Licença</h2></div><p>A Aura Performance concede uma licença pessoal, intransferível, não exclusiva e revogável para usar o aplicativo em dispositivos Apple de sua propriedade, exclusivamente para fins pessoais e não comerciais.</p></section>
  <section><div class="sec-header"><span class="sec-icon">🛡️</span><h2>2. Elegibilidade e Conta</h2></div><p>Uso permitido a pessoas com 16 anos ou mais. Você é responsável pela segurança da sua conta e por todas as atividades realizadas nela.</p></section>
  <section><div class="sec-header"><span class="sec-icon">💳</span><h2>3. Assinaturas, Pagamentos e Cancelamento</h2></div><p>Os planos PLUS e PRÓ são processados pela Apple App Store:\n• Cobrança na conta Apple ID no momento da confirmação\n• Renovação automática ao final do período\n• CANCELAMENTO: Ajustes do iPhone → [seu nome] → Assinaturas → Aura Performance → Cancelar\n• Sem reembolso por períodos parciais (política Apple)\n• A Aura não armazena dados de cartão de crédito</p></section>
  <section><div class="sec-header"><span class="sec-icon">⚠️</span><h2>4. Conduta do Usuário — Tolerância Zero</h2></div><p>É PROIBIDO:\n• Publicar conteúdo ofensivo, discriminatório, pornográfico ou ilegal\n• Assediar, ameaçar ou intimidar outros usuários\n• Usar o app para fraudes, spam ou atividades ilegais\n• Acessar dados de outros usuários sem autorização\n• Reverter engenharia ou reproduzir o código-fonte\n\nContas infratoras serão suspensas ou excluídas permanentemente, sem aviso e sem reembolso.</p></section>
  <section><div class="sec-header"><span class="sec-icon">📄</span><h2>5. Conteúdo do Usuário</h2></div><p>Ao enviar fotos ou dados, você concede à Aura licença limitada e não exclusiva para usá-los exclusivamente para personalizar sua experiência. Não publicamos seu conteúdo a terceiros.</p></section>
  <section><div class="sec-header"><span class="sec-icon">📄</span><h2>6. Saúde e Isenção de Responsabilidade</h2></div><p>O Aura é uma plataforma informativa. As informações não substituem diagnóstico médico ou aconselhamento profissional. Consulte um médico antes de iniciar qualquer programa de exercícios. A Aura não se responsabiliza por lesões decorrentes do uso das informações fornecidas.</p></section>
  <section><div class="sec-header"><span class="sec-icon">📄</span><h2>7. Propriedade Intelectual</h2></div><p>Todo o conteúdo do app — textos, imagens, código, design, marca "Aura Performance" — é propriedade exclusiva da Aura Performance e protegido por direitos autorais. Proibida reprodução sem autorização prévia e escrita.</p></section>
  <section><div class="sec-header"><span class="sec-icon">📄</span><h2>8. Limitação de Responsabilidade</h2></div><p>O aplicativo é fornecido "no estado em que se encontra" (as is). A Aura não garante disponibilidade ininterrupta ou ausência de erros. Não nos responsabilizamos por danos indiretos, incidentais ou consequenciais.</p></section>
  <section><div class="sec-header"><span class="sec-icon">📄</span><h2>9. Rescisão</h2></div><p>Esta licença é válida até ser encerrada. Você pode encerrá-la desinstalando o aplicativo. A Aura pode revogar sua licença imediatamente em caso de violação destes Termos.</p></section>
  <section><div class="sec-header"><span class="sec-icon">📄</span><h2>10. Lei Aplicável</h2></div><p>Estes Termos são regidos pelas leis do Brasil. Foro eleito: Comarca de Goiânia/GO.</p></section>
  <div class="contact-box">
    <div class="contact-label">Contato</div>
    <div class="contact-row"><span class="icon">✉️</span><div><div class="ct">Suporte:</div><div class="em">suporte@auraperformance.app</div></div></div>
  </div>
</div>
"""

@app.route('/privacidade')
@app.route('/privacy')
def pagina_privacidade():
    """Política de Privacidade pública — exigida pela Apple App Store."""
    from flask import Response
    html = _HTML_BASE.format(title="Política de Privacidade", body=_PRIVACY_BODY)
    return Response(html, mimetype='text/html')

@app.route('/termos')
@app.route('/terms')
def pagina_termos():
    """Termos de Uso (EULA) público — exigido pela Apple App Store."""
    from flask import Response
    html = _HTML_BASE.format(title="Termos de Uso (EULA)", body=_TERMS_BODY)
    return Response(html, mimetype='text/html')

# 3. Rota Raiz (Health Check & Version Control)
@app.route('/')
def health_check():
    return jsonify({
        "status": "online",
        "system": "Aura Performance OS",
        "version": "3.3.0-NATIVE-IAP",
        "env": os.getenv("FLASK_ENV", "production"),
        "engine": "Aura-Core-Hybrid-Engine",
        "features": [
            "Marketplace", 
            "Melhor Envio Logistics", 
            "Asaas Gateway", 
            "RevenueCat Webhooks", 
            "Apple Auth Ready"
        ]
    })

# 4. Tratamento Global de Erros
@app.errorhandler(404)
def not_found(e):
    logger.warning(f"⚠️ Rota não encontrada: {request.path} [MÉTODO: {request.method}]")
    return jsonify({"erro": f"Rota {request.path} não encontrada no Aura OS"}), 404

@app.errorhandler(400)
def bad_request(e):
    return jsonify({"erro": "Requisição mal formatada ou parâmetros ausentes"}), 400

@app.errorhandler(500)
def server_error(e):
    logger.error(f"❌ Erro Crítico Interno: {e}")
    return jsonify({"erro": "Falha interna no servidor Aura. Verifique os logs no Render."}), 500

# Verificação de Variáveis de Ambiente
if not os.getenv("MONGODB_URI"):
    logger.warning("⚠️ MONGODB_URI não detectada!")

if not os.getenv("MELHOR_ENVIO_TOKEN"):
    logger.warning("⚠️ MELHOR_ENVIO_TOKEN ausente!")

# [AURA LOCAL LAUNCH]
if __name__ == '__main__':
    port = int(os.getenv("PORT", 5050)) 
    logger.info(f"🚀 Aura OS Híbrido iniciando localmente na porta {port}...")
    app.run(host='0.0.0.0', port=port, debug=True)