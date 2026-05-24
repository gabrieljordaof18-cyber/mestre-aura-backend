# -*- coding: utf-8 -*-
"""
Painel administrativo de pedidos do Marketplace AURA Performance.

Rotas (prefixo /admin registrado em app.py):
  GET  /admin/login         — formulário de acesso
  POST /admin/login         — valida senha, seta session['admin']
  GET  /admin/logout        — limpa session, redireciona para login
  GET  /admin/pedidos       — listagem principal com filtros
  POST /admin/pedidos/<id>/encaminhar — muda status → ENVIADO_FORNECEDOR
  POST /admin/pedidos/<id>/rastreio   — salva código + muda → RASTREIO_GERADO
  POST /admin/pedidos/<id>/entregue   — muda status → ENTREGUE

Variável de ambiente obrigatória:
  ADMIN_SECRET_KEY  — senha estática do painel
"""
import os
import logging
from functools import wraps
from datetime import datetime

from flask import (
    Blueprint, session, redirect, request,
    render_template_string,
)
from bson.objectid import ObjectId

from data_manager import mongo_db

logger = logging.getLogger("AURA_ADMIN")

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ===================================================
# DECORADOR DE AUTENTICAÇÃO
# ===================================================

def _admin_required(f):
    @wraps(f)
    def _decorated(*args, **kwargs):
        if not session.get("admin"):
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return _decorated


# ===================================================
# HELPERS
# ===================================================

def _buscar_nome_usuario(user_id: str) -> str:
    """Retorna o nome do usuário na coleção 'usuarios' pelo user_id."""
    if not user_id or mongo_db is None:
        return "Desconhecido"
    try:
        doc = mongo_db["usuarios"].find_one(
            {"_id": ObjectId(user_id)},
            {"nome": 1, "cpf": 1}
        )
        if doc:
            return doc.get("nome") or "Sem nome"
        return "Não encontrado"
    except Exception:
        return "—"


def _buscar_cpf_usuario(user_id: str) -> str:
    """Retorna o CPF do usuário se disponível."""
    if not user_id or mongo_db is None:
        return ""
    try:
        doc = mongo_db["usuarios"].find_one(
            {"_id": ObjectId(user_id)},
            {"cpf": 1}
        )
        return doc.get("cpf", "") if doc else ""
    except Exception:
        return ""


def _formatar_endereco(end: dict) -> dict:
    """Garante que todos os campos de endereço sejam strings."""
    if not end:
        return {}
    return {
        "rua": end.get("rua") or end.get("logradouro") or "—",
        "numero": end.get("numero") or "S/N",
        "complemento": end.get("complemento") or "",
        "bairro": end.get("bairro") or "—",
        "cidade": end.get("cidade") or "—",
        "estado": end.get("estado") or end.get("uf") or "—",
        "cep": end.get("cep") or "—",
    }


# ===================================================
# TEMPLATE — LOGIN
# ===================================================

_LOGIN_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Admin — AURA Performance</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-black min-h-screen flex items-center justify-center p-4">
  <div class="w-full max-w-sm">
    <div class="text-center mb-10">
      <h1 class="text-4xl font-black tracking-widest" style="color:#FFD700">AURA</h1>
      <p class="text-xs text-gray-500 uppercase tracking-widest mt-2">Performance OS &middot; Painel Admin</p>
    </div>
    <div class="bg-[#0f0f0f] border border-gray-800 rounded-2xl p-8 shadow-2xl">
      {% if error %}
      <div class="mb-5 p-3 rounded-lg border text-xs" style="background:rgba(239,68,68,.08);border-color:rgba(239,68,68,.3);color:#f87171">
        {{ error }}
      </div>
      {% endif %}
      <form method="POST" action="/admin/login">
        <label class="block text-xs text-gray-400 uppercase tracking-widest mb-2">Senha de Acesso</label>
        <input type="password" name="senha" required autofocus
          class="w-full bg-black border border-gray-700 text-white rounded-xl px-4 py-3 text-sm focus:outline-none mb-5"
          style="transition:border-color .15s"
          onfocus="this.style.borderColor='#FFD700'" onblur="this.style.borderColor=''"/>
        <button type="submit"
          class="w-full py-3 font-black text-sm rounded-xl transition-opacity hover:opacity-90"
          style="background:#FFD700;color:#000">
          Entrar no Painel
        </button>
      </form>
    </div>
  </div>
</body>
</html>"""


# ===================================================
# TEMPLATE — PAINEL DE PEDIDOS
# ===================================================

_PEDIDOS_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Pedidos — AURA Admin</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    * { box-sizing: border-box; }
    body { background: #050505; }
    .badge { display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;border:1px solid;font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase; }
    .badge-gray   { background:rgba(107,114,128,.15);color:#9ca3af;border-color:rgba(107,114,128,.3); }
    .badge-blue   { background:rgba(59,130,246,.15);color:#60a5fa;border-color:rgba(59,130,246,.3); }
    .badge-yellow { background:rgba(234,179,8,.15);color:#facc15;border-color:rgba(234,179,8,.3); }
    .badge-orange { background:rgba(249,115,22,.15);color:#fb923c;border-color:rgba(249,115,22,.3); }
    .badge-green  { background:rgba(34,197,94,.15);color:#4ade80;border-color:rgba(34,197,94,.3); }
    .badge-red    { background:rgba(239,68,68,.15);color:#f87171;border-color:rgba(239,68,68,.3); }
    .btn-gold { background:#FFD700;color:#000;font-weight:800;font-size:12px;padding:8px 16px;border-radius:10px;cursor:pointer;border:none;transition:opacity .15s; }
    .btn-gold:hover { opacity:.88; }
    .btn-outline { background:transparent;color:#9ca3af;font-weight:700;font-size:12px;padding:7px 14px;border-radius:10px;cursor:pointer;border:1px solid #374151;transition:all .15s; }
    .btn-outline:hover { border-color:#FFD700;color:#FFD700; }
    .btn-blue { background:rgba(59,130,246,.1);color:#60a5fa;font-weight:700;font-size:12px;padding:7px 14px;border-radius:10px;cursor:pointer;border:1px solid rgba(59,130,246,.3);transition:all .15s; }
    .btn-blue:hover { background:rgba(59,130,246,.2); }
    .btn-green { background:rgba(34,197,94,.1);color:#4ade80;font-weight:700;font-size:12px;padding:7px 14px;border-radius:10px;cursor:pointer;border:1px solid rgba(34,197,94,.3);transition:all .15s; }
    .btn-green:hover { background:rgba(34,197,94,.2); }
    input[type=text], input[type=search], select {
      background:#0a0a0a;border:1px solid #374151;color:#e5e5e5;border-radius:10px;
      padding:8px 12px;font-size:13px;outline:none;
    }
    input[type=text]:focus, input[type=search]:focus, select:focus { border-color:#FFD700; }
    .card { background:#0f0f0f;border:1px solid #1f2937;border-radius:16px;padding:20px;transition:border-color .15s; }
    .card:hover { border-color:#374151; }
    .divider { height:1px;background:#1f2937;margin:14px 0; }
    pre { white-space:pre-wrap;word-break:break-word; }
    .modal-overlay { position:fixed;inset:0;background:rgba(0,0,0,.85);backdrop-filter:blur(8px);z-index:50;display:flex;align-items:center;justify-content:center;padding:24px; }
    .modal-box { background:#0f0f0f;border:1px solid #374151;border-radius:20px;padding:28px;width:100%;max-width:560px;max-height:90vh;overflow-y:auto;position:relative; }
  </style>
</head>
<body class="text-white min-h-screen">

<!-- ============ HEADER ============ -->
<header style="position:sticky;top:0;z-index:30;background:rgba(5,5,5,.96);border-bottom:1px solid rgba(255,215,0,.15);backdrop-filter:blur(12px)">
  <div style="max-width:1400px;margin:0 auto;padding:14px 24px;display:flex;align-items:center;justify-content:space-between;gap:16px">
    <div>
      <span style="font-size:22px;font-weight:900;letter-spacing:.12em;color:#FFD700">AURA</span>
      <span style="font-size:10px;color:#6b7280;text-transform:uppercase;letter-spacing:.1em;margin-left:10px">Performance OS &middot; Admin</span>
    </div>
    <div style="display:flex;align-items:center;gap:12px">
      <a href="/admin/pedidos" style="font-size:12px;color:#FFD700;font-weight:700;padding:5px 12px;border:1px solid rgba(255,215,0,.3);border-radius:8px;text-decoration:none">Pedidos</a>
      <a href="/admin/profissionais" style="font-size:12px;color:#9ca3af;font-weight:600;padding:5px 12px;border:1px solid #374151;border-radius:8px;text-decoration:none" onmouseover="this.style.color='#FFD700'" onmouseout="this.style.color='#9ca3af'">Profissionais</a>
      <span style="font-size:11px;color:#6b7280">{{ pedidos|length }} pedido(s)</span>
      <a href="/admin/logout"
        style="font-size:11px;color:#9ca3af;padding:6px 14px;border:1px solid #374151;border-radius:8px;text-decoration:none;transition:color .15s"
        onmouseover="this.style.color='#FFD700'" onmouseout="this.style.color='#9ca3af'">
        Sair
      </a>
    </div>
  </div>
</header>

<!-- ============ FILTROS ============ -->
<div style="max-width:1400px;margin:0 auto;padding:20px 24px 0">
  <form method="GET" action="/admin/pedidos"
    style="display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;background:#0a0a0a;border:1px solid #1f2937;border-radius:14px;padding:16px 20px">
    <div style="display:flex;flex-direction:column;gap:4px">
      <label style="font-size:10px;color:#6b7280;text-transform:uppercase;letter-spacing:.08em">Status</label>
      <select name="status" style="min-width:180px">
        <option value="">Todos os status</option>
        <option value="PENDING"            {% if filtro_status == 'PENDING' %}selected{% endif %}>PENDING</option>
        <option value="PAGO"               {% if filtro_status == 'PAGO' %}selected{% endif %}>PAGO</option>
        <option value="ENVIADO_FORNECEDOR" {% if filtro_status == 'ENVIADO_FORNECEDOR' %}selected{% endif %}>ENVIADO_FORNECEDOR</option>
        <option value="RASTREIO_GERADO"    {% if filtro_status == 'RASTREIO_GERADO' %}selected{% endif %}>RASTREIO_GERADO</option>
        <option value="ENTREGUE"           {% if filtro_status == 'ENTREGUE' %}selected{% endif %}>ENTREGUE</option>
        <option value="CANCELADO"          {% if filtro_status == 'CANCELADO' %}selected{% endif %}>CANCELADO</option>
      </select>
    </div>
    <div style="display:flex;flex-direction:column;gap:4px">
      <label style="font-size:10px;color:#6b7280;text-transform:uppercase;letter-spacing:.08em">Fornecedor</label>
      <select name="fornecedor" style="min-width:160px">
        <option value="">Todos</option>
        <option value="roupas"       {% if filtro_fornecedor == 'roupas' %}selected{% endif %}>Roupas</option>
        <option value="suplementos"  {% if filtro_fornecedor == 'suplementos' %}selected{% endif %}>Suplementos</option>
      </select>
    </div>
    <div style="display:flex;flex-direction:column;gap:4px;flex:1;min-width:220px">
      <label style="font-size:10px;color:#6b7280;text-transform:uppercase;letter-spacing:.08em">Buscar</label>
      <input type="search" name="busca" value="{{ busca }}" placeholder="Nome do cliente ou ID do pedido..." style="width:100%"/>
    </div>
    <button type="submit" class="btn-gold">Filtrar</button>
    {% if filtro_status or filtro_fornecedor or busca %}
    <a href="/admin/pedidos" class="btn-outline" style="text-decoration:none">Limpar</a>
    {% endif %}
  </form>
</div>

<!-- ============ LISTA DE PEDIDOS ============ -->
<div style="max-width:1400px;margin:0 auto;padding:20px 24px 60px">

  {% if not pedidos %}
  <div style="text-align:center;padding:80px 20px;color:#6b7280">
    <div style="font-size:48px;margin-bottom:16px">📦</div>
    <p style="font-size:14px">Nenhum pedido encontrado com os filtros selecionados.</p>
  </div>
  {% endif %}

  {% for pedido in pedidos %}
  {% set end = pedido.get('endereco_entrega', {}) %}
  {% set itens = pedido.get('itens', []) %}
  {% set status = pedido.get('status', 'PENDING') %}

  <div class="card" style="margin-bottom:16px">

    <!-- Linha 1: ID + Data + Badges -->
    <div style="display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:14px">
      <span style="font-family:monospace;font-size:12px;color:#6b7280">
        #{{ pedido.id_curto }}
      </span>
      <span style="font-size:11px;color:#4b5563">{{ pedido.data_fmt }}</span>

      <!-- Badge de Status -->
      {% if status == 'PENDING' %}
        <span class="badge badge-gray">PENDING</span>
      {% elif status == 'PAGO' %}
        <span class="badge badge-blue">PAGO</span>
      {% elif status == 'ENVIADO_FORNECEDOR' %}
        <span class="badge badge-yellow">ENVIADO AO FORNECEDOR</span>
      {% elif status == 'RASTREIO_GERADO' %}
        <span class="badge badge-orange">RASTREIO GERADO</span>
      {% elif status == 'ENTREGUE' %}
        <span class="badge badge-green">ENTREGUE</span>
      {% elif status == 'CANCELADO' %}
        <span class="badge badge-red">CANCELADO</span>
      {% else %}
        <span class="badge badge-gray">{{ status }}</span>
      {% endif %}

      <!-- Badge Fornecedor -->
      {% if pedido.get('fornecedor') %}
      <span class="badge" style="background:rgba(255,215,0,.08);color:#FFD700;border-color:rgba(255,215,0,.25)">
        {{ pedido.get('fornecedor') | upper }}
      </span>
      {% endif %}

      <!-- Badge Pagamento -->
      {% if pedido.get('metodo') == 'pix' %}
      <span class="badge" style="background:rgba(16,185,129,.08);color:#34d399;border-color:rgba(16,185,129,.25)">PIX</span>
      {% elif pedido.get('metodo') %}
      <span class="badge" style="background:rgba(139,92,246,.08);color:#a78bfa;border-color:rgba(139,92,246,.25)">CARTÃO</span>
      {% endif %}
    </div>

    <!-- Grade 3 colunas: Cliente | Endereço | Produtos -->
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:14px">

      <!-- CLIENTE -->
      <div style="background:#080808;border:1px solid #1f2937;border-radius:10px;padding:12px">
        <p style="font-size:9px;color:#6b7280;text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px">Cliente</p>
        <p style="font-size:13px;font-weight:700;color:#e5e5e5;margin-bottom:2px">{{ pedido.nome_cliente }}</p>
        {% if pedido.get('cpf_cliente') %}
        <p style="font-size:11px;color:#9ca3af">CPF: {{ pedido.get('cpf_cliente') }}</p>
        {% endif %}
        <p style="font-size:10px;color:#4b5563;margin-top:4px;font-family:monospace">ID: {{ pedido._id_str[-12:] }}</p>
      </div>

      <!-- ENDEREÇO -->
      <div style="background:#080808;border:1px solid #1f2937;border-radius:10px;padding:12px">
        <p style="font-size:9px;color:#6b7280;text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px">Endereço de Entrega</p>
        {% if end %}
        <p style="font-size:12px;color:#d1d5db;line-height:1.6">
          {{ end.get('rua', '—') }}, {{ end.get('numero', 'S/N') }}
          {% if end.get('complemento') %} — {{ end.get('complemento') }}{% endif %}<br/>
          {{ end.get('bairro', '—') }} — {{ end.get('cidade', '—') }}/{{ end.get('estado', '—') }}<br/>
          CEP: {{ end.get('cep', '—') }}
        </p>
        {% else %}
        <p style="font-size:12px;color:#6b7280">Endereço não informado</p>
        {% endif %}
        {% if pedido.get('transportadora') and pedido.get('transportadora') != 'N/A' %}
        <p style="font-size:10px;color:#6b7280;margin-top:6px">✈ {{ pedido.get('transportadora') }}</p>
        {% endif %}
      </div>

      <!-- PRODUTOS -->
      <div style="background:#080808;border:1px solid #1f2937;border-radius:10px;padding:12px">
        <p style="font-size:9px;color:#6b7280;text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px">Produtos</p>
        {% if itens %}
          {% for item in itens %}
          <div style="margin-bottom:4px;padding-bottom:4px;border-bottom:1px solid #1f2937">
            <p style="font-size:12px;color:#d1d5db;font-weight:600">
              {{ item.get('nome') or item.get('produto_nome') or '—' }}
            </p>
            <p style="font-size:10px;color:#9ca3af">
              {% if item.get('tamanho') %}Tam: {{ item.get('tamanho') }} &nbsp;{% endif %}
              Qtd: {{ item.get('quantidade', 1) }}
            </p>
          </div>
          {% endfor %}
        {% elif pedido.get('descricao') %}
          <p style="font-size:12px;color:#9ca3af">{{ pedido.get('descricao') }}</p>
        {% else %}
          <p style="font-size:12px;color:#4b5563">Itens não detalhados</p>
        {% endif %}
      </div>

    </div>

    <!-- Linha financeira + Rastreio -->
    <div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px">
      <div style="display:flex;align-items:baseline;gap:8px">
        <span style="font-size:22px;font-weight:900;color:#fff">
          R$ {{ '%.2f'|format(pedido.get('valor_total', 0)|float) }}
        </span>
        {% if pedido.get('valor_frete', 0)|float > 0 %}
        <span style="font-size:10px;color:#4ade80">
          (incl. R$ {{ '%.2f'|format(pedido.get('valor_frete', 0)|float) }} frete)
        </span>
        {% endif %}
      </div>

      {% if pedido.get('codigo_rastreio') %}
      <div style="background:rgba(249,115,22,.08);border:1px solid rgba(249,115,22,.25);border-radius:10px;padding:8px 14px">
        <span style="font-size:10px;color:#fb923c;text-transform:uppercase;letter-spacing:.08em">Rastreio: </span>
        <span style="font-family:monospace;font-size:13px;color:#fdba74;font-weight:700">{{ pedido.get('codigo_rastreio') }}</span>
      </div>
      {% endif %}
    </div>

    <!-- AÇÕES -->
    <div class="divider"></div>
    <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center">

      {% if status == 'PAGO' %}
      <!-- Botão Encaminhar ao Fornecedor -->
      <form method="POST" action="/admin/pedidos/{{ pedido._id_str }}/encaminhar" style="display:inline">
        <button type="submit" class="btn-gold">
          📤 Encaminhar ao Fornecedor
        </button>
      </form>

      {% elif status == 'ENVIADO_FORNECEDOR' %}
      <!-- Form Inserir Rastreio -->
      <form method="POST" action="/admin/pedidos/{{ pedido._id_str }}/rastreio"
        style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <input type="text" name="codigo_rastreio" placeholder="Código de rastreio (ex: BR123456789BR)"
          required style="min-width:240px" />
        <button type="submit" class="btn-blue">
          📮 Salvar Rastreio
        </button>
      </form>

      {% elif status == 'RASTREIO_GERADO' %}
      <!-- Botão Marcar como Entregue -->
      <form method="POST" action="/admin/pedidos/{{ pedido._id_str }}/entregue" style="display:inline">
        <button type="submit" class="btn-green">
          ✅ Marcar como Entregue
        </button>
      </form>
      {% endif %}

    </div>

  </div>
  {% endfor %}

</div>

<!-- ============ MODAL — MENSAGEM AO FORNECEDOR ============ -->
{% if modal_pedido %}
{% set mp = modal_pedido %}
{% set mp_end = mp.get('endereco_entrega', {}) %}
{% set mp_itens = mp.get('itens', []) %}
<div class="modal-overlay" id="supplier-modal">
  <div class="modal-box">
    <div style="position:absolute;top:0;left:0;right:0;height:3px;background:#FFD700;border-radius:20px 20px 0 0"></div>

    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px;padding-top:6px">
      <div>
        <h2 style="font-size:16px;font-weight:800;color:#FFD700">Mensagem ao Fornecedor</h2>
        <p style="font-size:11px;color:#6b7280;margin-top:2px">Pedido #{{ mp.id_curto }} &middot; {{ mp.nome_cliente }}</p>
      </div>
      <a href="/admin/pedidos" style="display:flex;align-items:center;justify-content:center;width:32px;height:32px;background:#1f2937;border-radius:8px;color:#9ca3af;text-decoration:none;font-size:18px;line-height:1">×</a>
    </div>

    <div style="background:#080808;border:1px solid #1f2937;border-radius:12px;padding:16px;margin-bottom:16px">
      <pre id="supplier-message" style="font-size:12px;color:#d1d5db;line-height:1.75;font-family:ui-monospace,monospace">NOVO PEDIDO AURA PERFORMANCE
─────────────────────────────
Pedido: #{{ mp.id_curto }}
Data: {{ mp.data_fmt }}

CLIENTE:
Nome: {{ mp.nome_cliente }}
{% if mp.get('cpf_cliente') %}CPF: {{ mp.get('cpf_cliente') }}
{% endif %}
ENDEREÇO DE ENTREGA:
{{ mp_end.get('rua', '—') }}, {{ mp_end.get('numero', 'S/N') }}{% if mp_end.get('complemento') %} — {{ mp_end.get('complemento') }}{% endif %}

{{ mp_end.get('bairro', '—') }} — {{ mp_end.get('cidade', '—') }}/{{ mp_end.get('estado', '—') }}
CEP: {{ mp_end.get('cep', '—') }}

PRODUTOS:
{% if mp_itens %}{% for item in mp_itens %}- {{ item.get('nome') or item.get('produto_nome') or '—' }} | Tam: {{ item.get('tamanho', 'Único') }} | Qtd: {{ item.get('quantidade', 1) }}
{% endfor %}{% else %}{{ mp.get('descricao', '(ver pedido)') }}
{% endif %}
OBSERVAÇÕES: Produto com etiqueta AURA Performance.
Não incluir nota fiscal ou material de marketing do fornecedor.
─────────────────────────────
Aguardamos confirmação de envio e código de rastreio.</pre>
    </div>

    <button onclick="copiarMensagem()" class="btn-gold" style="width:100%;padding:12px">
      📋 Copiar Mensagem
    </button>
    <p id="copy-feedback" style="text-align:center;font-size:11px;color:#4ade80;margin-top:8px;display:none">
      ✓ Mensagem copiada para a área de transferência!
    </p>
  </div>
</div>

<script>
function copiarMensagem() {
  var text = document.getElementById('supplier-message').innerText;
  navigator.clipboard.writeText(text).then(function() {
    var fb = document.getElementById('copy-feedback');
    fb.style.display = 'block';
    setTimeout(function() { fb.style.display = 'none'; }, 3000);
  }).catch(function() {
    // fallback para navegadores antigos
    var ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    document.getElementById('copy-feedback').style.display = 'block';
  });
}
</script>
{% endif %}

</body>
</html>"""


# ===================================================
# TEMPLATE — PROFISSIONAIS PENDENTES
# ===================================================

_PROFISSIONAIS_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AURA Admin — Profissionais</title>
<script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-950 text-white min-h-screen">
  <nav class="bg-black border-b border-yellow-500/20 px-6 py-4 flex items-center justify-between">
    <div class="flex items-center gap-6">
      <span class="text-yellow-400 font-black text-xl">AURA Admin</span>
      <a href="/admin/pedidos" class="text-gray-400 hover:text-white text-sm">Pedidos</a>
      <a href="/admin/profissionais" class="text-yellow-400 font-bold text-sm border-b border-yellow-400">Profissionais</a>
    </div>
    <a href="/admin/logout" class="text-gray-500 hover:text-red-400 text-sm">Sair</a>
  </nav>

  <div class="max-w-5xl mx-auto p-6">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-black">Profissionais Pendentes</h1>
      <span class="bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 px-3 py-1 rounded-full text-sm font-bold">
        {{ profissionais|length }} pendente(s)
      </span>
    </div>

    {% if request.args.get('msg') == 'aprovado' %}
    <div class="bg-green-500/10 border border-green-500/30 text-green-400 px-4 py-3 rounded-xl mb-4">✅ Profissional aprovado com sucesso!</div>
    {% elif request.args.get('msg') == 'rejeitado' %}
    <div class="bg-red-500/10 border border-red-500/30 text-red-400 px-4 py-3 rounded-xl mb-4">❌ Profissional rejeitado.</div>
    {% endif %}

    {% if not profissionais %}
    <div class="text-center py-20 text-gray-600">
      <p class="text-4xl mb-3">✅</p>
      <p class="text-lg font-bold">Nenhum profissional pendente</p>
    </div>
    {% else %}
    <div class="space-y-4">
      {% for p in profissionais %}
      <div class="bg-gray-900 border border-gray-800 rounded-2xl p-6">
        <div class="flex items-start justify-between mb-4">
          <div>
            <div class="flex items-center gap-2 mb-1">
              <span class="text-yellow-400 font-black text-lg">{{ p.nome_usuario }}</span>
              <span class="bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 px-2 py-0.5 rounded-full text-xs font-bold uppercase">{{ p.tipo_profissional }}</span>
              <span class="bg-orange-500/10 text-orange-400 border border-orange-500/20 px-2 py-0.5 rounded-full text-xs font-bold">PENDENTE</span>
            </div>
            <p class="text-gray-400 text-sm">{{ p.email_usuario }}</p>
            <p class="text-gray-600 text-xs mt-1">ID: {{ p.id_curto }} • {{ p.data_fmt }}</p>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div class="bg-gray-800/50 rounded-xl p-4">
            <p class="text-gray-500 text-xs uppercase font-bold mb-2">Bio</p>
            <p class="text-gray-200 text-sm">{{ p.bio or 'Não informado' }}</p>
          </div>
          <div class="bg-gray-800/50 rounded-xl p-4">
            <p class="text-gray-500 text-xs uppercase font-bold mb-2">Registro Profissional</p>
            <p class="text-gray-200 text-sm font-mono">{{ p.cref_crn_crm or 'Não informado' }}</p>
            {% if p.instagram %}
            <p class="text-gray-500 text-xs uppercase font-bold mt-3 mb-1">Instagram</p>
            <p class="text-blue-400 text-sm">@{{ p.instagram }}</p>
            {% endif %}
          </div>
        </div>

        {% if p.especialidades %}
        <div class="mb-4">
          <p class="text-gray-500 text-xs uppercase font-bold mb-2">Especialidades</p>
          <div class="flex flex-wrap gap-2">
            {% for esp in p.especialidades %}
            <span class="bg-gray-800 text-gray-300 px-3 py-1 rounded-full text-xs">{{ esp }}</span>
            {% endfor %}
          </div>
        </div>
        {% endif %}

        <div class="flex gap-3 pt-4 border-t border-gray-800">
          <form method="POST" action="/admin/profissionais/{{ p.user_id }}/aprovar">
            <button type="submit" class="bg-yellow-400 text-black font-black px-6 py-2.5 rounded-xl text-sm hover:bg-yellow-300 transition-all">
              ✅ Aprovar
            </button>
          </form>
          <form method="POST" action="/admin/profissionais/{{ p.user_id }}/rejeitar">
            <button type="submit" class="bg-red-500/10 text-red-400 border border-red-500/20 font-bold px-6 py-2.5 rounded-xl text-sm hover:bg-red-500/20 transition-all">
              ❌ Rejeitar
            </button>
          </form>
        </div>
      </div>
      {% endfor %}
    </div>
    {% endif %}
  </div>
</body>
</html>
"""


# ===================================================
# ROTAS — AUTH
# ===================================================

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        senha = request.form.get("senha", "")
        secret = os.getenv("ADMIN_SECRET_KEY", "")
        if not secret:
            return render_template_string(
                _LOGIN_TEMPLATE,
                error="ADMIN_SECRET_KEY não configurada no servidor."
            )
        if senha == secret:
            session["admin"] = True
            logger.info("✅ Login no painel admin bem-sucedido.")
            return redirect("/admin/pedidos")
        logger.warning("⚠️ Tentativa de login admin com senha incorreta.")
        return render_template_string(_LOGIN_TEMPLATE, error="Senha incorreta.")
    return render_template_string(_LOGIN_TEMPLATE, error=None)


@admin_bp.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect("/admin/login")


# ===================================================
# ROTAS — LISTAGEM DE PEDIDOS
# ===================================================

@admin_bp.route("/pedidos", methods=["GET"])
@_admin_required
def pedidos():
    filtro_status = request.args.get("status", "")
    filtro_fornecedor = request.args.get("fornecedor", "")
    busca = request.args.get("busca", "").strip()
    modal_id = request.args.get("modal", "")

    pedidos_lista = []
    modal_pedido = None

    if mongo_db is not None:
        try:
            query = {}
            if filtro_status:
                query["status"] = filtro_status
            if filtro_fornecedor:
                query["fornecedor"] = filtro_fornecedor

            cursor = mongo_db["pedidos"].find(query).sort("created_at", -1).limit(200)

            for p in cursor:
                p["_id_str"] = str(p["_id"])
                p["id_curto"] = str(p["_id"])[-8:].upper()
                p["nome_cliente"] = _buscar_nome_usuario(p.get("user_id", ""))
                p["cpf_cliente"] = _buscar_cpf_usuario(p.get("user_id", ""))

                try:
                    dt = datetime.fromisoformat(p.get("created_at", ""))
                    p["data_fmt"] = dt.strftime("%d/%m/%Y %H:%M")
                except Exception:
                    p["data_fmt"] = p.get("created_at", "—")

                pedidos_lista.append(p)

            if busca:
                busca_lower = busca.lower()
                pedidos_lista = [
                    p for p in pedidos_lista
                    if busca_lower in p["nome_cliente"].lower()
                    or busca_lower in p["_id_str"].lower()
                ]

            if modal_id:
                for p in pedidos_lista:
                    if p["_id_str"] == modal_id:
                        modal_pedido = p
                        break
                # Se o pedido foi encaminhado e já saiu do filtro atual, buscamos diretamente
                if not modal_pedido:
                    try:
                        doc = mongo_db["pedidos"].find_one({"_id": ObjectId(modal_id)})
                        if doc:
                            doc["_id_str"] = str(doc["_id"])
                            doc["id_curto"] = str(doc["_id"])[-8:].upper()
                            doc["nome_cliente"] = _buscar_nome_usuario(doc.get("user_id", ""))
                            doc["cpf_cliente"] = _buscar_cpf_usuario(doc.get("user_id", ""))
                            try:
                                dt = datetime.fromisoformat(doc.get("created_at", ""))
                                doc["data_fmt"] = dt.strftime("%d/%m/%Y %H:%M")
                            except Exception:
                                doc["data_fmt"] = doc.get("created_at", "—")
                            modal_pedido = doc
                    except Exception as e:
                        logger.error(f"Erro ao buscar pedido para modal {modal_id}: {e}")

        except Exception as e:
            logger.error(f"Erro ao listar pedidos no painel admin: {e}")

    return render_template_string(
        _PEDIDOS_TEMPLATE,
        pedidos=pedidos_lista,
        filtro_status=filtro_status,
        filtro_fornecedor=filtro_fornecedor,
        busca=busca,
        modal_pedido=modal_pedido,
    )


# ===================================================
# ROTAS — AÇÕES
# ===================================================

@admin_bp.route("/pedidos/<pedido_id>/encaminhar", methods=["POST"])
@_admin_required
def encaminhar_fornecedor(pedido_id):
    """Muda status para ENVIADO_FORNECEDOR e redireciona com modal da mensagem."""
    try:
        if mongo_db is not None:
            mongo_db["pedidos"].update_one(
                {"_id": ObjectId(pedido_id)},
                {"$set": {
                    "status": "ENVIADO_FORNECEDOR",
                    "encaminhado_em": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }}
            )
            logger.info(f"📦 Pedido {pedido_id} encaminhado ao fornecedor.")
    except Exception as e:
        logger.error(f"Erro ao encaminhar pedido {pedido_id}: {e}")
    return redirect(f"/admin/pedidos?modal={pedido_id}")


@admin_bp.route("/pedidos/<pedido_id>/rastreio", methods=["POST"])
@_admin_required
def inserir_rastreio(pedido_id):
    """Salva código de rastreio e muda status para RASTREIO_GERADO."""
    codigo = request.form.get("codigo_rastreio", "").strip()
    if not codigo:
        return redirect("/admin/pedidos")
    try:
        if mongo_db is not None:
            mongo_db["pedidos"].update_one(
                {"_id": ObjectId(pedido_id)},
                {"$set": {
                    "status": "RASTREIO_GERADO",
                    "codigo_rastreio": codigo,
                    "rastreio_atualizado_em": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }}
            )
            logger.info(f"📮 Rastreio '{codigo}' salvo para pedido {pedido_id}.")
    except Exception as e:
        logger.error(f"Erro ao inserir rastreio no pedido {pedido_id}: {e}")
    return redirect("/admin/pedidos")


@admin_bp.route("/pedidos/<pedido_id>/entregue", methods=["POST"])
@_admin_required
def marcar_entregue(pedido_id):
    """Muda status para ENTREGUE."""
    try:
        if mongo_db is not None:
            mongo_db["pedidos"].update_one(
                {"_id": ObjectId(pedido_id)},
                {"$set": {
                    "status": "ENTREGUE",
                    "entregue_em": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }}
            )
            logger.info(f"✅ Pedido {pedido_id} marcado como ENTREGUE.")
    except Exception as e:
        logger.error(f"Erro ao marcar pedido {pedido_id} como entregue: {e}")
    return redirect("/admin/pedidos")


# ===================================================
# ROTAS — PROFISSIONAIS
# ===================================================

@admin_bp.route("/profissionais")
@_admin_required
def admin_profissionais():
    try:
        pendentes = list(mongo_db["profissionais"].find(
            {"status_verificacao": {"$in": ["pendente", "pending", None]}}
        ).sort("created_at", -1).limit(200))

        for p in pendentes:
            p["_id_str"] = str(p["_id"])
            p["id_curto"] = str(p["_id"])[-8:].upper()
            try:
                usuario = mongo_db["usuarios"].find_one({"_id": ObjectId(p["user_id"])})
                p["nome_usuario"] = usuario.get("nome", "N/A") if usuario else "N/A"
                p["email_usuario"] = usuario.get("email", "N/A") if usuario else "N/A"
            except Exception:
                p["nome_usuario"] = "N/A"
                p["email_usuario"] = "N/A"
            try:
                dt = datetime.fromisoformat(p.get("created_at", ""))
                p["data_fmt"] = dt.strftime("%d/%m/%Y %H:%M")
            except Exception:
                p["data_fmt"] = p.get("created_at", "")[:10]

        return render_template_string(_PROFISSIONAIS_TEMPLATE, profissionais=pendentes)
    except Exception as e:
        logger.error(f"Erro ao listar profissionais pendentes: {e}")
        return f"Erro: {e}", 500


@admin_bp.route("/profissionais/<user_id>/aprovar", methods=["POST"])
@_admin_required
def aprovar_profissional(user_id):
    try:
        mongo_db["profissionais"].update_one(
            {"user_id": user_id},
            {"$set": {"status_verificacao": "aprovado", "verificado": True}}
        )
        mongo_db["usuarios"].update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"tipo_perfil": "profissional"}}
        )
        mongo_db["notificacoes"].insert_one({
            "user_id": user_id,
            "tipo": "sistema",
            "mensagem": "🎉 Parabéns! Seu cadastro profissional foi aprovado! Agora você pode criar desafios e atender alunos na AURA.",
            "meta": {"acao": "profissional_aprovado"},
            "lida": False,
            "created_at": datetime.now().isoformat()
        })
        logger.info(f"✅ Profissional {user_id} aprovado.")
        return redirect("/admin/profissionais?msg=aprovado")
    except Exception as e:
        logger.error(f"Erro ao aprovar profissional {user_id}: {e}")
        return f"Erro: {e}", 500


@admin_bp.route("/profissionais/<user_id>/rejeitar", methods=["POST"])
@_admin_required
def rejeitar_profissional(user_id):
    try:
        mongo_db["profissionais"].update_one(
            {"user_id": user_id},
            {"$set": {"status_verificacao": "rejeitado", "verificado": False}}
        )
        mongo_db["usuarios"].update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"tipo_perfil": "atleta"}}
        )
        mongo_db["notificacoes"].insert_one({
            "user_id": user_id,
            "tipo": "sistema",
            "mensagem": "⚠️ Seu cadastro profissional não foi aprovado desta vez. Verifique suas informações e tente novamente.",
            "meta": {"acao": "profissional_rejeitado"},
            "lida": False,
            "created_at": datetime.now().isoformat()
        })
        logger.info(f"❌ Profissional {user_id} rejeitado.")
        return redirect("/admin/profissionais?msg=rejeitado")
    except Exception as e:
        logger.error(f"Erro ao rejeitar profissional {user_id}: {e}")
        return f"Erro: {e}", 500
