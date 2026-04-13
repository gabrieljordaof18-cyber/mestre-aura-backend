# -*- coding: utf-8 -*-
"""
Paginas HTML publicas do Aura (site oficial no Render).
Rotas: /, /suporte, /privacidade, /termos (+ aliases Apple) e /health para JSON.

Variaveis opcionais no Render:
  AURA_PUBLIC_SITE_URL (default https://mestre-aura.onrender.com)
  AURA_SUPPORT_EMAIL, AURA_PRIVACY_EMAIL
  AURA_SOCIAL_INSTAGRAM_URL, AURA_SOCIAL_LINKEDIN_URL, AURA_SOCIAL_YOUTUBE_URL, AURA_SOCIAL_X_URL
"""
import os
from flask import Response, jsonify

_PUBLIC_SITE_URL = os.getenv("AURA_PUBLIC_SITE_URL", "https://mestre-aura.onrender.com").rstrip("/")
_SUPPORT_EMAIL = os.getenv("AURA_SUPPORT_EMAIL", "suporte@auraperformance.app")
_PRIVACY_EMAIL = os.getenv("AURA_PRIVACY_EMAIL", "privacidade@auraperformance.app")
_HOST_DISPLAY = _PUBLIC_SITE_URL.replace("https://", "").replace("http://", "")


def _nav_html(active_key: str) -> str:
    items = [
        ("/", "Início", "home"),
        ("/suporte", "Suporte", "suporte"),
        ("/privacidade", "Privacidade", "privacidade"),
        ("/termos", "Termos", "termos"),
    ]
    parts = []
    for href, label, key in items:
        cls = " nav-active" if key == active_key else ""
        parts.append(f'<a class="nav-link{cls}" href="{href}">{label}</a>')
    return "\n      ".join(parts)


def _social_links_html() -> str:
    pairs = [
        ("Instagram", os.getenv("AURA_SOCIAL_INSTAGRAM_URL", "").strip()),
        ("LinkedIn", os.getenv("AURA_SOCIAL_LINKEDIN_URL", "").strip()),
        ("YouTube", os.getenv("AURA_SOCIAL_YOUTUBE_URL", "").strip()),
        ("X (Twitter)", os.getenv("AURA_SOCIAL_X_URL", "").strip()),
    ]
    items = [
        f'<li><a href="{url}" rel="noopener noreferrer" target="_blank">{label}</a></li>'
        for label, url in pairs if url
    ]
    if not items:
        return (
            '<p class="subtitle" style="margin-top:12px">Redes sociais: defina '
            '<code style="color:#666">AURA_SOCIAL_INSTAGRAM_URL</code> (e outras) '
            "no painel do Render para exibir links aqui.</p>"
        )
    return '<ul class="social-list">' + "".join(items) + "</ul>"


def _wrap_page(browser_title: str, body: str, active_nav: str) -> str:
    nav = _nav_html(active_nav)
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <meta name="description" content="Aura Performance OS — performance atletica, biohacking e evolucao mensuravel."/>
  <title>{browser_title} — Aura Performance OS</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:#050505;color:#e5e5e5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;padding:0 0 72px;min-height:100vh}}
    .site-header{{position:sticky;top:0;z-index:20;background:rgba(5,5,5,.92);border-bottom:1px solid rgba(255,215,0,.18);backdrop-filter:blur(14px)}}
    .site-header-inner{{max-width:960px;margin:0 auto;padding:14px 20px;display:flex;flex-wrap:wrap;align-items:center;gap:12px 20px;justify-content:space-between}}
    .brand{{display:flex;flex-direction:column;gap:2px}}
    .brand a{{color:#FFD700;text-decoration:none;font-weight:800;font-size:18px;letter-spacing:.06em}}
    .brand span{{font-size:9px;text-transform:uppercase;letter-spacing:.14em;color:#555}}
    nav{{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center}}
    .nav-link{{color:#888;text-decoration:none;font-size:12px;font-weight:600;padding:6px 10px;border-radius:8px;transition:color .15s,background .15s}}
    .nav-link:hover{{color:#fff;background:rgba(255,215,0,.08)}}
    .nav-link.nav-active{{color:#000;background:#FFD700}}
    .hero{{max-width:680px;margin:0 auto;padding:32px 20px 0}}
    .hero-inner{{display:flex;gap:16px;align-items:flex-start;padding-bottom:24px;border-bottom:1px solid #151515}}
    .icon-box{{width:56px;height:56px;background:rgba(255,215,0,.08);border:1px solid rgba(255,215,0,.22);border-radius:16px;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800;color:#FFD700;flex-shrink:0}}
    h1{{font-size:20px;font-weight:700;color:#fff}}
    .version{{font-size:9px;text-transform:uppercase;letter-spacing:.14em;color:#555;margin-top:4px}}
    .subtitle{{font-size:11px;color:#888;margin-top:8px;line-height:1.65}}
    .content{{max-width:680px;margin:0 auto;padding:0 20px}}
    .highlight{{background:rgba(255,215,0,.05);border:1px solid rgba(255,215,0,.18);border-radius:14px;padding:18px;margin:24px 0}}
    .highlight .label{{font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:#FFD700;font-weight:700;margin-bottom:8px}}
    .highlight p{{font-size:11px;color:#ccc;line-height:1.75}}
    .apple-box{{background:#0c0c0c;border:1px solid #222;border-radius:12px;padding:16px;margin:0 0 24px;display:flex;gap:12px;align-items:flex-start}}
    .apple-box .ap-mark{{font-size:14px;font-weight:800;color:#FFD700;flex-shrink:0;margin-top:2px}}
    .apple-box .ap-title{{font-size:11px;color:#ddd;font-weight:700;margin-bottom:4px}}
    .apple-box .ap-text{{font-size:10px;color:#777;line-height:1.65}}
    section{{margin:28px 0}}
    .sec-header{{display:flex;align-items:center;gap:8px;margin-bottom:10px}}
    .sec-num{{font-size:11px;font-weight:800;color:#FFD700;min-width:1.2em}}
    h2{{font-size:13px;font-weight:700;color:#fff}}
    p,li{{font-size:11px;color:#888;line-height:1.75;white-space:pre-line}}
    ul{{padding-left:16px}}
    li{{margin:4px 0}}
    .contact-box{{background:#0a0a0a;border:1px solid rgba(255,215,0,.15);border-radius:12px;padding:20px;margin-top:32px}}
    .contact-label{{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:#FFD700;font-weight:700;margin-bottom:12px}}
    .contact-row{{display:flex;gap:8px;align-items:flex-start;margin:8px 0}}
    .contact-row .icon{{color:#555;font-size:13px;margin-top:1px}}
    .contact-row .ct{{font-size:11px;color:#888}}
    .contact-row .em{{font-size:11px;color:#fff;font-family:ui-monospace,monospace;word-break:break-all}}
    .divider{{height:1px;background:#151515;margin:10px 0}}
    .legal-note{{font-size:9px;color:#444;margin-top:8px}}
    .landing-wrap{{max-width:920px;margin:0 auto;padding:0 20px 40px}}
    .landing-hero{{padding:48px 0 40px;text-align:center;border-bottom:1px solid #151515}}
    .landing-hero h1{{font-size:clamp(28px,6vw,42px);font-weight:800;color:#fff;letter-spacing:-.02em;line-height:1.1}}
    .landing-hero .gold{{color:#FFD700}}
    .landing-hero p{{max-width:560px;margin:20px auto 0;font-size:14px;color:#9ca3af;line-height:1.7}}
    .landing-pills{{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-top:24px}}
    .pill{{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;padding:8px 14px;border-radius:999px;border:1px solid #2a2a2a;color:#a3a3a3;background:#0a0a0a}}
    .landing-section{{padding:44px 0;border-bottom:1px solid #151515}}
    .landing-section h2{{font-size:11px;text-transform:uppercase;letter-spacing:.16em;color:#FFD700;margin-bottom:16px}}
    .landing-section p{{font-size:13px;color:#a3a3a3;line-height:1.8;max-width:720px}}
    .landing-grid{{display:grid;gap:20px;margin-top:20px}}
    @media(min-width:640px){{.landing-grid{{grid-template-columns:1fr 1fr}}}}
    .card{{background:#0a0a0a;border:1px solid #1f1f1f;border-radius:16px;padding:22px}}
    .card h3{{font-size:15px;color:#fff;margin-bottom:10px}}
    .card p{{font-size:12px;color:#888;line-height:1.7}}
    .landing-cta{{padding:40px 0;text-align:center}}
    .btn-row{{display:flex;flex-wrap:wrap;gap:12px;justify-content:center;margin-top:20px}}
    .btn{{display:inline-block;padding:12px 22px;border-radius:12px;font-size:12px;font-weight:700;text-decoration:none;transition:opacity .12s}}
    .btn-primary{{background:#FFD700;color:#000}}
    .btn-primary:hover{{opacity:.92}}
    .btn-ghost{{border:1px solid #333;color:#ccc}}
    .btn-ghost:hover{{border-color:#FFD700;color:#FFD700}}
    .site-footer{{text-align:center;font-size:10px;color:#404040;margin-top:48px;padding:0 20px}}
    .site-footer a{{color:#666;text-decoration:none;margin:0 8px}}
    .site-footer a:hover{{color:#FFD700}}
    .social-list{{list-style:none;padding:0;margin:16px 0 0}}
    .social-list li{{margin:10px 0}}
    .social-list a{{color:#FFD700;font-size:13px;font-weight:600}}
    code{{font-size:10px}}
  </style>
</head>
<body>
<header class="site-header">
  <div class="site-header-inner">
    <div class="brand">
      <a href="/">AURA</a>
      <span>Performance OS · {_HOST_DISPLAY}</span>
    </div>
    <nav>
      {nav}
    </nav>
  </div>
</header>
{body}
<footer class="site-footer">
  <div>&copy; 2026 Aura Performance OS &middot; <a href="{_PUBLIC_SITE_URL}/privacidade">Privacidade</a> &middot; <a href="{_PUBLIC_SITE_URL}/termos">Termos</a> &middot; <a href="{_PUBLIC_SITE_URL}/suporte">Suporte</a></div>
</footer>
</body>
</html>"""


def _landing_body() -> str:
    u = _PUBLIC_SITE_URL
    return f"""
<div class="landing-wrap">
  <section class="landing-hero">
    <h1>Performance <span class="gold">mensuravel</span>. Evolucao <span class="gold">constante</span>.</h1>
    <p>O Aura Performance OS une treino, dados, gamificacao e orientacao inteligente para atletas que tratam o corpo como sistema — do sono ao pico de forca.</p>
    <div class="landing-pills">
      <span class="pill">Biohacking</span>
      <span class="pill">Forca e resistencia</span>
      <span class="pill">IA contextual</span>
      <span class="pill">Habito e ofensiva</span>
    </div>
    <div class="btn-row" style="margin-top:28px">
      <a class="btn btn-primary" href="{u}/suporte">Suporte e contato</a>
      <a class="btn btn-ghost" href="{u}/privacidade">Privacidade</a>
      <a class="btn btn-ghost" href="{u}/termos">Termos de uso</a>
    </div>
  </section>

  <section class="landing-section" id="quem-somos">
    <h2>Quem somos</h2>
    <p>Somos uma equipe focada em performance real — nao apenas estetica de feed. Construimos o Aura para quem treina com metodo: registra carga, respeita recuperacao e quer feedback que acompanha a rotina, nao o contrario.</p>
    <div class="landing-grid" style="margin-top:24px">
      <div class="card">
        <h3>Para atletas exigentes</h3>
        <p>Do iniciante consistente ao praticante avancado: linguagem direta, metricas claras e foco em progressao sustentavel.</p>
      </div>
      <div class="card">
        <h3>Tecnologia a servico do corpo</h3>
        <p>Integracao com fluxos modernos (App Store, dados seguros na nuvem) sem perder a simplicidade no dia a dia.</p>
      </div>
    </div>
  </section>

  <section class="landing-section" id="objetivos">
    <h2>Objetivos do Aura</h2>
    <p><strong style="color:#e5e5e5">1.</strong> Centralizar sua jornada — treinos, habitos e evolucao em um so ecossistema.<br/>
    <strong style="color:#e5e5e5">2.</strong> Traduzir esforco em clareza — XP, ofensivas e metas que mantem o engajamento honesto.<br/>
    <strong style="color:#e5e5e5">3.</strong> Respeitar sua privacidade — dados tratados com transparencia (veja nossa <a href="{u}/privacidade" style="color:#FFD700">Politica de Privacidade</a>).<br/>
    <strong style="color:#e5e5e5">4.</strong> Suporte acessivel — <a href="{u}/suporte" style="color:#FFD700">pagina de suporte</a>.</p>
  </section>

  <section class="landing-cta">
    <h2 style="margin-bottom:8px">Documentacao Apple e legal</h2>
    <p style="margin:0 auto;max-width:480px;font-size:12px">Links oficiais neste dominio ({_HOST_DISPLAY}) para revisao da App Store e transparencia com voce.</p>
    <div class="btn-row">
      <a class="btn btn-primary" href="{u}/privacidade">Politica de privacidade</a>
      <a class="btn btn-ghost" href="{u}/termos">EULA / Termos</a>
    </div>
  </section>
</div>
"""


def _support_body() -> str:
    social = _social_links_html()
    return f"""
<div class="hero">
  <div class="hero-inner">
    <div class="icon-box">S</div>
    <div>
      <h1>Suporte Aura</h1>
      <div class="version">Canal oficial &middot; {_HOST_DISPLAY}</div>
      <p class="subtitle">Duvidas sobre conta, assinatura (App Store), pedidos no Mercado Aura ou privacidade: use o e-mail abaixo.</p>
    </div>
  </div>
</div>
<div class="content">
  <div class="contact-box">
    <div class="contact-label">E-mail</div>
    <div class="contact-row"><span class="icon">&gt;</span><div><div class="ct">Suporte geral</div><div class="em"><a href="mailto:{_SUPPORT_EMAIL}" style="color:#FFD700;text-decoration:none">{_SUPPORT_EMAIL}</a></div></div></div>
    <div class="contact-row"><span class="icon">&gt;</span><div><div class="ct">Privacidade / DPO</div><div class="em"><a href="mailto:{_PRIVACY_EMAIL}" style="color:#FFD700;text-decoration:none">{_PRIVACY_EMAIL}</a></div></div></div>
    <div class="divider"></div>
    <div class="contact-label">Redes sociais</div>
    {social}
  </div>
  <div class="highlight" style="margin-top:28px">
    <div class="label">API e aplicativo</div>
    <p>Este site e servido pelo mesmo dominio da API em producao. O app movel Aura Performance OS referencia estas paginas nas telas legais.</p>
  </div>
</div>
"""


_PRIVACY_TEMPLATE = """
<div class="hero">
  <div class="hero-inner">
    <div class="icon-box">P</div>
    <div>
      <h1>Politica de Privacidade</h1>
      <div class="version">Versao 3.0 &middot; Ultima atualizacao: Marco de 2026</div>
      <p class="subtitle">Esta Politica descreve como coletamos, usamos e protegemos seus dados em conformidade com a LGPD (Lei n 13.709/2018) e as diretrizes da Apple App Store.</p>
    </div>
  </div>
</div>
<div class="content">
  <div class="highlight">
    <div class="label">Nosso Compromisso Fundamental</div>
    <p>A Aura Performance OS <strong style="color:#fff">nao vende, nao aluga e nao compartilha</strong> seus dados pessoais com terceiros para fins comerciais ou publicitarios. Seus dados existem para uma unica finalidade: acelerar sua evolucao.</p>
  </div>
  <div class="apple-box">
    <div class="ap-mark">A</div>
    <div>
      <div class="ap-title">Processamento de Pagamentos — Apple</div>
      <div class="ap-text">Todos os pagamentos de assinatura sao processados exclusivamente pela Apple App Store. A Aura Performance <strong style="color:#ccc">nao armazena dados de cartao de credito, debito ou qualquer informacao financeira</strong> do usuario.</div>
    </div>
  </div>
  <section><div class="sec-header"><span class="sec-num">1</span><h2>Controlador dos Dados</h2></div><p>A controladora dos dados e a Aura Performance, com sede no Brasil.
DPO: disponivel via {privacy_email}</p></section>
  <section><div class="sec-header"><span class="sec-num">2</span><h2>Dados que Coletamos</h2></div><p>Coletamos apenas o minimo necessario:
• Dados de conta: nome, e-mail e senha (hash bcrypt)
• Dados biometricos voluntarios: peso, altura, idade
• Foto de perfil (opcional)
• Dados de atividade: treinos, categorias, duracao, datas
• Dados de gamificacao: XP, moedas, cristais, missoes
• Dados tecnicos basicos para suporte</p></section>
  <section><div class="sec-header"><span class="sec-num">3</span><h2>Como Usamos seus Dados</h2></div><p>Seus dados sao usados exclusivamente para:
• Autenticar sua conta com seguranca (JWT)
• Personalizar planos de treino e nutricao via IA
• Calcular progresso, XP, nivel e gamificacao
• Processar pedidos no Mercado Aura
• Melhorar a experiencia no aplicativo

Nao usamos dados para publicidade de terceiros.</p></section>
  <section><div class="sec-header"><span class="sec-num">4</span><h2>Compartilhamento de Dados</h2></div><p>Compartilhamos apenas quando necessario:
• Infraestrutura: MongoDB Atlas e Render.com (SOC 2)
• Logistica: endereco de entrega para transportadoras
• Asaas (gateway PIX): nome, CPF e e-mail
• Exigencias legais por autoridade competente

Nunca vendemos dados. Nunca usamos para anuncios.</p></section>
  <section><div class="sec-header"><span class="sec-num">5</span><h2>Seguranca e Criptografia</h2></div><p>• Senhas com hash bcrypt (nunca em texto puro)
• Comunicacoes via HTTPS/TLS 1.3
• Tokens JWT com expiracao automatica
• Banco de dados com criptografia em repouso</p></section>
  <section><div class="sec-header"><span class="sec-num">6</span><h2>Retencao de Dados</h2></div><p>• Dados ativos mantidos enquanto a conta estiver ativa
• Conta excluida: remocao em ate 30 dias
• Dados de pedidos: retidos 5 anos (obrigacao fiscal)
• Backups: excluidos em ate 90 dias apos exclusao</p></section>
  <section><div class="sec-header"><span class="sec-num">7</span><h2>Seus Direitos (LGPD — Art. 18)</h2></div><p>• Confirmacao, acesso e correcao dos seus dados
• Anonimizacao ou exclusao de dados desnecessarios
• Portabilidade em formato legivel
• Revogacao do consentimento a qualquer momento
• Oposicao ao tratamento em casos especificos

Contato: {privacy_email}</p></section>
  <section><div class="sec-header"><span class="sec-num">8</span><h2>Exclusao de Conta</h2></div><p>Acesse: Perfil &rarr; Configuracoes &rarr; Excluir minha conta
Ou envie e-mail para: {privacy_email}
Prazo: dados removidos em ate 30 dias.</p></section>
  <section><div class="sec-header"><span class="sec-num">9</span><h2>Dados de Menores</h2></div><p>Nao coletamos dados de menores de 16 anos. Se identificarmos tal situacao, os dados serao excluidos imediatamente.</p></section>
  <section><div class="sec-header"><span class="sec-num">10</span><h2>Cookies e Rastreamento</h2></div><p>Usamos apenas localStorage para manter sessao ativa (token JWT). Sem cookies publicitarios, sem SDKs de rastreamento de terceiros.</p></section>
  <section><div class="sec-header"><span class="sec-num">11</span><h2>Transferencia Internacional</h2></div><p>Dados podem ser processados em servidores nos EUA (MongoDB Atlas / Render.com), ambos com certificacoes compativeis com a LGPD.</p></section>
  <div class="contact-box">
    <div class="contact-label">Contato e DPO</div>
    <div class="contact-row"><span class="icon">&gt;</span><div><div class="ct">Privacidade:</div><div class="em">{privacy_email}</div></div></div>
    <div class="contact-row"><span class="icon">&gt;</span><div><div class="ct">Suporte geral:</div><div class="em">{support_email}</div></div></div>
    <div class="divider"></div>
    <div class="legal-note">Prazo de resposta: ate 15 dias uteis — Art. 18, paragrafo 3 da LGPD.</div>
  </div>
</div>
"""

_TERMS_TEMPLATE = """
<div class="hero">
  <div class="hero-inner">
    <div class="icon-box">T</div>
    <div>
      <h1>Termos de Uso (EULA)</h1>
      <div class="version">Versao 3.0 &middot; Ultima atualizacao: Marco de 2026</div>
      <p class="subtitle">Este Contrato de Licenca de Usuario Final ("EULA") regula o uso do aplicativo Aura Performance OS. Ao instalar ou usar o aplicativo, voce concorda integralmente com estes termos.</p>
    </div>
  </div>
</div>
<div class="content">
  <div class="apple-box" style="margin-top:24px">
    <div class="ap-mark">A</div>
    <div>
      <div class="ap-title">Distribuido via Apple App Store</div>
      <div class="ap-text">Este aplicativo e distribuido pela Apple App Store. A Apple Inc. nao e parte deste contrato e nao tem responsabilidade pelo conteudo ou suporte do aplicativo.</div>
    </div>
  </div>
  <section><div class="sec-header"><span class="sec-num">1</span><h2>Concessao de Licenca</h2></div><p>A Aura Performance concede uma licenca pessoal, intransferivel, nao exclusiva e revogavel para usar o aplicativo em dispositivos Apple de sua propriedade, exclusivamente para fins pessoais e nao comerciais.</p></section>
  <section><div class="sec-header"><span class="sec-num">2</span><h2>Elegibilidade e Conta</h2></div><p>Uso permitido a pessoas com 16 anos ou mais. Voce e responsavel pela seguranca da sua conta e por todas as atividades realizadas nela.</p></section>
  <section><div class="sec-header"><span class="sec-num">3</span><h2>Assinaturas, Pagamentos e Cancelamento</h2></div><p>Os planos PLUS e PRO sao processados pela Apple App Store:
• Cobranca na conta Apple ID no momento da confirmacao
• Renovacao automatica ao final do periodo
• CANCELAMENTO: Ajustes do iPhone &rarr; [seu nome] &rarr; Assinaturas &rarr; Aura Performance &rarr; Cancelar
• Sem reembolso por periodos parciais (politica Apple)
• A Aura nao armazena dados de cartao de credito</p></section>
  <section><div class="sec-header"><span class="sec-num">4</span><h2>Conduta do Usuario — Tolerancia Zero</h2></div><p>E PROIBIDO:
• Publicar conteudo ofensivo, discriminatorio, pornografico ou ilegal
• Assediar, ameacar ou intimidar outros usuarios
• Usar o app para fraudes, spam ou atividades ilegais
• Acessar dados de outros usuarios sem autorizacao
• Reverter engenharia ou reproduzir o codigo-fonte

Contas infratoras serao suspensas ou excluidas permanentemente, sem aviso e sem reembolso.</p></section>
  <section><div class="sec-header"><span class="sec-num">5</span><h2>Conteudo do Usuario</h2></div><p>Ao enviar fotos ou dados, voce concede a Aura licenca limitada e nao exclusiva para usa-los exclusivamente para personalizar sua experiencia. Nao publicamos seu conteudo a terceiros.</p></section>
  <section><div class="sec-header"><span class="sec-num">6</span><h2>Saude e Isencao de Responsabilidade</h2></div><p>O Aura e uma plataforma informativa. As informacoes nao substituem diagnostico medico ou aconselhamento profissional. Consulte um medico antes de iniciar qualquer programa de exercicios. A Aura nao se responsabiliza por lesoes decorrentes do uso das informacoes fornecidas.</p></section>
  <section><div class="sec-header"><span class="sec-num">7</span><h2>Propriedade Intelectual</h2></div><p>Todo o conteudo do app — textos, imagens, codigo, design, marca Aura Performance — e propriedade exclusiva da Aura Performance e protegido por direitos autorais. Proibida reproducao sem autorizacao previa e escrita.</p></section>
  <section><div class="sec-header"><span class="sec-num">8</span><h2>Limitacao de Responsabilidade</h2></div><p>O aplicativo e fornecido "no estado em que se encontra" (as is). A Aura nao garante disponibilidade ininterrupta ou ausencia de erros. Nao nos responsabilizamos por danos indiretos, incidentais ou consequenciais.</p></section>
  <section><div class="sec-header"><span class="sec-num">9</span><h2>Rescisao</h2></div><p>Esta licenca e valida ate ser encerrada. Voce pode encerra-la desinstalando o aplicativo. A Aura pode revogar sua licenca imediatamente em caso de violacao destes Termos.</p></section>
  <section><div class="sec-header"><span class="sec-num">10</span><h2>Lei Aplicavel</h2></div><p>Estes Termos sao regidos pelas leis do Brasil. Foro eleito: Comarca de Goiania/GO.</p></section>
  <div class="contact-box">
    <div class="contact-label">Contato</div>
    <div class="contact-row"><span class="icon">&gt;</span><div><div class="ct">Suporte:</div><div class="em">{support_email}</div></div></div>
  </div>
</div>
"""


def register_public_routes(flask_app):
    """Registra rotas HTML publicas e health JSON."""

    @flask_app.route("/")
    def pagina_home():
        html = _wrap_page("Início", _landing_body(), "home")
        return Response(html, mimetype="text/html; charset=utf-8")

    @flask_app.route("/suporte")
    def pagina_suporte():
        html = _wrap_page("Suporte", _support_body(), "suporte")
        return Response(html, mimetype="text/html; charset=utf-8")

    @flask_app.route("/privacidade")
    @flask_app.route("/privacy")
    def pagina_privacidade():
        body = _PRIVACY_TEMPLATE.format(
            privacy_email=_PRIVACY_EMAIL, support_email=_SUPPORT_EMAIL
        )
        html = _wrap_page("Politica de Privacidade", body, "privacidade")
        return Response(html, mimetype="text/html; charset=utf-8")

    @flask_app.route("/termos")
    @flask_app.route("/terms")
    def pagina_termos():
        body = _TERMS_TEMPLATE.format(support_email=_SUPPORT_EMAIL)
        html = _wrap_page("Termos de Uso (EULA)", body, "termos")
        return Response(html, mimetype="text/html; charset=utf-8")

    @flask_app.route("/health")
    @flask_app.route("/api/health")
    def health_json():
        return jsonify(
            {
                "status": "online",
                "system": "Aura Performance OS",
                "version": "3.3.0-NATIVE-IAP",
                "public_site": _PUBLIC_SITE_URL,
                "env": os.getenv("FLASK_ENV", "production"),
                "engine": "Aura-Core-Hybrid-Engine",
                "features": [
                    "Marketplace",
                    "Melhor Envio Logistics",
                    "Asaas Gateway",
                    "RevenueCat Webhooks",
                    "Apple Auth Ready",
                    "Public site / /suporte /privacidade /termos",
                ],
            }
        )
