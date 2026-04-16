/**
 * SALEIA — content.js
 * Script principal que roda dentro do Google Meet.
 * Responsável por:
 *  1. Injetar a sidebar lateral de dicas
 *  2. Capturar legendas/captions via MutationObserver
 *  3. Enviar transcrição ao backend a cada 60 segundos
 *  4. Exibir respostas da IA na sidebar
 */

(function () {
  'use strict';

  // ─────────────────────────────────────────────
  // CONFIGURAÇÕES PADRÃO
  // ─────────────────────────────────────────────
  const CONFIG = {
    backendUrl: 'http://localhost:8000',
    intervaloAnalise: 60, // segundos
    maxTranscricaoRecente: 2 * 60,  // 2 minutos em chars ~
    maxHistorico: 5 * 60,           // 5 minutos
  };

  // Estado interno da extensão
  const estado = {
    ativo: true,
    transcricao: [],          // [{speaker, text, timestamp}]
    historicoResumo: '',
    perfilDiscAtual: null,
    contador: CONFIG.intervaloAnalise,
    sidebarMinimizada: false,
    timerContador: null,
    timerEnvio: null,
    backendOnline: true,
  };

  // ─────────────────────────────────────────────
  // CARREGAR CONFIGURAÇÕES DO STORAGE
  // ─────────────────────────────────────────────
  chrome.storage.local.get(['saleliaBackendUrl', 'saleliaAtivo'], function (result) {
    if (result.saleliaBackendUrl) {
      CONFIG.backendUrl = result.saleliaBackendUrl;
    }
    if (result.saleliaAtivo === false) {
      estado.ativo = false;
    }
    iniciar();
  });

  // ─────────────────────────────────────────────
  // INICIALIZAÇÃO
  // ─────────────────────────────────────────────
  function iniciar() {
    if (document.getElementById('saleia-sidebar')) return; // já injetado

    criarSidebar();
    iniciarObservadorLegendas();
    iniciarContadorRegressivo();
    iniciarEnvioPeriodico();

    // Ouvir mensagens do popup/background
    chrome.runtime.onMessage.addListener(function (msg) {
      if (msg.tipo === 'toggle') {
        estado.ativo = msg.valor;
        atualizarStatusSidebar();
      }
      if (msg.tipo === 'backendUrl') {
        CONFIG.backendUrl = msg.valor;
      }
    });
  }

  // ─────────────────────────────────────────────
  // CRIAR SIDEBAR
  // ─────────────────────────────────────────────
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

        <div id="saleia-proxima-fala" class="saleia-secao">
          <div class="saleia-secao-titulo">💬 PRÓXIMA FALA</div>
          <div id="saleia-proxima-fala-texto">Aguardando...</div>
        </div>

        <div id="saleia-sinal-financeiro" class="saleia-secao" style="display:none">
          <div class="saleia-secao-titulo">💰 SINAL FINANCEIRO</div>
          <div id="saleia-sinal-financeiro-texto"></div>
        </div>

        <div id="saleia-produto" class="saleia-secao" style="display:none">
          <div class="saleia-secao-titulo">📦 PRODUTO INDICADO</div>
          <div id="saleia-produto-texto"></div>
        </div>

        <div id="saleia-oportunidade" class="saleia-secao" style="display:none">
          <div class="saleia-secao-titulo">⚡ OPORTUNIDADE</div>
          <div id="saleia-oportunidade-texto"></div>
        </div>

        <div id="saleia-objecoes" class="saleia-secao" style="display:none">
          <div class="saleia-secao-titulo">🛡️ OBJEÇÕES</div>
          <div id="saleia-objecoes-texto"></div>
        </div>

        <div id="saleia-legenda-aviso" class="saleia-secao saleia-aviso" style="display:none">
          ⚠️ Ative as legendas no Meet:<br>
          Clique em "CC" na barra inferior do Meet
        </div>

        <div id="saleia-contador">Próxima análise em: 60s</div>
      </div>
    `;

    document.body.appendChild(sidebar);

    // Botão de toggle minimizar
    document.getElementById('saleia-toggle-btn').addEventListener('click', function () {
      estado.sidebarMinimizada = !estado.sidebarMinimizada;
      const body = document.getElementById('saleia-body');
      body.style.display = estado.sidebarMinimizada ? 'none' : 'block';
      this.textContent = estado.sidebarMinimizada ? '▶' : '≡';
      sidebar.style.width = estado.sidebarMinimizada ? '44px' : '280px';
    });
  }

  // ─────────────────────────────────────────────
  // CAPTURAR LEGENDAS VIA MUTATIONOBSERVER
  // ─────────────────────────────────────────────

  // Seletores que o Google Meet usa para exibir captions
  // (O Meet muda classes frequentemente — usamos múltiplos)
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

  // Texto já capturado para evitar duplicatas
  const textoCapturado = new Set();
  let legendasDetectadas = false;
  let verificacaoLegendaTimer = null;

  function iniciarObservadorLegendas() {
    const observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        mutation.addedNodes.forEach(function (node) {
          if (node.nodeType !== Node.ELEMENT_NODE) return;

          // Verifica o próprio nó e descendentes para cada seletor
          CAPTION_SELECTORS.forEach(function (sel) {
            try {
              // Verifica se o próprio nó corresponde
              if (node.matches && node.matches(sel)) {
                processarElementoLegenda(node);
              }
              // Busca dentro do nó
              const filhos = node.querySelectorAll ? node.querySelectorAll(sel) : [];
              filhos.forEach(processarElementoLegenda);
            } catch (e) {
              // Seletor inválido — ignora silenciosamente
            }
          });
        });
      });
    });

    observer.observe(document.body, { childList: true, subtree: true });

    // Verificar periodicamente se as legendas estão ativas
    verificacaoLegendaTimer = setInterval(verificarLegendas, 10000);
  }

  function processarElementoLegenda(el) {
    if (!el || !el.textContent) return;
    const texto = el.textContent.trim();
    if (!texto || texto.length < 3) return;

    // Evitar capturar o conteúdo da própria sidebar
    if (el.closest && el.closest('#saleia-sidebar')) return;

    // Chave única para evitar duplicatas
    const chave = texto.substring(0, 80);
    if (textoCapturado.has(chave)) return;
    textoCapturado.add(chave);

    // Manter o Set com tamanho razoável
    if (textoCapturado.size > 500) {
      const primeiro = textoCapturado.values().next().value;
      textoCapturado.delete(primeiro);
    }

    legendasDetectadas = true;

    // Tentar detectar o falante (Meet mostra nome acima da legenda)
    let speaker = 'Participante';
    const speakerEl = el.closest('[class*="caption"]');
    if (speakerEl) {
      const nomeEl = speakerEl.querySelector('[class*="zs7s8d"]') ||
                     speakerEl.querySelector('[class*="NWpY1"]') ||
                     speakerEl.querySelector('strong') ||
                     speakerEl.querySelector('b');
      if (nomeEl && nomeEl.textContent.trim()) {
        speaker = nomeEl.textContent.trim();
      }
    }

    estado.transcricao.push({
      speaker: speaker,
      text: texto,
      timestamp: new Date().toISOString(),
    });

    // Atualizar aviso de legendas
    ocultarAvisoLegenda();
  }

  function verificarLegendas() {
    if (!legendasDetectadas) {
      exibirAvisoLegenda();
    }
  }

  function exibirAvisoLegenda() {
    const aviso = document.getElementById('saleia-legenda-aviso');
    if (aviso) aviso.style.display = 'block';
  }

  function ocultarAvisoLegenda() {
    const aviso = document.getElementById('saleia-legenda-aviso');
    if (aviso) aviso.style.display = 'none';
  }

  // ─────────────────────────────────────────────
  // CONTADOR REGRESSIVO
  // ─────────────────────────────────────────────
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
    if (el) {
      el.textContent = 'Próxima análise em: ' + estado.contador + 's';
    }
  }

  // ─────────────────────────────────────────────
  // ENVIO PERIÓDICO AO BACKEND
  // ─────────────────────────────────────────────
  function iniciarEnvioPeriodico() {
    estado.timerEnvio = setInterval(function () {
      if (estado.ativo) {
        enviarParaBackend();
      }
    }, CONFIG.intervaloAnalise * 1000);
  }

  function montarTranscricaoParcial() {
    // Pegar os últimos 2 minutos de transcrição (aprox. últimas 60 entradas)
    const recentes = estado.transcricao.slice(-60);
    return recentes.map(function (item) {
      return item.speaker + ': ' + item.text;
    }).join('\n');
  }

  function montarHistorico() {
    // Usar o resumo acumulado ou os últimos 5 minutos
    if (estado.historicoResumo) return estado.historicoResumo;
    const historico = estado.transcricao.slice(-150);
    return historico.map(function (item) {
      return item.speaker + ': ' + item.text;
    }).join('\n');
  }

  function enviarParaBackend() {
    const transcricaoParcial = montarTranscricaoParcial();

    if (!transcricaoParcial && !legendasDetectadas) {
      // Sem transcrição — mostrar aviso
      exibirAvisoLegenda();
      return;
    }

    const payload = {
      transcricao_parcial: transcricaoParcial,
      historico: montarHistorico(),
      perfil_disc_atual: estado.perfilDiscAtual,
    };

    const url = CONFIG.backendUrl + '/tempo-real';

    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (dados) {
        estado.backendOnline = true;
        atualizarSidebarComResposta(dados);

        // Salvar perfil DISC para enviar na próxima chamada
        if (dados.perfil_disc && dados.perfil_disc.tipo) {
          estado.perfilDiscAtual = dados.perfil_disc.tipo;
        }

        // Atualizar histórico resumido se veio do backend
        if (dados.historico_resumido) {
          estado.historicoResumo = dados.historico_resumido;
        }

        // Reiniciar contador
        estado.contador = CONFIG.intervaloAnalise;
      })
      .catch(function (err) {
        console.warn('[SALEIA] Backend offline:', err.message);
        estado.backendOnline = false;
        exibirErroBackend();
      });
  }

  // ─────────────────────────────────────────────
  // ATUALIZAR SIDEBAR COM RESPOSTA DO BACKEND
  // ─────────────────────────────────────────────
  function atualizarSidebarComResposta(dados) {
    // Alerta urgente
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

    // Perfil DISC
    if (dados.perfil_disc) {
      const disc = dados.perfil_disc;
      const tipo = disc.tipo || '';
      const confianca = disc.confianca || '';
      const evidencia = disc.evidencia || '';
      const acaoSugerida = disc.acao_sugerida || '';

      const corDisc = { D: '#ff4444', I: '#f0c040', S: '#4caf50', C: '#42a5f5' };
      const cor = corDisc[tipo] || '#ffffff';

      document.getElementById('saleia-disc-texto').innerHTML =
        '<span class="saleia-badge" style="background:' + cor + '">' + tipo + '</span> ' +
        '<strong>' + confianca + '</strong><br>' +
        '<em>' + evidencia + '</em>' +
        (acaoSugerida ? '<br><span class="saleia-acao">' + acaoSugerida + '</span>' : '');
    }

    // Próxima ação / fala sugerida
    if (dados.proxima_acao) {
      document.getElementById('saleia-proxima-fala-texto').innerHTML =
        '<span class="saleia-verde">' + dados.proxima_acao + '</span>';
    }

    // Sinal financeiro
    const sinalEl = document.getElementById('saleia-sinal-financeiro');
    if (dados.sinal_financeiro) {
      document.getElementById('saleia-sinal-financeiro-texto').textContent = dados.sinal_financeiro;
      sinalEl.style.display = 'block';
    } else {
      sinalEl.style.display = 'none';
    }

    // Produto indicado
    const produtoEl = document.getElementById('saleia-produto');
    if (dados.produto_indicado) {
      document.getElementById('saleia-produto-texto').innerHTML =
        '<strong>' + dados.produto_indicado.nome + '</strong><br>' +
        'R$ ' + dados.produto_indicado.valor + '<br>' +
        '<em>' + dados.produto_indicado.justificativa + '</em>';
      produtoEl.style.display = 'block';
    } else {
      produtoEl.style.display = 'none';
    }

    // Oportunidade perdida
    const oportunidadeEl = document.getElementById('saleia-oportunidade');
    if (dados.oportunidade_perdida) {
      document.getElementById('saleia-oportunidade-texto').textContent = dados.oportunidade_perdida;
      oportunidadeEl.style.display = 'block';
    } else {
      oportunidadeEl.style.display = 'none';
    }

    // Objeções
    const objecoesEl = document.getElementById('saleia-objecoes');
    if (dados.objecoes && dados.objecoes.length > 0) {
      const html = dados.objecoes.map(function (obj) {
        return '<div class="saleia-objecao">' +
               '<strong>' + obj.objecao + '</strong>' +
               (obj.resposta ? '<br><span class="saleia-resposta">↳ ' + obj.resposta + '</span>' : '') +
               '</div>';
      }).join('');
      document.getElementById('saleia-objecoes-texto').innerHTML = html;
      objecoesEl.style.display = 'block';
    } else {
      objecoesEl.style.display = 'none';
    }

    // Animar atualização
    animarAtualizacao();
  }

  function animarAtualizacao() {
    const body = document.getElementById('saleia-body');
    if (!body) return;
    body.classList.remove('saleia-fade-in');
    // Forçar reflow para reiniciar animação
    void body.offsetWidth;
    body.classList.add('saleia-fade-in');
  }

  function exibirErroBackend() {
    const statusEl = document.getElementById('saleia-status');
    if (statusEl) {
      statusEl.innerHTML = '<span class="saleia-dot saleia-dot-vermelho"></span> Backend offline — verifique se o SALEIA está rodando';
    }
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
