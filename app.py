from flask import Flask, render_template
from rotas_api import api_bp # Importa o novo módulo de rotas de API

# ===================================================
# ⚙️ CONFIGURAÇÃO DO SERVIDOR FLASK
# ===================================================
# Dizemos explicitamente onde estão as pastas 'templates' e 'static'.
app = Flask(__name__, template_folder='templates', static_folder='static')

# 1. REGISTRA AS ROTAS DE API:
# Todas as rotas de dados (comando, xp, missoes, equilibrio) agora estão aqui.
app.register_blueprint(api_bp)

# ========================================
# 🌐 ROTAS DE PÁGINAS (FRONT-END)
# ========================================

@app.route('/')
def home():
    """Rota principal do site (Vitrine Pública)."""
    return render_template("index.html")

@app.route('/recurso/mestre')
def mestre_app():
    """Rota para a interface do Mestre da Aura (usado pelo Base44)."""
    # Usamos o template principal refatorado (mestre_painel.html)
    return render_template("mestre_painel.html")


# ===================================================
# 🚀 INICIALIZAÇÃO DO SERVIDOR LOCAL
# ===================================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050, debug=True)