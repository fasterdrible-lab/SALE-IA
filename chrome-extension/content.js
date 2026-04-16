/**
 * content.js — Script de conteúdo da extensão SALEIA
 *
 * Monitora as legendas do Google Meet em tempo real,
 * envia trechos para o backend SALEIA e exibe dicas
 * numa barra lateral dentro do próprio Meet.
 */

/* ─────────────────────────────────────────────
   BARRA LATERAL (SIDEBAR)
───────────────────────────────────────────── */

// Injeta o CSS da sidebar
const link = document.createElement('link');
link.rel = 'stylesheet';
link.href = chrome.runtime.getURL('content.css');
document.head.appendChild(link);

// Cria o elemento da sidebar
const sidebar = document.createElement('div');
sidebar.id = 'saleia-sidebar';
sidebar.innerHTML = `
  <div id="saleia-header">
    <span class="saleia-logo">🤖 SALEIA</span>
    <button id="saleia-toggle" title="Minimizar">—</button>
  </div>
  <div id="saleia-body">
    <div id="saleia-alerta" class="saleia-card saleia-alerta hidden"></div>
    <div id="saleia-disc" class="saleia-card">
      <div class="card-title">🎯 Perfil DISC</div>
      <div id="saleia-disc-content" class="card-content">Aguardando conversa...</div>
    </div>
    <div id="saleia-dica" class="saleia-card">
      <div class="card-title">💡 Dica Oculta</div>
      <div id="saleia-dica-content" class="card-content">—</div>
    </div>
    <div id="saleia-proxima" class="saleia-card">
      <div class="card-title">⚡ Próxima Fala</div>
      <div id="saleia-proxima-content" class="card-content">—</div>
    </div>
    <div id="saleia-financeiro" class="saleia-card">
      <div class="card-title">💰 Sinal Financeiro</div>
      <div id="saleia-financeiro-content" class="card-content">—</div>
    </div>
    <div class="saleia-status">
      Atualizado: <span id="saleia-timestamp">—</span>
    </div>
  </div>
`;
document.body.appendChild(sidebar);

// Botão de minimizar/expandir
const toggleBtn = document.getElementById('saleia-toggle');
const sidebarBody = document.getElementById('saleia-body');
let minimizado = false;
toggleBtn.addEventListener('click', () => {
  minimizado = !minimizado;
  sidebarBody.style.display = minimizado ? 'none' : 'block';
  toggleBtn.textContent = minimizado ? '+' : '—';
});

/* ─────────────────────────────────────────────
   CAPTURA DE LEGENDAS DO GOOGLE MEET
───────────────────────────────────────────── */

let transcricaoParcial = '';
let historico = '';
let perfilDiscAtual = '';
let ultimoEnvio = 0;
const INTERVALO_MS = 60000; // envia ao backend a cada 60 segundos

// Observer que monitora as legendas geradas pelo Meet
const legendaObserver = new MutationObserver(() => {
  // Seletores usados pelo Google Meet para exibir legendas (podem variar)
  const seletores = [
    '[data-message-text]',
    '.a4cQT',            // legenda em tempo real
    '[jsname="tgaKEf"]', // participante + fala
  ];

  let textoNovo = '';
  for (const sel of seletores) {
    document.querySelectorAll(sel).forEach(el => {
      textoNovo += el.innerText + ' ';
    });
    if (textoNovo.trim()) break;
  }

  if (textoNovo.trim() && textoNovo !== transcricaoParcial) {
    transcricaoParcial = textoNovo.trim();
    const agora = Date.now();
    if (agora - ultimoEnvio >= INTERVALO_MS) {
      ultimoEnvio = agora;
      enviarParaBackend();
    }
  }
});

// Inicia o observer quando o DOM do Meet estiver pronto
function iniciarObserver() {
  const alvo = document.body;
  legendaObserver.observe(alvo, { childList: true, subtree: true, characterData: true });
}

// Aguarda a página do Meet carregar antes de iniciar
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', iniciarObserver);
} else {
  iniciarObserver();
}

/* ─────────────────────────────────────────────
   COMUNICAÇÃO COM O BACKEND SALEIA
───────────────────────────────────────────── */

function enviarParaBackend() {
  // Busca configurações salvas no storage (modelo, provedor, chave, URL)
  chrome.storage.local.get(
    ['selectedLlm', 'selectedProvider', 'apiKey_openai', 'apiKey_anthropic', 'apiKey_google', 'saleliaBackendUrl'],
    (config) => {
      const backendUrl = config.saleliaBackendUrl || 'http://localhost:8000';
      const provider = config.selectedProvider || 'openai';

      fetch(`${backendUrl}/tempo-real`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transcricao_parcial: transcricaoParcial,
          historico: historico,
          perfil_disc_atual: perfilDiscAtual,
          llm_model: config.selectedLlm || 'gpt-4o',
          llm_provider: provider,
          api_key_override: config[`apiKey_${provider}`] || null
        })
      })
        .then(r => r.json())
        .then(data => {
          atualizarSidebar(data);
          // Acumula histórico para o próximo ciclo
          historico += '\n' + transcricaoParcial;
          if (data.perfil_disc) perfilDiscAtual = data.perfil_disc;
        })
        .catch(err => console.warn('[SALEIA] Erro ao chamar backend:', err));
    }
  );
}

/* ─────────────────────────────────────────────
   ATUALIZAR A SIDEBAR COM A RESPOSTA DA IA
───────────────────────────────────────────── */

function atualizarSidebar(data) {
  // Alerta urgente (aparece em destaque se houver)
  const alertaEl = document.getElementById('saleia-alerta');
  if (data.alerta_urgente) {
    alertaEl.textContent = '🚨 ' + data.alerta_urgente;
    alertaEl.classList.remove('hidden');
  } else {
    alertaEl.classList.add('hidden');
  }

  // Perfil DISC
  if (data.perfil_disc) {
    document.getElementById('saleia-disc-content').innerHTML =
      `<strong>${data.perfil_disc}</strong>${data.disc_confianca ? ' (' + data.disc_confianca + '%)' : ''}` +
      (data.disc_evidencia ? `<br><small>${data.disc_evidencia}</small>` : '');
  }

  // Dica oculta (o que o vendedor não percebeu)
  if (data.sinal_oculto) {
    document.getElementById('saleia-dica-content').textContent = data.sinal_oculto;
  }

  // Próxima fala sugerida
  if (data.proxima_acao) {
    document.getElementById('saleia-proxima-content').textContent = data.proxima_acao;
  }

  // Sinal financeiro
  if (data.sinal_financeiro) {
    document.getElementById('saleia-financeiro-content').textContent = data.sinal_financeiro;
  }

  // Timestamp da última atualização
  const agora = new Date();
  document.getElementById('saleia-timestamp').textContent =
    agora.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
