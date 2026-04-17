/**
 * SALEIA — content.js
 * Script principal que roda dentro do Google Meet.
 * Responsável por:
 *  1. Injetar a sidebar lateral de dicas
 *  2. Capturar legendas/captions via MutationObserver
 *  3. Enviar transcrição ao backend a cada 60 segundos
 *  4. Exibir respostas da IA na sidebar
 *
 * NOTA TÉCNICA: O fetch ao backend é feito via chrome.runtime.sendMessage
 * para o background.js, pois o Service Worker do Google Meet (meetsw.js)
 * intercepta e bloqueia requisições fetch feitas diretamente pelo content script.
 */

(function () {
  'use strict';

  function escaparHtml(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  const CONFIG = {
    backendUrl: 'https://dime-flip-protector.ngrok-free.dev',
    intervaloAnalise: 60,
    maxTranscricaoRecente: 2 * 60,
    maxHistorico: 5 * 60,
  };

  const estado = {
    ativo: true,
    transcricao: [],
    historicoResumo: '',
    perfilDiscAtual: null,
    mapaFinanceiro: {},
    contador: CONFIG.intervaloAnalise,
    sidebarMinimizada: false,
    timerContador: null,
    timerEnvio: null,
    backendOnline: true,
  };

  chrome.storage.local.get(['saleiaBackendUrl', 'saleiaAtivo'], function (result) {
    if (result.saleiaBackendUrl) CONFIG.backendUrl = result.saleiaBackendUrl;
    if (result.saleiaAtivo === false) estado.ativo = false;
    iniciar();
  });

  function iniciar() {
    if (document.getElementById('saleia-sidebar')) return;
    criarSidebar();
    iniciarObservadorLegendas();
    iniciarContadorRegressivo();
    iniciarEnvioPeriodico();
    chrome.runtime.onMessage.addListener(function (msg) {
      if (msg.tipo === 'toggle') { estado.ativo = msg.valor; atualizarStatusSidebar(); }
      if (msg.tipo === 'backendUrl') { CONFIG.backendUrl = msg.valor; }
    });
  }

  function criarSidebar() {
    const sidebar = document.createElement('div');
    sidebar.id = 'saleia-sidebar';
    sidebar.innerHTML = `
      <div id="saleia-header">
        <span>🤖 SALEIA AO VIVO</span>
        <button id="saleia-toggle-btn" title="Minimizar/Expandir">≡</button>
      </div>
      <div id="saleia-body">
        <div id="saleia-status"><span class="saleia-dot"></span> Monitorando...</div>

        <div id="saleia-alerta" class="saleia-secao saleia-alerta-box" style="display:none">
          <div class="saleia-secao-titulo">⚠️ ALERTA URGENTE</div>
          <div id="saleia-alerta-texto"></div>
        </div>

        <div id="saleia-disc" class="saleia-secao">
          <div class="saleia-secao-titulo">🎯 PERFIL DISC</div>
          <div id="saleia-disc-texto">Aguardando análise...</div>
        </div>

        <div id="saleia-mapa-financeiro" class="saleia-secao saleia-mapa-financeiro">
          <div class="saleia-secao-titulo">💰 MAPA FINANCEIRO</div>
          <div id="saleia-mapa-financeiro-texto">Aguardando dados financeiros...</div>
        </div>

        <div id="saleia-temperatura" class="saleia-secao saleia-temperatura">
          <div class="saleia-secao-titulo">🌡️ TEMPERATURA</div>
          <div id="saleia-temperatura-texto">Aguardando análise...</div>
        </div>

        <div id="saleia-proxima-fala" class="saleia-secao">
          <div class="saleia-secao-titulo">💬 PRÓXIMA FALA</div>
          <div id="saleia-proxima-fala-texto">Aguardando...</div>
        </div>

        <div id="saleia-objecao" class="saleia-secao" style="display:none">
          <div class="saleia-secao-titulo">🛡️ OBJEÇÃO DETECTADA</div>
          <div id="saleia-objecao-texto"></div>
        </div>

        <div id="saleia-dado-esquecido" class="saleia-secao saleia-dado-esquecido" style="display:none">
          <div class="saleia-secao-titulo">🔔 DADO ESQUECIDO</div>
          <div id="saleia-dado-esquecido-texto"></div>
        </div>

        <div id="saleia-legenda-aviso" class="saleia-secao saleia-aviso" style="display:none">
          ⚠️ Ative as legendas no Meet:<br>
          Clique em "CC" na barra inferior do Meet
        </div>
        <div id="saleia-contador">Próxima análise em: 60s</div>
      </div>
    `;
    document.body.appendChild(sidebar);
    document.getElementById('saleia-toggle-btn').addEventListener('click', function () {
      estado.sidebarMinimizada = !estado.sidebarMinimizada;
      const body = document.getElementById('saleia-body');
      body.style.display = estado.sidebarMinimizada ? 'none' : 'block';
      this.textContent = estado.sidebarMinimizada ? '▶' : '≡';
      sidebar.style.width = estado.sidebarMinimizada ? '44px' : '280px';
    });
  }

  const CAPTION_SELECTORS = [
    '[class*="caption"]',
    '[jsname="tgaKEf"]',
    '[class*="CNusmb"]',
    'div[class*="iOzk7"]',
    '[data-message-text]',
    'span[class*="bj56rb"]',
    '[class*="a4cQT"]',
    '[class*="TBMuR"]',
    '[class*="Mz6pEf"]',
  ];

  const textoCapturado = new Set();
  let legendasDetectadas = false;
  let verificacaoLegendaTimer = null;

  function iniciarObservadorLegendas() {
    const observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        mutation.addedNodes.forEach(function (node) {
          if (node.nodeType !== Node.ELEMENT_NODE) return;
          CAPTION_SELECTORS.forEach(function (sel) {
            try {
              if (node.matches && node.matches(sel)) processarElementoLegenda(node);
              const filhos = node.querySelectorAll ? node.querySelectorAll(sel) : [];
              filhos.forEach(processarElementoLegenda);
            } catch (e) {}
          });
        });
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
    verificacaoLegendaTimer = setInterval(verificarLegendas, 10000);
  }

  function processarElementoLegenda(el) {
    if (!el || !el.textContent) return;
    const texto = el.textContent.trim();
    if (!texto || texto.length < 3) return;
    if (el.closest && el.closest('#saleia-sidebar')) return;
    const chave = texto.substring(0, 80);
    if (textoCapturado.has(chave)) return;
    textoCapturado.add(chave);
    if (textoCapturado.size > 500) {
      const primeiro = textoCapturado.values().next().value;
      textoCapturado.delete(primeiro);
    }
    legendasDetectadas = true;
    let speaker = 'Participante';
    const speakerEl = el.closest('[class*="caption"]');
    if (speakerEl) {
      const nomeEl = speakerEl.querySelector('[class*="zs7s8d"]') ||
                     speakerEl.querySelector('[class*="NWpY1"]') ||
                     speakerEl.querySelector('strong') ||
                     speakerEl.querySelector('b');
      if (nomeEl && nomeEl.textContent.trim()) speaker = nomeEl.textContent.trim();
    }
    estado.transcricao.push({ speaker: speaker, text: texto, timestamp: new Date().toISOString() });
    ocultarAvisoLegenda();
  }

  function verificarLegendas() { if (!legendasDetectadas) exibirAvisoLegenda(); }
  function exibirAvisoLegenda() { const a = document.getElementById('saleia-legenda-aviso'); if (a) a.style.display = 'block'; }
  function ocultarAvisoLegenda() { const a = document.getElementById('saleia-legenda-aviso'); if (a) a.style.display = 'none'; }

  function iniciarContadorRegressivo() {
    estado.contador = CONFIG.intervaloAnalise;
    estado.timerContador = setInterval(function () {
      if (!estado.ativo) return;
      estado.contador--;
      if (estado.contador < 0) estado.contador = CONFIG.intervaloAnalise;
      atualizarContador();
    }, 1000);
  }

  function atualizarContador() {
    const el = document.getElementById('saleia-contador');
    if (el) el.textContent = 'Próxima análise em: ' + estado.contador + 's';
  }

  function iniciarEnvioPeriodico() {
    estado.timerEnvio = setInterval(function () {
      if (estado.ativo) enviarParaBackend();
    }, CONFIG.intervaloAnalise * 1000);
  }

  function montarTranscricaoParcial() {
    const recentes = estado.transcricao.slice(-60);
    return recentes.map(function (item) { return item.speaker + ': ' + item.text; }).join('\n');
  }

  function montarHistorico() {
    if (estado.historicoResumo) return estado.historicoResumo;
    const historico = estado.transcricao.slice(-150);
    return historico.map(function (item) { return item.speaker + ': ' + item.text; }).join('\n');
  }

  function enviarParaBackend() {
    const transcricaoParcial = montarTranscricaoParcial();

    // GUARDA: só envia se houver transcrição real com pelo menos 20 caracteres
    // Evita chamadas ao backend quando não há conversa no Meet
    if (!transcricaoParcial || transcricaoParcial.trim().length < 20) {
      exibirAvisoLegenda();
      return;
    }

    const payload = {
      transcricao_parcial: transcricaoParcial,
      historico: montarHistorico(),
      perfil_disc_atual: estado.perfilDiscAtual,
      mapa_financeiro: estado.mapaFinanceiro,
    };

    const url = CONFIG.backendUrl + '/tempo-real';

    // PROXY VIA BACKGROUND.JS
    // O fetch é delegado ao background.js para contornar o bloqueio do
    // Service Worker do Google Meet (meetsw.js) que intercepta requisições
    // externas feitas diretamente por content scripts.
    chrome.runtime.sendMessage(
      { tipo: 'fetchBackend', url: url, payload: payload },
      function (resp) {
        if (resp && resp.ok) {
          var dados = resp.data;
          estado.backendOnline = true;
          // Merge mapa_financeiro retornado com o estado local
          if (dados.mapa_financeiro && typeof dados.mapa_financeiro === 'object') {
            Object.keys(dados.mapa_financeiro).forEach(function (campo) {
              var valor = dados.mapa_financeiro[campo];
              if (campo === 'produto_indicado') {
                if (valor && typeof valor === 'object') {
                  estado.mapaFinanceiro.produto_indicado = estado.mapaFinanceiro.produto_indicado || {};
                  Object.keys(valor).forEach(function (k) {
                    if (valor[k] !== null && valor[k] !== '') {
                      estado.mapaFinanceiro.produto_indicado[k] = valor[k];
                    }
                  });
                }
              } else if (valor !== null && valor !== '') {
                estado.mapaFinanceiro[campo] = valor;
              }
            });
          }
          atualizarSidebarComResposta(dados);
          if (dados.perfil_disc && dados.perfil_disc.tipo) estado.perfilDiscAtual = dados.perfil_disc.tipo;
          estado.contador = CONFIG.intervaloAnalise;
        } else {
          console.warn('[SALEIA] Backend offline:', resp ? resp.error : 'sem resposta');
          estado.backendOnline = false;
          exibirErroBackend();
        }
      }
    );
  }

  function atualizarSidebarComResposta(dados) {
    // ⚠️ ALERTA URGENTE
    const alertaBox = document.getElementById('saleia-alerta');
    const alertaTexto = document.getElementById('saleia-alerta-texto');
    if (dados.alerta_urgente) {
      alertaTexto.textContent = dados.alerta_urgente;
      alertaBox.style.display = 'block';
      alertaBox.classList.add('saleia-pulse');
    } else {
      alertaBox.style.display = 'none';
      alertaBox.classList.remove('saleia-pulse');
    }

    // 🎯 PERFIL DISC
    if (dados.perfil_disc) {
      const disc = dados.perfil_disc;
      const corDisc = { D: '#ff4444', I: '#f0c040', S: '#4caf50', C: '#42a5f5' };
      const cor = corDisc[disc.tipo] || '#ffffff';
      document.getElementById('saleia-disc-texto').innerHTML =
        '<span class="saleia-badge" style="background:' + cor + '">' + escaparHtml(disc.tipo) + '</span> ' +
        '<strong>' + escaparHtml(disc.confianca) + '</strong><br>' +
        '<em>' + escaparHtml(disc.evidencia) + '</em>' +
        (disc.como_tratar ? '<br><span class="saleia-como-tratar">' + escaparHtml(disc.como_tratar) + '</span>' : '');
    }

    // 💰 MAPA FINANCEIRO
    var mapa = estado.mapaFinanceiro;
    var mapaLinhas = [];
    if (mapa.faturamento_mensal) mapaLinhas.push('<div class="saleia-mapa-linha"><span class="saleia-mapa-label">Faturamento:</span> ' + escaparHtml(mapa.faturamento_mensal) + '</div>');
    if (mapa.renda_clt) mapaLinhas.push('<div class="saleia-mapa-linha"><span class="saleia-mapa-label">Renda CLT:</span> ' + escaparHtml(mapa.renda_clt) + '</div>');
    if (mapa.capacidade_investimento) mapaLinhas.push('<div class="saleia-mapa-linha"><span class="saleia-mapa-label">Capacidade:</span> ' + escaparHtml(mapa.capacidade_investimento) + '</div>');
    if (mapa.cartao_credito_limite) mapaLinhas.push('<div class="saleia-mapa-linha"><span class="saleia-mapa-label">Cartão:</span> ' + escaparHtml(mapa.cartao_credito_limite) + '</div>');
    if (mapa.produto_indicado && mapa.produto_indicado.nome) {
      mapaLinhas.push('<div class="saleia-mapa-linha saleia-mapa-produto"><span class="saleia-mapa-label">Produto:</span> <strong>' + escaparHtml(mapa.produto_indicado.nome) + '</strong>' +
        (mapa.produto_indicado.justificativa ? '<br><em>' + escaparHtml(mapa.produto_indicado.justificativa) + '</em>' : '') + '</div>');
    }
    document.getElementById('saleia-mapa-financeiro-texto').innerHTML =
      mapaLinhas.length > 0 ? mapaLinhas.join('') : 'Aguardando dados financeiros...';

    // 🌡️ TEMPERATURA
    if (dados.temperatura) {
      var temp = dados.temperatura;
      var tempEl = document.getElementById('saleia-temperatura');
      var nivelClasse = { alta: 'saleia-temperatura-alta', media: 'saleia-temperatura-media', baixa: 'saleia-temperatura-baixa' };
      tempEl.className = 'saleia-secao saleia-temperatura ' + (nivelClasse[temp.nivel] || '');
      document.getElementById('saleia-temperatura-texto').innerHTML =
        '<strong>' + escaparHtml(temp.nivel) + '</strong> · ' + escaparHtml(temp.entonacao) + '<br>' +
        '<em>' + escaparHtml(temp.sinal) + '</em><br>' +
        '<span class="saleia-acao">' + escaparHtml(temp.acao) + '</span>';
    }

    // 💬 PRÓXIMA FALA
    if (dados.proxima_fala) {
      document.getElementById('saleia-proxima-fala-texto').innerHTML =
        '<span class="saleia-verde">' + escaparHtml(dados.proxima_fala) + '</span>';
    }

    // 🛡️ OBJEÇÃO DETECTADA
    const objecaoEl = document.getElementById('saleia-objecao');
    if (dados.objecao_detectada && dados.objecao_detectada.objecao) {
      var obj = dados.objecao_detectada;
      document.getElementById('saleia-objecao-texto').innerHTML =
        '<strong>' + escaparHtml(obj.objecao) + '</strong>' +
        (obj.resposta_pronta ? '<br><span class="saleia-resposta">↳ ' + escaparHtml(obj.resposta_pronta) + '</span>' : '');
      objecaoEl.style.display = 'block';
    } else {
      objecaoEl.style.display = 'none';
    }

    // 🔔 DADO ESQUECIDO
    const dadoEsquecidoEl = document.getElementById('saleia-dado-esquecido');
    if (dados.dado_esquecido) {
      document.getElementById('saleia-dado-esquecido-texto').textContent = dados.dado_esquecido;
      dadoEsquecidoEl.style.display = 'block';
    } else {
      dadoEsquecidoEl.style.display = 'none';
    }

    animarAtualizacao();
  }

  function animarAtualizacao() {
    const body = document.getElementById('saleia-body');
    if (!body) return;
    body.classList.remove('saleia-fade-in');
    void body.offsetWidth;
    body.classList.add('saleia-fade-in');
  }

  function exibirErroBackend() {
    const statusEl = document.getElementById('saleia-status');
    if (statusEl) statusEl.innerHTML = '<span class="saleia-dot saleia-dot-vermelho"></span> Backend offline — verifique se o SALEIA está rodando';
  }

  function atualizarStatusSidebar() {
    const statusEl = document.getElementById('saleia-status');
    if (!statusEl) return;
    if (estado.ativo) {
      statusEl.innerHTML = '<span class="saleia-dot"></span> Monitorando...';
    } else {
      statusEl.innerHTML = '<span class="saleia-dot saleia-dot-cinza"></span> Pausado';
    }
  }

})();
