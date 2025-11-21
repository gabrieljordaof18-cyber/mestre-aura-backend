// ==============================================================
// 🖥️ MESTRE DA AURA - FRONT-END (CLIENTE)
// ==============================================================
// Responsabilidade: Apenas exibir dados. Nenhuma regra de negócio aqui.

document.addEventListener("DOMContentLoaded", () => {
    // Inicia o ciclo de atualizações assim que a página carrega
    atualizarTudo();
    setInterval(atualizarTudo, 10000); // Atualiza a cada 10 segundos
});

// --- 1. SISTEMA DE CHAT ---

async function enviarMensagem() {
    const msgInput = document.getElementById("msg");
    const btnEnviar = document.querySelector("button.enviar");
    const texto = msgInput.value.trim();

    if (!texto) return;

    // Feedback visual imediato (UX)
    msgInput.value = "";
    btnEnviar.disabled = true;
    btnEnviar.textContent = "Enviando...";
    btnEnviar.style.opacity = "0.7";
    
    adicionarMensagem("Você", texto, "user");

    try {
        const response = await fetch("/comando", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ comando: texto })
        });

        const data = await response.json();
        const respostaAura = data.resposta || "Silêncio...";
        
        adicionarMensagem("AURA", respostaAura, "bot");

        // Se a resposta da IA sugerir atualização, forçamos uma agora
        if (respostaAura.includes("atualiz") || respostaAura.includes("registrado")) {
            setTimeout(atualizarTudo, 1000);
        }

    } catch (error) {
        console.error("Erro no chat:", error);
        adicionarMensagem("Sistema", "Erro de conexão com a AURA.", "bot");
    } finally {
        // Restaura o botão
        btnEnviar.disabled = false;
        btnEnviar.textContent = "Enviar";
        btnEnviar.style.opacity = "1";
    }
}

function adicionarMensagem(remetente, texto, classe) {
    const container = document.getElementById("mensagens");
    const msg = document.createElement("div");
    msg.className = `msg ${classe}`;
    
    // Renderiza quebras de linha se houver
    msg.innerText = `${remetente}: ${texto}`; 
    
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;
}

// --- 2. ORQUESTRADOR DE ATUALIZAÇÕES ---

async function atualizarTudo() {
    // Chama todas as funções de atualização em paralelo
    await Promise.all([
        atualizarFisiologia(),
        atualizarGamificacao(),
        atualizarEquilibrio(),
        atualizarFeedback()
    ]);
}

// --- 3. MÓDULOS DE EXIBIÇÃO ---

async function atualizarFisiologia() {
    try {
        const dados = await fetch("/status_fisiologico").then(r => r.json());
        
        // Atualiza textos simples
        setText("energia", (dados.energia?.nivel || 0) + "%");
        
        // Formatação segura (evita erro se for null)
        const sono = dados.sono?.horas || dados.sono || 0;
        setText("sono_info", `${sono}h`);
        
        const hrv = dados.hrv?.valor || dados.hrv || 0;
        setText("hrv_info", hrv);
        
        const treino = dados.treino?.intensidade || 0;
        setText("treino_info", `${treino}%`);

        // Atualiza status dos sensores (simulado)
        const conectado = "✅ On";
        setText("apple_status", conectado);
        setText("garmin_status", conectado);
        setText("strava_status", conectado);

    } catch (e) {
        console.warn("Falha ao atualizar fisiologia", e);
    }
}

async function atualizarGamificacao() {
    try {
        // 1. Atualiza XP e Nível
        const xpStatus = await fetch("/xp_status").then(r => r.json());
        setText("nivel-num", xpStatus.nivel);
        setText("xp-atual", `${xpStatus.xp_total} XP`);
        setText("xp-necessario", `Meta: ${xpStatus.xp_por_nivel} XP`);
        
        // Barra de progresso
        const percent = Math.min(100, Math.round((xpStatus.xp_total / xpStatus.xp_por_nivel) * 100));
        const bar = document.getElementById("xp-bar");
        if(bar) bar.style.width = `${percent}%`;

        // 2. Atualiza Missões
        const listaRes = await fetch("/missoes").then(r => r.json());
        renderizarMissoes(listaRes.missoes || []);

    } catch (e) {
        console.warn("Falha ao atualizar gamificação", e);
    }
}

function renderizarMissoes(missoes) {
    const container = document.getElementById("lista-missoes");
    if (!container) return;

    // Conta concluídas para o header
    const concluidas = missoes.filter(m => m.concluida).length;
    setText("missoes-concluidas", concluidas);

    if (missoes.length === 0) {
        container.innerHTML = '<div class="small">Nenhuma missão ativa.</div>';
        return;
    }

    container.innerHTML = ""; // Limpa lista
    
    missoes.forEach(m => {
        const div = document.createElement("div");
        div.className = "missao";
        
        // Botão ou Texto de Status
        let actionHTML = "";
        if (m.concluida) {
            actionHTML = `<span style="color:#00FF7F; font-weight:bold;">✔ Feito</span>`;
        } else {
            // Botão que chama a API para concluir
            actionHTML = `<button class="btn-claim" onclick="concluirMissao('${m.id}')">Concluir</button>`;
        }

        div.innerHTML = `
            <div class="descricao">${m.descricao}</div>
            <div style="display:flex; align-items:center; gap:10px;">
                <span class="badge-xp">+${m.xp} XP</span>
                ${actionHTML}
            </div>
        `;
        container.appendChild(div);
    });
}

async function concluirMissao(id) {
    // Efeito visual imediato (feedback otimista)
    const btn = event.target;
    btn.textContent = "...";
    btn.disabled = true;

    try {
        const res = await fetch("/concluir_missao", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ id: id })
        }).then(r => r.json());

        if (res.sucesso) {
            adicionarMensagem("Sistema", res.msg, "bot");
            atualizarGamificacao(); // Recarrega a lista oficial
        } else {
            alert(res.erro || "Erro ao concluir");
            btn.textContent = "Erro";
        }
    } catch (e) {
        console.error(e);
    }
}

async function atualizarEquilibrio() {
    try {
        // O Python calcula, o JS só pinta
        const eq = await fetch("/equilibrio").then(r => r.json());
        
        const score = eq.score || 0;
        setText("equilibrio-percent", `${score}%`);
        setText("equilibrio-sub", eq.estado || "Calculando...");
        setText("equilibrio-legend", `Corpo ${eq.componentes?.corpo || 0} | Mente ${eq.componentes?.mente || 0}`);

        // Atualiza cor do Gauge
        const gauge = document.getElementById("equilibrio-gauge");
        if (gauge) {
            const cor = obterCorPorScore(score);
            gauge.style.boxShadow = `0 0 20px ${cor} inset, 0 0 10px ${cor}`;
            gauge.style.borderColor = cor;
        }

    } catch (e) {
        console.warn("Falha equilibrio", e);
    }
}

async function atualizarFeedback() {
    try {
        const fb = await fetch("/feedback").then(r => r.json());
        setText("feedback-text", fb.texto || "Analisando dados...");
    } catch (e) {
        console.warn("Falha feedback", e);
    }
}

// --- 4. UTILITÁRIOS ---

function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.innerText = text;
}

function obterCorPorScore(score) {
    if (score >= 80) return "rgba(0, 255, 127, 0.8)"; // Verde
    if (score >= 60) return "rgba(255, 215, 0, 0.8)"; // Amarelo
    if (score >= 40) return "rgba(255, 140, 0, 0.8)"; // Laranja
    return "rgba(255, 69, 0, 0.8)"; // Vermelho
}