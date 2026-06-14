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
    return limparFrasesGatilho(String(str))
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function limparFrasesGatilho(str) {
    var texto = String(str || '');
    [
      /deixa\s+eu\s+ver\s+se\s+entendi/gi,
      /pelo\s+que\s+voc[eé?]\s+me\s+falou/gi,
      /foi\s+isso\s+que\s+eu\s+colhi/gi,
      /s[oó?]\s+para\s+confirmar/gi
    ].forEach(function (pattern) {
      texto = texto.replace(pattern, '');
    });
    return texto.replace(/\s{2,}/g, ' ').replace(/\s+([,.;:!?])/g, '$1').trim();
  }

  const CONFIG = {
    backendUrl: 'https://api.saleia.app.br',
    intervaloAnalise: 60,
    maxTranscricaoRecente: 2 * 60,
    maxHistorico: 5 * 60,
  };

  // Extrai o código da reunião do Google Meet da URL (ex: abc-defg-hij)
  // Retorna null se a URL não for de uma reunião real (página inicial, /landing, etc.)
  function obterMeetingId() {
    var m = window.location.pathname.match(/\/([a-z]{3}-[a-z]{4}-[a-z]{3})/i);
    return m ? m[1] : null;
  }
  var MEETING_ID = obterMeetingId();

  // Não ativar fora de uma reunião real
  if (!MEETING_ID) return;

  const estado = {
    ativo: true,
    transcricao: [],
    historicoResumo: '',
    perfilDiscAtual: null,
    mapaFinanceiro: {},
    recapitulacaoViva: null,
    recapitulacaoVivaOculta: false,
    recapitulacaoVivaUsada: false,
    contador: CONFIG.intervaloAnalise,
    sidebarMinimizada: false,
    timerContador: null,
    timerEnvio: null,
    backendOnline: true,
    ultimoIndexEnviado: 0,  // tracks last committed entry sent to DB
    participantes: {
      vendedor: 'Vendedor',
      clientes: ['Cliente'],
    },
  };

  chrome.storage.local.get(['saleiaBackendUrl', 'saleiaAtivo'], function (result) {
    if (result.saleiaBackendUrl) CONFIG.backendUrl = result.saleiaBackendUrl;
    if (result.saleiaAtivo === false) estado.ativo = false;
    chrome.storage.local.get(['saleiaParticipantes'], function (dadosParticipantes) {
      if (dadosParticipantes.saleiaParticipantes) {
        var saved = dadosParticipantes.saleiaParticipantes;
        estado.participantes.vendedor = saved.vendedor || 'Vendedor';
        if (Array.isArray(saved.clientes) && saved.clientes.length) {
          estado.participantes.clientes = saved.clientes;
        } else if (saved.cliente) {
          estado.participantes.clientes = [saved.cliente];
        }
      }
      iniciar();
    });
  });

  function iniciar() {
    if (document.getElementById('saleia-sidebar')) return;
    criarSidebar();
    iniciarObservadorLegendas();
    iniciarContadorRegressivo();
    iniciarEnvioPeriodico();
    registrarSessao();

    // Botão de captura de áudio (Whisper) — MediaRecorder direto no content.js
    // O prompt de microfone aparece na barra da aba do Meet (contexto visível)
    var capturaAudioAtiva = false;
    var whisperRecorder = null;
    var whisperStream = null;
    var whisperMimeType = 'audio/webm';
    var whisperCicloTimer = null;
    var btnAudio = document.getElementById('saleia-btn-audio-capture');
    var statusAudio = document.getElementById('saleia-audio-status');
    function setAudioStatus(txt, cor) {
      if (statusAudio) { statusAudio.textContent = txt; statusAudio.style.color = cor || '#888'; }
    }
    function pararWhisper() {
      capturaAudioAtiva = false;
      if (whisperCicloTimer) { clearTimeout(whisperCicloTimer); whisperCicloTimer = null; }
      if (whisperRecorder && whisperRecorder.state !== 'inactive') {
        whisperRecorder.stop();
      }
      if (whisperStream) {
        whisperStream.getTracks().forEach(function (t) { t.stop(); });
        whisperStream = null;
      }
      whisperRecorder = null;
    }
    // Cada ciclo: start() → 15s → stop() → ondataavailable com WebM completo (com header)
    // Isso garante que cada chunk enviado ao Whisper é um arquivo WebM válido e independente.
    function iniciarCicloWhisper() {
      if (!capturaAudioAtiva || !whisperStream || !whisperStream.active) return;
      whisperRecorder = new MediaRecorder(whisperStream, { mimeType: whisperMimeType });
      whisperRecorder.ondataavailable = function (e) {
        // Áudio silencioso em WebM/opus gera ~2-4KB; exigir >10KB garante fala real
        if (e.data && e.data.size > 10240) enviarChunkWhisper(e.data);
      };
      whisperRecorder.onerror = function (e) {
        console.error('[SALEIA] MediaRecorder erro:', e);
        pararWhisper();
        if (btnAudio) {
          btnAudio.textContent = '🎤 Capturar áudio (Whisper)';
          btnAudio.style.background = '#1a1a2e'; btnAudio.style.borderColor = '#00d4aa'; btnAudio.style.color = '#00d4aa';
        }
        setAudioStatus('⚠️ Erro na gravação', '#ff4444');
      };
      whisperRecorder.onstop = function () {
        // Reinicia novo ciclo se ainda ativo (garante novo header WebM a cada chunk)
        if (capturaAudioAtiva) setTimeout(iniciarCicloWhisper, 100);
      };
      whisperRecorder.start(); // sem timeslice → chunk completo no stop()
      // Para automaticamente após 15s para disparar ondataavailable
      whisperCicloTimer = setTimeout(function () {
        if (whisperRecorder && whisperRecorder.state === 'recording') {
          whisperRecorder.stop();
        }
      }, 15000);
    }
    function enviarChunkWhisper(blob) {
      var reader = new FileReader();
      reader.onloadend = function () {
        var base64 = reader.result;
        if (!base64 || base64.length < 600) return; // chunk muito pequeno
        // Rota via background.js — fetch direto é interceptado pelo SW do Meet e duplicado
        if (!chrome.runtime || !chrome.runtime.id) return;
        chrome.runtime.sendMessage({
          tipo: 'whisperChunk',
          audio_base64: base64,
          mime_type: blob.type,
          meeting_id: MEETING_ID,
          backendUrl: CONFIG.backendUrl,
        }, function (data) {
          if (data && data.texto && data.texto.trim()) {
            var texto = data.texto.trim();
            // Filtro de ruído: rejeita texto com < 3 palavras únicas (ruído de fundo / eco)
            var palavras = texto.toLowerCase().replace(/[^a-záéíóúãõâêîôûàçü\s]/g, '').split(/\s+/).filter(Boolean);
            var unicas = new Set(palavras);
            if (unicas.size < 3 && palavras.length < 6) {
              console.log('[SALEIA] chunk descartado (ruído/repetição):', texto);
              return;
            }
            commitarFrase('Audio', texto);
            setAudioStatus('🎤 ' + texto.slice(0, 50) + '…', '#00d4aa');
            enviarParaBackend();
          } else if (data && (data.ok === false || data.error)) {
            var msgErro = data.error || 'Erro desconhecido';
            console.warn('[SALEIA] Transcrição erro:', msgErro);
            setAudioStatus('⚠️ ' + msgErro.slice(0, 80), '#ff9900');
          }
        });
      };
      reader.readAsDataURL(blob);
    }
    if (btnAudio) btnAudio.addEventListener('click', function () {
      var btn = this;
      if (!capturaAudioAtiva) {
        btn.textContent = '⏳ Aguardando microfone...';
        btn.disabled = true;
        setAudioStatus('Aguardando permissão do Chrome...', '#aaa');
        navigator.mediaDevices.getUserMedia({ audio: true, video: false })
          .then(function (stream) {
            whisperStream = stream;
            whisperMimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
              ? 'audio/webm;codecs=opus' : 'audio/webm';
            capturaAudioAtiva = true;
            btn.disabled = false;
            btn.textContent = '⏹ Parar captura de áudio';
            btn.style.background = '#2d0a0a'; btn.style.borderColor = '#ff4444'; btn.style.color = '#ff4444';
            setAudioStatus('🎤 Whisper ativo — gravando...', '#00d4aa');
            iniciarCicloWhisper(); // ciclos de 15s com WebM completo a cada ciclo
          })
          .catch(function (err) {
            btn.disabled = false;
            btn.textContent = '🎤 Capturar áudio (Whisper)';
            var msg = err.name === 'NotAllowedError'
              ? '🔒 Permissão negada — clique no cadeado na barra de endereço → Microfone → Permitir → recarregue'
              : '⚠️ ' + err.message;
            setAudioStatus(msg, '#ff9900');
            console.error('[SALEIA] getUserMedia erro:', err.name, err.message);
          });
      } else {
        pararWhisper();
        btn.textContent = '🎤 Capturar áudio (Whisper)';
        btn.style.background = '#1a1a2e'; btn.style.borderColor = '#00d4aa'; btn.style.color = '#00d4aa';
        setAudioStatus('', '');
      }
    });

    chrome.runtime.onMessage.addListener(function (msg) {
      if (msg.tipo === 'toggle') { estado.ativo = msg.valor; atualizarStatusSidebar(); }
      if (msg.tipo === 'backendUrl') { CONFIG.backendUrl = msg.valor; }
      if (msg.tipo === 'backendStatus') {
        const dot = document.querySelector('#saleia-status .saleia-dot');
        const txt = document.getElementById('saleia-status');
        if (dot && txt) {
          dot.style.background = msg.online ? '#00d4aa' : '#ff4444';
          txt.childNodes[1].textContent = msg.online ? ' Monitorando...' : ' Backend offline — reconectando...';
        }
      }
    });
  }

  function criarSidebar() {
    const sidebar = document.createElement('div');
    sidebar.id = 'saleia-sidebar';
    sidebar.innerHTML = `
      <div id="saleia-header">
        <button id="saleia-toggle-btn" title="Minimizar/Expandir">≡</button>
        <button id="saleia-btn-foto" title="Capturar foto do cliente para o Visual Scenario">📸</button>
        <span>🤖 SALEIA AO VIVO</span>
      </div>
      <div id="saleia-body">
        <div id="saleia-status"><span class="saleia-dot"></span> Monitorando...</div>
        <button id="saleia-btn-participantes" class="saleia-discreto-btn" type="button">Editar participantes</button>
        <div id="saleia-participantes-resumo" class="saleia-participantes-resumo"></div>

        <div id="saleia-alerta" class="saleia-secao saleia-alerta-box" style="display:none">
          <div class="saleia-secao-titulo">⚠️ ALERTA URGENTE</div>
          <div id="saleia-alerta-texto"></div>
        </div>

        <div id="saleia-recapitulacao" class="saleia-secao saleia-recap-viva" style="display:none">
          <div class="saleia-recap-topo">
            <div class="saleia-secao-titulo">🧠 RECAPITULAÇÃO GUIADA</div>
            <span id="saleia-recap-status" class="saleia-recap-badge">nova</span>
          </div>
          <div id="saleia-recapitulacao-texto" class="saleia-recap-texto"></div>
          <div id="saleia-recap-mapa" class="saleia-recap-mapa"></div>
          <div id="saleia-recap-pergunta" class="saleia-recap-bloco"></div>
          <div id="saleia-recap-dica" class="saleia-recap-dica"></div>
          <div id="saleia-recap-faltantes" class="saleia-recap-faltantes"></div>
          <div class="saleia-recap-acoes">
            <button id="saleia-btn-copiar-fala" class="saleia-recap-btn">Copiar fala</button>
            <button id="saleia-btn-regenerar-recap" class="saleia-recap-btn">Regenerar</button>
            <button id="saleia-btn-marcar-usado" class="saleia-recap-btn">Marcar como usado</button>
            <button id="saleia-btn-fechar-recap" class="saleia-recap-btn">Fechar</button>
          </div>
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

        <div id="saleia-stage-kare" class="saleia-stage-kare" style="display:none"></div>

        <div id="saleia-nbq" class="saleia-secao saleia-nbq-box">
          <div class="saleia-secao-titulo">🎯 PRÓXIMA MELHOR AÇÃO</div>
          <div id="saleia-nbq-badges"></div>
          <div id="saleia-nbq-objetivo" class="saleia-nbq-objetivo"></div>
          <div id="saleia-nbq-pergunta" class="saleia-nbq-pergunta">Aguardando análise...</div>
          <div id="saleia-nbq-motivo" class="saleia-nbq-motivo"></div>
          <div id="saleia-nbq-risco" class="saleia-nbq-risco" style="display:none"></div>
          <div id="saleia-nbq-followup" class="saleia-nbq-followup" style="display:none"></div>
          <div id="saleia-nbq-impacto" class="saleia-nbq-impacto"></div>
          <button id="saleia-nbq-copiar" class="saleia-discreto-btn" style="margin-top:6px;display:none">📋 Copiar</button>
        </div>

        <div id="saleia-maturity" class="saleia-secao saleia-maturity-box" style="display:none">
          <div class="saleia-secao-titulo">📊 MATURIDADE DA OPORTUNIDADE</div>
          <div id="saleia-maturity-total" class="saleia-maturity-total"></div>
          <div id="saleia-maturity-grid" class="saleia-maturity-grid"></div>
        </div>

        <div id="saleia-objecao" class="saleia-secao" style="display:none">
          <div class="saleia-secao-titulo">🛡️ OBJEÇÃO DETECTADA</div>
          <div id="saleia-objecao-texto"></div>
        </div>

        <div id="saleia-dado-esquecido" class="saleia-secao saleia-dado-esquecido" style="display:none">
          <div class="saleia-secao-titulo">🔔 DADO ESQUECIDO</div>
          <div id="saleia-dado-esquecido-texto"></div>
        </div>

        <div id="saleia-score" class="saleia-secao" style="display:none">
          <div class="saleia-secao-titulo">📊 SCORE DE COMPRA</div>
          <div id="saleia-score-valor" style="font-size:1.6rem;font-weight:700;color:#00d4aa">--</div>
          <div id="saleia-score-barra" style="background:#333;border-radius:4px;height:8px;margin:6px 0">
            <div id="saleia-score-fill" style="height:100%;border-radius:4px;transition:width .6s ease;background:#00d4aa"></div>
          </div>
          <div id="saleia-score-texto" style="font-size:.8rem;color:#aaa"></div>
          <button id="saleia-btn-cenario"
            style="margin-top:10px;width:100%;padding:8px;background:linear-gradient(135deg,#00d4aa,#0099cc);
                   color:#fff;border:none;border-radius:6px;font-size:.85rem;font-weight:600;cursor:pointer">
            📊 Abrir cenário do cliente
          </button>
        </div>

        <div id="saleia-legenda-aviso" class="saleia-secao saleia-aviso" style="display:none">
          ⚠️ Ative as legendas no Meet:<br>
          Clique em "CC" na barra inferior do Meet
        </div>
        <div id="saleia-debug-count" style="font-size:.75rem;color:#666;margin-top:4px"></div>
        <button id="saleia-btn-audio-capture"
          style="margin:6px 0 2px;width:100%;padding:7px;background:#1a1a2e;border:1px solid #00d4aa;
                 color:#00d4aa;border-radius:6px;font-size:.8rem;font-weight:600;cursor:pointer">
          🎤 Capturar áudio (Whisper)
        </button>
        <div id="saleia-audio-status" style="font-size:.73rem;min-height:1.1em;margin-bottom:2px;padding:0 2px"></div>
        <div id="saleia-contador">Próxima análise em: 60s</div>
      </div>
      <div id="saleia-participantes-modal" class="saleia-modal" style="display:none">
        <div class="saleia-modal-card">
          <div class="saleia-modal-title">Participantes</div>
          <label>Nome do vendedor</label>
          <input id="saleia-input-vendedor" type="text" placeholder="Vendedor" />
          <div style="display:flex;align-items:center;justify-content:space-between;margin:10px 0 5px">
            <label style="margin:0;color:#888;font-size:12px">Clientes</label>
            <button id="saleia-btn-add-cliente" style="background:none;border:1px dashed rgba(212,175,55,0.5);color:#D4AF37;padding:2px 10px;border-radius:6px;font-size:11px;cursor:pointer;font-weight:700">+ Adicionar</button>
          </div>
          <div id="saleia-clientes-lista"></div>
          <div class="saleia-modal-actions">
            <button id="saleia-btn-salvar-participantes" class="saleia-recap-btn">Salvar</button>
            <button id="saleia-btn-cancelar-participantes" class="saleia-recap-btn">Cancelar</button>
          </div>
        </div>
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
    document.getElementById('saleia-btn-cenario').addEventListener('click', function () {
      if (!chrome.runtime || !chrome.runtime.id) return;
      chrome.runtime.sendMessage({ tipo: 'abrirCenario', url: CONFIG.backendUrl + '/cenario/' + MEETING_ID });
    });

    var btnFoto = document.getElementById('saleia-btn-foto');
    if (btnFoto) btnFoto.addEventListener('click', capturarFotoCliente);
    atualizarResumoParticipantes();
    var btnParticipantes = document.getElementById('saleia-btn-participantes');
    if (btnParticipantes) btnParticipantes.addEventListener('click', abrirModalParticipantes);
    var btnSalvarParticipantes = document.getElementById('saleia-btn-salvar-participantes');
    if (btnSalvarParticipantes) btnSalvarParticipantes.addEventListener('click', salvarParticipantes);
    var btnCancelarParticipantes = document.getElementById('saleia-btn-cancelar-participantes');
    if (btnCancelarParticipantes) btnCancelarParticipantes.addEventListener('click', fecharModalParticipantes);
    var btnCopiarFala = document.getElementById('saleia-btn-copiar-fala');
    if (btnCopiarFala) {
      btnCopiarFala.addEventListener('click', function () {
        var fala = '';
        if (estado.recapitulacaoViva && estado.recapitulacaoViva.texto_falavel) {
          fala = estado.recapitulacaoViva.texto_falavel;
        } else {
          fala = document.getElementById('saleia-proxima-fala-texto') ? document.getElementById('saleia-proxima-fala-texto').innerText : '';
        }
        copiarTextoParaAreaTransferencia(fala);
      });
    }
    var btnRegenerarRecap = document.getElementById('saleia-btn-regenerar-recap');
    if (btnRegenerarRecap) {
      btnRegenerarRecap.addEventListener('click', solicitarRegeneracaoRecapitulacao);
    }
    var btnMarcarUsado = document.getElementById('saleia-btn-marcar-usado');
    if (btnMarcarUsado) {
      btnMarcarUsado.addEventListener('click', function () {
        marcarRecapitulacaoComoUsada();
      });
    }
    var btnFecharRecap = document.getElementById('saleia-btn-fechar-recap');
    if (btnFecharRecap) {
      btnFecharRecap.addEventListener('click', function () {
        fecharRecapitulacaoViva();
      });
    }
  }

  function normalizarNomeParticipante(valor) {
    return String(valor || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .trim()
      .toLowerCase();
  }

  var _clientesModal = [''];

  function renderizarClientesModal() {
    var container = document.getElementById('saleia-clientes-lista');
    if (!container) return;
    container.innerHTML = _clientesModal.map(function(nome, idx) {
      return '<div style="display:flex;gap:6px;align-items:center;margin-bottom:6px">' +
        '<input type="text" placeholder="Cliente' + (_clientesModal.length > 1 ? ' ' + (idx + 1) : '') + '" ' +
        'value="' + nome.replace(/"/g, '&quot;') + '" ' +
        'data-ci="' + idx + '" ' +
        'style="width:100%;background:#1A1A1A;color:#F0F0F0;border:1px solid rgba(212,175,55,0.25);border-radius:7px;padding:7px 10px;font-size:12px;outline:none;flex:1" />' +
        (_clientesModal.length > 1
          ? '<button data-ri="' + idx + '" style="background:none;border:1px solid rgba(239,68,68,.3);color:#EF4444;border-radius:6px;width:28px;height:28px;cursor:pointer;flex-shrink:0;font-size:13px;line-height:1">✕</button>'
          : '') +
        '</div>';
    }).join('');

    container.onclick = function(e) {
      var ri = e.target.getAttribute('data-ri');
      if (ri !== null && _clientesModal.length > 1) {
        _clientesModal.splice(parseInt(ri, 10), 1);
        renderizarClientesModal();
      }
    };

    container.oninput = function(e) {
      var ci = e.target.getAttribute('data-ci');
      if (ci !== null) _clientesModal[parseInt(ci, 10)] = e.target.value;
    };
  }

  function rotuloParticipante(speaker) {
    var nome = String(speaker || '').trim();
    var normalizado = normalizarNomeParticipante(nome);
    var vendedor = estado.participantes.vendedor || 'Vendedor';
    var clientes = estado.participantes.clientes || ['Cliente'];
    var primeiroCliente = clientes[0] || 'Cliente';

    if (!normalizado || normalizado === 'participante' || normalizado === 'cliente') return primeiroCliente;
    if (normalizado === 'voce' || normalizado === 'vendedor' || normalizado === normalizarNomeParticipante(vendedor)) return vendedor;
    for (var i = 0; i < clientes.length; i++) {
      if (clientes[i] && normalizado === normalizarNomeParticipante(clientes[i])) return clientes[i];
    }
    return nome;
  }

  function atualizarResumoParticipantes() {
    var el = document.getElementById('saleia-participantes-resumo');
    if (!el) return;
    var clientes = estado.participantes.clientes || ['Cliente'];
    el.textContent = (estado.participantes.vendedor || 'Vendedor') + ' -> ' + clientes.join(', ');
  }

  function abrirModalParticipantes() {
    var modal = document.getElementById('saleia-participantes-modal');
    if (!modal) return;
    document.getElementById('saleia-input-vendedor').value = estado.participantes.vendedor || '';
    _clientesModal = (estado.participantes.clientes || ['Cliente']).slice();
    renderizarClientesModal();
    var btnAdd = document.getElementById('saleia-btn-add-cliente');
    if (btnAdd) btnAdd.onclick = function() { _clientesModal.push(''); renderizarClientesModal(); };
    modal.style.display = 'flex';
  }

  function fecharModalParticipantes() {
    var modal = document.getElementById('saleia-participantes-modal');
    if (modal) modal.style.display = 'none';
  }

  function salvarParticipantes() {
    var inputs = document.querySelectorAll('#saleia-clientes-lista input[data-ci]');
    var clientes = [];
    inputs.forEach(function(inp) { var v = inp.value.trim(); if (v) clientes.push(v); });
    if (!clientes.length) clientes = ['Cliente'];
    estado.participantes = {
      vendedor: document.getElementById('saleia-input-vendedor').value.trim() || 'Vendedor',
      clientes: clientes,
    };
    chrome.storage.local.set({ saleiaParticipantes: estado.participantes });
    atualizarResumoParticipantes();
    fecharModalParticipantes();
  }

  // Seletores de legenda do Google Meet.
  // Lista ampla — o Meet atualiza DOM frequentemente.
  const CAPTION_SELECTORS = [
    // jsnames historicamente usados para legendas
    '[jsname="tgaKEf"]',
    '[jsname="bVMM9c"]',
    '[jsname="YSxPC"]',
    '[jsname="r4nke"]',
    '[jsname="r8qfJe"]',
    '[jsname="YPqjbf"]',
    '[jsname="dsyhDe"]',
    '[jsname="K4EGdf"]',
    // classes conhecidas
    'span[class*="bj56rb"]',
    '[class*="CNusmb"]',
    '[class*="a4cQT"]',
    '[class*="iOzk7"]',
    '[class*="KcIKyf"]',
    '[class*="TBMuR"]',
    '[class*="VfPpkd-WsjYwc"]',
    // role=region para legendas (Meet 2025+)
    '[role="region"][aria-label*="legenda" i]',
    '[role="region"][aria-label*="caption" i]',
    '[role="region"][aria-label*="transcript" i]',
    // contenedor genérico de captions ao vivo
    '[aria-live="polite"]',
    '[aria-live="assertive"]',
  ];

  // Buffer por speaker: guarda a frase ativa enquanto o speaker ainda está falando.
  // Só commita ao array de transcrição quando o speaker para (2.5s sem atualização).
  // Isso evita acumular fragmentos parciais ("Você", "de multi", "de multiplicar...").
  const captionBuffer = {};
  // Rastreia prefixos de frases já commitadas para evitar re-commit pelo scan periódico
  const jaCommitado = new Set();
  setInterval(function() { jaCommitado.clear(); }, 60000);
  let legendasDetectadas = false;
  let verificacaoLegendaTimer = null;

  function commitarFrase(speaker, texto) {
    if (!texto || texto.trim().length < 10) return;
    if (eRuidoUI(texto.trim())) return;
    speaker = rotuloParticipante(speaker);
    var t = texto.trim();
    var chave = t.substring(0, 50).toLowerCase();
    // Evita duplicata: texto igual ou já commitado recentemente
    if (jaCommitado.has(chave)) return;
    var ultimas = estado.transcricao.slice(-10);
    if (ultimas.some(function(e) {
      return e.text === t || e.text.startsWith(t) || t.startsWith(e.text);
    })) return;
    jaCommitado.add(chave);
    estado.transcricao.push({ speaker: speaker, text: t, timestamp: new Date().toISOString() });
    legendasDetectadas = true;
    ocultarAvisoLegenda();
    // Debug: mostra contagem de frases capturadas na sidebar
    var dbg = document.getElementById('saleia-debug-count');
    if (dbg) dbg.textContent = '📝 ' + estado.transcricao.length + ' frase(s) capturada(s)';
  }

  // A cada 800ms commita frases "silenciadas" (speaker parou há >2.5s)
  setInterval(function () {
    var agora = Date.now();
    Object.keys(captionBuffer).forEach(function (speaker) {
      var buf = captionBuffer[speaker];
      if (buf && agora - buf.lastSeen > 3500) {
        commitarFrase(speaker, buf.texto);
        delete captionBuffer[speaker];
      }
    });
  }, 800);

  // Extrai elementos folha de texto (sem filhos elemento) dentro de um container
  function processarFolhas(container) {
    if (!container || container.closest('#saleia-sidebar')) return;
    // Se não tem filhos elemento, é folha — processa diretamente
    var temFilhoElemento = false;
    for (var i = 0; i < container.childNodes.length; i++) {
      if (container.childNodes[i].nodeType === Node.ELEMENT_NODE) { temFilhoElemento = true; break; }
    }
    if (!temFilhoElemento) {
      processarElementoLegenda(container);
    } else {
      // Percorre filhos recursivamente até chegar nas folhas
      container.querySelectorAll('*').forEach(function(child) {
        if (child.closest('#saleia-sidebar')) return;
        var temFilho = false;
        for (var j = 0; j < child.childNodes.length; j++) {
          if (child.childNodes[j].nodeType === Node.ELEMENT_NODE) { temFilho = true; break; }
        }
        if (!temFilho && child.textContent.trim()) processarElementoLegenda(child);
      });
    }
  }

  function iniciarObservadorLegendas() {
    const observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        if (mutation.type === 'characterData' && mutation.target.parentElement) {
          var el = mutation.target.parentElement;
          if (!el.closest('#saleia-sidebar')) processarElementoLegenda(el);
        }
        if (mutation.type === 'childList') {
          mutation.addedNodes.forEach(function (node) {
            if (node.nodeType === Node.ELEMENT_NODE) processarFolhas(node);
            else if (node.nodeType === Node.TEXT_NODE && node.parentElement) {
              if (!node.parentElement.closest('#saleia-sidebar')) processarElementoLegenda(node.parentElement);
            }
          });
        }
      });
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });

    // Scan periódico: SOMENTE seletores de área de legenda CC do Meet.
    // NÃO usar [aria-live] aqui pois captura tooltips de botões.
    setInterval(function () {
      try {
        var CAPTION_SCAN = [
          // jsnames do painel de legenda CC overlay (confirmados no Meet)
          '[jsname="tgaKEf"]', '[jsname="bVMM9c"]', '[jsname="r8qfJe"]',
          '[jsname="YPqjbf"]', '[jsname="dsyhDe"]', '[jsname="K4EGdf"]',
          // classes de texto de legenda
          'span[class*="bj56rb"]',
          // painel lateral de transcrição ao vivo
          '[class*="a4cQT"]', '[class*="iOzk7"]', '[class*="NMTbpc"]'
        ];
        CAPTION_SCAN.forEach(function (sel) {
          document.querySelectorAll(sel).forEach(function (el) {
            if (!el.closest('#saleia-sidebar')) processarFolhas(el);
          });
        });
      } catch (e) {}
    }, 2000);

    verificacaoLegendaTimer = setInterval(verificarLegendas, 10000);
  }

  // Padrões de ruído do Google Meet (ícones Material + botões de UI)
  const RUIDO_REGEX = /^(arrow_downward|arrow_upward|expand_more|expand_less|close|mic|mic_off|videocam|videocam_off|more_vert|chat|people|settings|call_end|thumb_up|check|keyboard_arrow)[a-z_]*(\s.*)?$/i;
  // Ícones que podem aparecer concatenados com outro texto (ex: "arrow_downwardIr para o fim")
  const RUIDO_PREFIXO_RE = /^(arrow_downward|arrow_upward|expand_more|expand_less|keyboard_arrow_\w+|close|mic_off|videocam_off)/i;

  // Filtro abrangente de ruído da interface do Google Meet
  function eRuidoUI(texto) {
    // Nomes de idiomas do painel de configuração de legendas (incluindo compostos com vírgula)
    if (/^(Africâner|Albanês|Alemão|Amárico|Árabe|Armênio|Azerbaijano|Azerbaijanês|Basco|Bengali|Bielorrusso|Birmanês|Bósnio|Búlgaro|Canarês|Catalão|Cazaque|Cingalês|Coreano|Crioulo|Croata|Curdo|Dinamarquês|Eslovaco|Esloveno|Espanhol|Estoniano|Filipino|Finlandês|Francês|Galego|Galês|Georgiano|Grego|Gujarati|Guzerate|Hauçá|Hebraico|Hindi|Holandês|Húngaro|Igbo|Indonésio|Inglês|Irlandês|Islandês|Italiano|Japonês|Javanês|Khmer|Kinyarwanda|Laosiano|Letão|Lituano|Macedônio|Malaiala|Malaio|Marati|Mongol|Nepalês|Norueguês|Persa|Polonês|Português|Romeno|Russo|Sepedi|Sérvio|Sesoto|Suaíli|Sudanês|Sueco|Swati|Tailandês|Tâmil|Tcheco|Télugo|Tshivenda|Tswana|Turco|Ucraniano|Urdu|Uzbeque|Vietnamita|Xhosa|Xitsonga|Yorubá|Zulu)(\s*,\s*[^(]+)?(\s*\([^)]+\))?$/i.test(texto)) return true;
    // Padrão genérico: "Idioma (País/descritor)" com ≤5 palavras (apanha novos idiomas não listados)
    if (texto.split(/\s+/).length <= 5 && /^[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÈÌÒÙÇ][a-záéíóúâêîôûãõàèìòùç,\s]{1,35}\([^)]{2,40}\)$/.test(texto)) return true;
    // Opções de estilo de legenda + rótulo BETA
    if (/^(BETA|Tamanho da fonte|Padrão|Muito pequena|Pequena|Moderado|Grande|Enorme|Gigante|Cor da fonte|Branco|Preto|Azul|Verde|Vermelho|Amarelo|Ciano|Magenta)$/i.test(texto)) return true;
    // Botões e controles da UI do Meet
    if (/^(Abrir configurações de legenda|A legenda instantânea foi desativada|Ativar câmera|Desativar câmera|Ativar microfone|Desativar microfone|Compartilhar tela|Sair da chamada|Levantar a mão|Abaixar a mão|Enviar uma reação|Ferramentas da reunião|Controles do organizador|Detalhes da reunião|Planos de fundo e efeitos|Reenquadrar|Cronômetro da reunião|Pessoas|Mãos levantadas|mood|apps|info)$/i.test(texto)) return true;
    // Mensagens de sistema do Meet (prefixo — cobre versões curtas e longas)
    if (/^(Pronto para participar|Procurando outras pessoas|Só você está aqui|A câmera está iniciando|Sua câmera está (ativada|desativada)|Seu microfone está (ativado|desativado)|Sua mão está (levantada|abaixada)|Você está participando da chamada|Você foi a primeira pessoa|Sua chamada do Meet|O recurso picture-in-picture|Transferir a chamada para cá|A chamada vai terminar|Esta chamada é aberta|Acesse mais recursos|Saiba mais sobre o plano|Configurações de (áudio|vídeo)|Grupo de microfones|Padrão do sistema|Fazer um teste de gravação|Alto-falantes|Testar alto-falantes|Pressione a seta|Está desenvolvendo uma extensão|As pessoas ainda podem ver|Mais opções para|Aproveite videochamadas)/i.test(texto)) return true;
    // Diálogo "Sua reunião está pronta" (aparece ao entrar na reunião)
    if (/Sua reunião está pronta/i.test(texto)) return true;
    if (/Adicionar outras pessoas/i.test(texto)) return true;
    if (/Ou compartilhe este link/i.test(texto)) return true;
    if (/precisarão receber sua permissão/i.test(texto)) return true;
    if (/Participando como /i.test(texto)) return true;
    if (/content_copy|Copiar link/i.test(texto)) return true;
    // Avisos de privacidade / denúncia de abuso do Meet
    if (/denunciar abus|privacy_tip|clipe curto|enviado ao Google para verifica/i.test(texto)) return true;
    if (/^Saiba como denunciar/i.test(texto)) return true;
    if (/Se algu[eé]m.*denunciar abuso/i.test(texto)) return true;
    // Notificações de modo tela cheia
    if (/modo tela cheia|Pressione Escape para sair/i.test(texto)) return true;
    // Qualquer texto que contenha URL do Meet embutida
    if (/meet\.google\.com/i.test(texto)) return true;
    // Avisos do Chrome sobre extensões modificando a página
    if (/extensões que modificam|modifying the page|modificar a p[aá]gina/i.test(texto)) return true;
    if (/estabilidade|experi[eê]ncia do usu[aá]rio|desenvolvedores|cuidado com as extens/i.test(texto)) return true;
    // Ícones Material concatenados com texto de UI (ex: "closeFecharperson_add")
    if (/closeFech|person_add|close[A-Z]/i.test(texto)) return true;
    // Atalhos de teclado (ex: "Desativar microfone (ctrl + d)", "Ativar legendas (c ou shift + c)")
    if (/\(ctrl\s*\+/i.test(texto)) return true;
    if (/\([a-z]\s+ou\s+shift\s*\+|shift\s*\+\s*[a-z]\)/i.test(texto)) return true;
    // Textos de botão com atalho concatenado
    if (/ativar legendas|desativar legendas/i.test(texto)) return true;
    if (/^mais opções$/i.test(texto)) return true;
    if (/^opções de legenda/i.test(texto)) return true;
    // Código de reunião (ex: "zpr-bcqe-bub")
    if (/^[a-z]{3}-[a-z]{4}-[a-z]{3}$/i.test(texto)) return true;
    // URLs sozinhas
    if (/^https?:\/\//.test(texto) && texto.split(' ').length < 5) return true;
    // Nomes de dispositivos/câmeras: 2-4 palavras, todas capitalizadas, sem verbos/conjunções PT
    // Ex: "Positivo Theia Camera", "Logitech HD Webcam C920"
    var palavrasDevice = texto.split(/\s+/);
    if (palavrasDevice.length >= 2 && palavrasDevice.length <= 4 &&
        palavrasDevice.every(function(p) { return /^[A-Z0-9]/.test(p); }) &&
        !/\b(o|a|os|as|um|uma|de|da|do|das|dos|em|na|no|por|para|com|que|se|não|eu|você|ele|ela|nós|eles|isso|como|mais|mas|ou|é|são|está|tem|foi|ser|ter|vai|aqui|já|então|agora|muito|bem|sim|não)\b/i.test(texto) &&
        !/[.,!?;:]/.test(texto)) {
      return true;
    }
    return false;
  }

  function processarElementoLegenda(el) {
    if (!el || !el.textContent) return;
    if (el.closest && el.closest('#saleia-sidebar')) return;
    var texto = el.textContent.trim();
    // Mínimo: 2 palavras e 10 chars para ser fala real
    if (!texto || texto.length < 10) return;
    if (texto.split(/\s+/).length < 2) return;
    if (RUIDO_REGEX.test(texto)) return;
    if (RUIDO_PREFIXO_RE.test(texto)) return;
    if (eRuidoUI(texto)) return;
    if (texto.includes('Ir para o fim') || texto.includes('Go to the end')) return;
    // Debug: loga o que passa pelo filtro para identificar elementos reais de CC
    console.log('[SALEIA-DBG] tag=' + el.tagName + ' class="' + (el.className||'') + '" jsname="' + (el.getAttribute&&el.getAttribute('jsname')||'') + '" aria-live="' + (el.getAttribute&&el.getAttribute('aria-live')||'') + '" texto="' + texto.substring(0,80) + '"');

    // Detectar speaker
    var speaker = 'Participante';
    var speakerEl = el.closest('[class*="a4cQT"]') || el.closest('[class*="caption"]');
    if (speakerEl) {
      var nomeEl = speakerEl.querySelector('[class*="zs7s8d"]') ||
                   speakerEl.querySelector('[class*="NWpY1"]') ||
                   speakerEl.querySelector('strong') ||
                   speakerEl.querySelector('b');
      if (nomeEl && nomeEl.textContent.trim()) speaker = nomeEl.textContent.trim();
    }

    // Remove o nome do speaker do início do texto se estiver concatenado (ex: "VocêQue nos ajudou")
    if (speaker !== 'Participante' && texto.toLowerCase().startsWith(speaker.toLowerCase())) {
      texto = texto.substring(speaker.length).trim();
      if (!texto || texto.length < 15 || texto.split(/\s+/).length < 3) return;
    }

    // Ignora se já foi commitado recentemente (evita re-commit pelo scan periódico)
    speaker = rotuloParticipante(speaker);
    var chaveTexto = texto.substring(0, 50).toLowerCase();
    if (jaCommitado.has(chaveTexto)) return;

    var agora = Date.now();
    var buf = captionBuffer[speaker];

    if (!buf) {
      captionBuffer[speaker] = { texto: texto, lastSeen: agora };
      return;
    }

    // Calcula prefixo comum para detectar se é a mesma frase evoluindo
    var prefLen = Math.min(20, Math.max(6, Math.floor(Math.min(buf.texto.length, texto.length) * 0.5)));
    var mesmaPrefixo = texto.toLowerCase().substring(0, prefLen) === buf.texto.toLowerCase().substring(0, prefLen);
    var velhoContemNovo = buf.texto.toLowerCase().indexOf(texto.toLowerCase().substring(0, prefLen)) >= 0;

    if (mesmaPrefixo || velhoContemNovo) {
      // Mesma frase evoluindo — mantém a versão mais longa
      if (texto.length > buf.texto.length) buf.texto = texto;
      buf.lastSeen = agora;
    } else {
      // Nova frase diferente — commita a anterior e inicia nova
      commitarFrase(speaker, buf.texto);
      captionBuffer[speaker] = { texto: texto, lastSeen: agora };
    }
  }

  function verificarLegendas() {
    if (legendasDetectadas) { ocultarAvisoLegenda(); return; }
    // Detecta CC ligado pelo aria-label do botão (muda de "Ativar" para "Desativar")
    var ccAtivo = document.querySelector(
      '[aria-label*="esativar legenda" i],[aria-label*="urn off caption" i],' +
      '[data-tooltip*="esativar legenda" i],[data-tooltip*="urn off caption" i],' +
      'button[aria-pressed="true"][aria-label*="legenda" i],' +
      'button[aria-pressed="true"][aria-label*="caption" i]'
    );
    if (ccAtivo) { ocultarAvisoLegenda(); return; }
    exibirAvisoLegenda();
  }
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
      if (!estado.ativo) return;
      // Só analisa se houver entradas novas desde o último envio — evita análise de silêncio
      if (estado.transcricao.length <= estado.ultimoIndexEnviado) return;
      enviarParaBackend();
    }, CONFIG.intervaloAnalise * 1000);
  }

  function montarTranscricaoParcial() {
    const recentes = estado.transcricao.slice(-60);
    return recentes.map(function (item) { return item.speaker + ': ' + item.text; }).join('\n');
  }

  // Retorna apenas entradas novas desde o último envio (delta para o DB)
  function montarTranscricaoDelta() {
    const novos = estado.transcricao.slice(estado.ultimoIndexEnviado);
    return novos.map(function (item) { return item.speaker + ': ' + item.text; }).join('\n');
  }

  function montarHistorico() {
    if (estado.historicoResumo) return estado.historicoResumo;
    const historico = estado.transcricao.slice(-150);
    return historico.map(function (item) { return item.speaker + ': ' + item.text; }).join('\n');
  }

  function registrarSessao() {
    const url = CONFIG.backendUrl + '/iniciar-sessao';
    if (!chrome.runtime || !chrome.runtime.id) return;
    chrome.runtime.sendMessage(
      { tipo: 'fetchBackend', url: url, payload: { meeting_id: MEETING_ID } },
      function (resp) {
        if (resp && resp.ok) {
          console.log('[SALEIA] Sessão registrada id=' + (resp.data && resp.data.sessao_id));
        }
      }
    );
  }

  function textoOuVazio(valor) {
    if (valor == null) return '';
    return String(valor).trim();
  }

  function copiarTextoParaAreaTransferencia(texto) {
    const valor = textoOuVazio(texto);
    if (!valor) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(valor).catch(function (err) {
        console.warn('[SALEIA] Falha ao copiar texto:', err);
      });
      return;
    }
    var area = document.createElement('textarea');
    area.value = valor;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand('copy');
    } catch (err) {
      console.warn('[SALEIA] Falha ao copiar texto:', err);
    }
    document.body.removeChild(area);
  }

  function renderizarListaHtml(lista) {
    if (!Array.isArray(lista) || lista.length === 0) return '';
    return '<ul class="saleia-recap-lista">' + lista.map(function (item) {
      return '<li>' + escaparHtml(textoOuVazio(item)) + '</li>';
    }).join('') + '</ul>';
  }

  function renderizarRecapitulacaoViva(recap, resumoFallback) {
    const recapEl = document.getElementById('saleia-recapitulacao');
    const recapTexto = document.getElementById('saleia-recapitulacao-texto');
    const recapMapa = document.getElementById('saleia-recap-mapa');
    const recapPergunta = document.getElementById('saleia-recap-pergunta');
    const recapDica = document.getElementById('saleia-recap-dica');
    const recapFaltantes = document.getElementById('saleia-recap-faltantes');
    const recapStatus = document.getElementById('saleia-recap-status');

    const resumo = textoOuVazio(
      (recap && (recap.resumo_curto || recap.resumo_executivo || recap.resumo_vivo)) ||
      resumoFallback ||
      estado.historicoResumo
    );

    if (!recapEl || !recapTexto) return;
    if (estado.recapitulacaoVivaOculta && !recap) {
      recapEl.style.display = 'none';
      return;
    }
    if (!resumo) {
      if (!estado.recapitulacaoVivaOculta) recapEl.style.display = 'none';
      return;
    }

    if (recap) estado.recapitulacaoVivaOculta = false;
    recapEl.style.display = 'block';
    recapEl.classList.toggle('saleia-recap-usada', !!estado.recapitulacaoVivaUsada);
    recapTexto.textContent = resumo;

    if (recapStatus) {
      recapStatus.textContent = estado.recapitulacaoVivaUsada ? 'usada' : (recap && recap.trigger && recap.trigger.trigger_phrase ? 'ativa' : 'nova');
    }

    if (recap && recap.mapa_mental) {
      var mapa = recap.mapa_mental;
      var mapaHtml = [];
      if (mapa.dor_principal) mapaHtml.push('<div class="saleia-recap-linha"><span>Dor principal:</span> ' + escaparHtml(textoOuVazio(mapa.dor_principal)) + '</div>');
      if (mapa.impacto) mapaHtml.push('<div class="saleia-recap-linha"><span>Impacto:</span> ' + escaparHtml(textoOuVazio(mapa.impacto)) + '</div>');
      if (mapa.objetivo) mapaHtml.push('<div class="saleia-recap-linha"><span>Objetivo:</span> ' + escaparHtml(textoOuVazio(mapa.objetivo)) + '</div>');
      if (mapa.objecoes) mapaHtml.push('<div class="saleia-recap-linha"><span>Objeções:</span>' + renderizarListaHtml(Array.isArray(mapa.objecoes) ? mapa.objecoes : [mapa.objecoes]) + '</div>');
      if (mapa.oportunidades) mapaHtml.push('<div class="saleia-recap-linha"><span>Oportunidades:</span>' + renderizarListaHtml(Array.isArray(mapa.oportunidades) ? mapa.oportunidades : [mapa.oportunidades]) + '</div>');
      if (mapa.proximo_passo) mapaHtml.push('<div class="saleia-recap-linha"><span>Próximo passo:</span> ' + escaparHtml(textoOuVazio(mapa.proximo_passo)) + '</div>');
      recapMapa.innerHTML = mapaHtml.length ? mapaHtml.join('') : '';
      recapMapa.style.display = mapaHtml.length ? 'block' : 'none';
    } else {
      recapMapa.innerHTML = '';
      recapMapa.style.display = 'none';
    }

    const pergunta = textoOuVazio((recap && (recap.pergunta_confirmacao || recap.pergunta_sugerida || recap.pergunta)) || '');
    if (recapPergunta) {
      recapPergunta.innerHTML = pergunta ? '<strong>Pergunta de confirmação:</strong> ' + escaparHtml(pergunta) : '';
      recapPergunta.style.display = pergunta ? 'block' : 'none';
    }

    const dica = textoOuVazio((recap && recap.dica_vendedor) || '');
    if (recapDica) {
      recapDica.innerHTML = dica ? '<strong>Dica:</strong> ' + escaparHtml(dica) : '';
      recapDica.style.display = dica ? 'block' : 'none';
    }

    const faltantes = (recap && Array.isArray(recap.perguntas_faltantes)) ? recap.perguntas_faltantes.filter(Boolean) : [];
    if (recapFaltantes) {
      recapFaltantes.innerHTML = faltantes.length ? '<strong>Perguntas faltantes:</strong>' + renderizarListaHtml(faltantes) : '';
      recapFaltantes.style.display = faltantes.length ? 'block' : 'none';
    }
  }

  function solicitarRegeneracaoRecapitulacao() {
    const url = CONFIG.backendUrl + '/recapitulacao-viva';
    if (!chrome.runtime || !chrome.runtime.id) return;
    const botao = document.getElementById('saleia-btn-regenerar-recap');
    if (botao) botao.disabled = true;
    chrome.runtime.sendMessage(
      { tipo: 'fetchBackend', url: url, payload: { meeting_id: MEETING_ID } },
      function (resp) {
        if (botao) botao.disabled = false;
        if (resp && resp.ok) {
          var dados = resp.data || {};
          var recap = dados.recapitulacao_viva || dados.live_recap || dados;
          estado.recapitulacaoVivaOculta = false;
          estado.recapitulacaoVivaUsada = false;
          estado.recapitulacaoViva = recap;
          renderizarRecapitulacaoViva(recap, estado.historicoResumo);
        } else {
          console.warn('[SALEIA] Falha ao regenerar recapitulação:', resp ? resp.error : 'sem resposta');
        }
      }
    );
  }

  function marcarRecapitulacaoComoUsada() {
    estado.recapitulacaoVivaUsada = true;
    const badge = document.getElementById('saleia-recap-status');
    if (badge) badge.textContent = 'usada';
    const recapEl = document.getElementById('saleia-recapitulacao');
    if (recapEl) recapEl.classList.add('saleia-recap-usada');
  }

  function fecharRecapitulacaoViva() {
    estado.recapitulacaoVivaOculta = true;
    const recapEl = document.getElementById('saleia-recapitulacao');
    if (recapEl) recapEl.style.display = 'none';
  }

  function enviarParaBackend() {
    const transcricaoParcial = montarTranscricaoParcial();

    // GUARDA: só envia se houver transcrição real com pelo menos 20 caracteres
    // Evita chamadas ao backend quando não há conversa no Meet
    if (!transcricaoParcial || transcricaoParcial.trim().length < 20) {
      exibirAvisoLegenda();
      return;
    }

    // Captura delta e índice ANTES da chamada async (evita race condition)
    var indexSnapshot = estado.transcricao.length;
    var transcricaoDelta = montarTranscricaoDelta();

    const payload = {
      transcricao_parcial: transcricaoParcial,
      transcricao_nova: transcricaoDelta,  // apenas novas entradas → DB não acumula duplicatas
      historico: montarHistorico(),
      perfil_disc_atual: estado.perfilDiscAtual,
      mapa_financeiro: estado.mapaFinanceiro,
      meeting_id: MEETING_ID,
    };

    const url = CONFIG.backendUrl + '/tempo-real';

    // PROXY VIA BACKGROUND.JS
    // O fetch é delegado ao background.js para contornar o bloqueio do
    // Service Worker do Google Meet (meetsw.js) que intercepta requisições
    // externas feitas diretamente por content scripts.
    if (!chrome.runtime || !chrome.runtime.id) return;
    chrome.runtime.sendMessage(
      { tipo: 'fetchBackend', url: url, payload: payload },
      function (resp) {
        if (chrome.runtime.lastError) { estado.backendOnline = false; return; }
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
          // Avança índice para não reenviar as mesmas entradas ao DB
          estado.ultimoIndexEnviado = indexSnapshot;
        } else {
          console.warn('[SALEIA] Backend offline:', resp ? resp.error : 'sem resposta');
          estado.backendOnline = false;
          exibirErroBackend();
        }
      }
    );
  }

  function atualizarSidebarComResposta(dados) {
    if (dados && (dados.resumo_vivo || dados.recapitulacao)) {
      estado.historicoResumo = dados.resumo_vivo || dados.recapitulacao || estado.historicoResumo;
    }

    // 🧠 RECAPITULAÇÃO DO CLIENTE
    const recapEl = document.getElementById('saleia-recapitulacao');
    const recapTexto = document.getElementById('saleia-recapitulacao-texto');
    const resumoAtual = dados.resumo_vivo || dados.recapitulacao;
    const recapViva = dados.recapitulacao_viva || dados.live_recap || dados.recapitulacaoViva || null;
    if (recapViva) {
      estado.recapitulacaoViva = recapViva;
      estado.recapitulacaoVivaOculta = false;
      estado.recapitulacaoVivaUsada = false;
      renderizarRecapitulacaoViva(recapViva, resumoAtual);
    } else if (resumoAtual && recapTexto) {
      renderizarRecapitulacaoViva(null, resumoAtual);
    } else if (recapEl) {
      recapEl.style.display = 'none';
    }

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

    // 🏷️ ESTÁGIO + KARE
    renderizarStageKare(dados);

    // 🎯 PRÓXIMA MELHOR AÇÃO
    renderizarNBQ(dados);

    // 📊 MATURITY SCORE
    renderizarMaturity(dados);

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

    // 📊 SCORE DE COMPRA
    const scoreEl = document.getElementById('saleia-score');
    if (dados.score_compra && dados.score_compra.valor !== undefined) {
      const val = Math.min(98, Math.max(5, Number(dados.score_compra.valor)));
      const cor = val >= 70 ? '#00d4aa' : val >= 45 ? '#ffaa00' : '#ff4444';
      document.getElementById('saleia-score-valor').textContent = val + '/100';
      document.getElementById('saleia-score-valor').style.color = cor;
      document.getElementById('saleia-score-fill').style.width = val + '%';
      document.getElementById('saleia-score-fill').style.background = cor;
      document.getElementById('saleia-score-texto').textContent = dados.score_compra.justificativa || '';
      scoreEl.style.display = 'block';
    } else {
      scoreEl.style.display = 'none';
    }

    animarAtualizacao();
  }

  var _NBA_CATEGORY_LABEL = {
    descoberta_dor:      'Descoberta',
    problema:            'Identificar Dor',
    amplificacao_dor:    'Amplificar Dor',
    implicacao:          'Implicação',
    necessidade_solucao: 'Necessidade',
    impacto_financeiro:  'Impacto $',
    urgencia:            'Urgência',
    autoridade:          'Autoridade',
    budget:              'Budget',
    objecao:             'Objeção',
    insight_desafiador:  'Insight',
    controle_consultivo: 'Controle',
    compromisso:         'Próx. Passo',
    situacao:            'Situação',
  };

  var _NBA_TYPE_LABEL = {
    question:  '❓',
    insight:   '💡',
    warning:   '⚠️',
    next_step: '▶️',
  };

  var _NBA_CONF_COLOR = { high: '#EF4444', medium: '#F59E0B', low: '#888' };

  var _STAGE_LABEL = {
    abertura:            'Abertura',
    situacao:            'Situação',
    problema:            'Problema',
    implicacao:          'Implicação',
    necessidade_solucao: 'Necessidade',
    qualificacao:        'Qualificação',
    proposta:            'Proposta',
    compromisso:         'Compromisso',
  };

  var _KARE_LABEL = { keep: 'Keep', attain: 'Attain', recapture: 'Recapture', expand: 'Expand' };
  var _KARE_COLOR = { keep: '#22C55E', attain: '#C9A227', recapture: '#F97316', expand: '#3B82F6' };

  function renderizarStageKare(dados) {
    var el = document.getElementById('saleia-stage-kare');
    if (!el) return;
    var stage = dados.conversation_stage;
    var kare = dados.kare_type;
    if (!stage && !kare) { el.style.display = 'none'; return; }
    var html = '';
    if (stage) html += '<span class="saleia-stage-badge">' + escaparHtml(_STAGE_LABEL[stage] || stage) + '</span>';
    if (kare) {
      var kColor = _KARE_COLOR[kare] || '#888';
      html += '<span class="saleia-kare-badge" style="color:' + kColor + ';border-color:' + kColor + '44">' + escaparHtml(_KARE_LABEL[kare] || kare) + '</span>';
    }
    el.innerHTML = html;
    el.style.display = 'flex';
  }

  function renderizarNBQ(dados) {
    // Prefere next_best_action (novo), cai em next_best_question (legacy)
    var nba = dados.next_best_action;
    var nbq = dados.next_best_question;
    var perguntaEl = document.getElementById('saleia-nbq-pergunta');
    var badgesEl   = document.getElementById('saleia-nbq-badges');
    var objetivoEl = document.getElementById('saleia-nbq-objetivo');
    var motivoEl   = document.getElementById('saleia-nbq-motivo');
    var riscoEl    = document.getElementById('saleia-nbq-risco');
    var followupEl = document.getElementById('saleia-nbq-followup');
    var impactoEl  = document.getElementById('saleia-nbq-impacto');
    var copiarBtn  = document.getElementById('saleia-nbq-copiar');
    if (!perguntaEl) return;

    // --- Extrair texto principal ---
    var textoMsg = (nba && nba.message) || (nbq && nbq.question) ||
                   dados.proxima_pergunta || dados.proxima_fala || dados.texto_falavel || null;
    if (!textoMsg) {
      perguntaEl.textContent = 'Aguardando análise...';
      badgesEl.innerHTML = '';
      objetivoEl.textContent = '';
      motivoEl.textContent = '';
      if (riscoEl)    { riscoEl.textContent = ''; riscoEl.style.display = 'none'; }
      if (followupEl) { followupEl.textContent = ''; followupEl.style.display = 'none'; }
      impactoEl.textContent = '';
      if (copiarBtn) copiarBtn.style.display = 'none';
      return;
    }

    // --- Badges: tipo + categoria + confiança ---
    var typeIcon  = (nba && _NBA_TYPE_LABEL[nba.type]) || '❓';
    var catKey    = (nba && nba.category) || (nbq && nbq.category) || '';
    var catLabel  = _NBA_CATEGORY_LABEL[catKey] || catKey || '';
    var conf      = nba && nba.confidence != null ? parseFloat(nba.confidence) : null;
    var confLevel = conf != null ? (conf >= 0.8 ? 'high' : conf >= 0.6 ? 'medium' : 'low') : null;
    var confColor = confLevel ? _NBA_CONF_COLOR[confLevel] : '#888';

    badgesEl.innerHTML =
      '<span class="saleia-nbq-type">' + typeIcon + '</span>' +
      (catLabel ? '<span class="saleia-nbq-badge">' + escaparHtml(catLabel) + '</span>' : '') +
      (confLevel ? '<span class="saleia-nbq-urgency" style="background:' + confColor + '22;color:' + confColor + '">' + Math.round((conf || 0) * 100) + '%</span>' : '');

    // --- Título / Objetivo ---
    var titulo = (nba && nba.title) || '';
    var objetivo = (nba && nba.objective) || (nbq && nbq.objective) || '';
    objetivoEl.textContent = titulo ? titulo + (objetivo ? ' — ' + objetivo : '') : (objetivo ? objetivo : '');

    // --- Mensagem principal ---
    perguntaEl.innerHTML = '<span class="saleia-verde">"' + escaparHtml(textoMsg) + '"</span>';

    // --- Motivo (por que agora) ---
    var motivo = (nba && nba.reason) || (nbq && nbq.reason) || '';
    motivoEl.textContent = motivo ? '↳ ' + motivo : '';

    // --- Risco se ignorado ---
    if (riscoEl) {
      var risco = nba && nba.risk_if_ignored;
      if (risco) {
        riscoEl.textContent = '⚠ ' + risco;
        riscoEl.style.display = 'block';
      } else {
        riscoEl.textContent = '';
        riscoEl.style.display = 'none';
      }
    }

    // --- Follow-up ---
    if (followupEl) {
      var fu = (nba && nba.follow_up) || (nbq && nbq.follow_up_question) || null;
      if (fu) {
        followupEl.textContent = '↪ ' + fu;
        followupEl.style.display = 'block';
      } else {
        followupEl.textContent = '';
        followupEl.style.display = 'none';
      }
    }

    // --- Efeito esperado / score ---
    var efeito = (nba && nba.expected_effect) || (nbq && nbq.expected_score_impact ? 'Score: ' + nbq.expected_score_impact : '');
    impactoEl.textContent = efeito || '';

    // --- Botão copiar ---
    if (copiarBtn) {
      copiarBtn.style.display = 'block';
      copiarBtn.onclick = function () {
        navigator.clipboard.writeText(textoMsg).catch(function () {});
      };
    }
  }

  var _MATURITY_LABELS = {
    dor_identificada:          'Dor',
    impacto_quantificado:      'Impacto',
    urgencia_identificada:     'Urgência',
    budget_identificado:       'Budget',
    decisores_mapeados:        'Decisor',
    valor_verbalizado_cliente: 'Valor',
    proximo_passo_claro:       'Próx.Passo',
  };
  var _MATURITY_MAX = {
    dor_identificada: 20, impacto_quantificado: 20, urgencia_identificada: 15,
    budget_identificado: 15, decisores_mapeados: 10, valor_verbalizado_cliente: 10, proximo_passo_claro: 10,
  };

  function renderizarMaturity(dados) {
    var el = document.getElementById('saleia-maturity');
    var totalEl = document.getElementById('saleia-maturity-total');
    var gridEl  = document.getElementById('saleia-maturity-grid');
    if (!el || !gridEl) return;
    var ms = dados.maturity_score;
    if (!ms || typeof ms.total === 'undefined') { el.style.display = 'none'; return; }
    el.style.display = 'block';
    var total = ms.total || 0;
    var cor = total >= 70 ? '#22C55E' : total >= 40 ? '#F59E0B' : '#EF4444';
    totalEl.innerHTML = 'Score: <strong style="color:' + cor + '">' + total + '/100</strong>';
    var html = '';
    Object.keys(_MATURITY_LABELS).forEach(function (k) {
      var val = ms[k] || 0;
      var max = _MATURITY_MAX[k] || 10;
      var pct = Math.round((val / max) * 100);
      var chipCor = val >= max ? '#22C55E' : val > 0 ? '#F59E0B' : '#444';
      html += '<div class="saleia-maturity-chip" style="border-color:' + chipCor + ';color:' + chipCor + '" title="' + _MATURITY_LABELS[k] + ': ' + val + '/' + max + '">' +
              escaparHtml(_MATURITY_LABELS[k]) + (val > 0 ? ' ✓' : '') + '</div>';
    });
    gridEl.innerHTML = html;
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

  // ── Captura foto do cliente via elemento <video> do Meet ──
  function capturarFotoCliente() {
    var btn = document.getElementById('saleia-btn-foto');
    if (btn) { btn.textContent = '⏳'; btn.disabled = true; }

    try {
      // Coleta todos os <video> visíveis com conteúdo
      var videos = Array.from(document.querySelectorAll('video')).filter(function (v) {
        return v.videoWidth > 0 && v.videoHeight > 0 && !v.paused && v.readyState >= 2;
      });

      if (videos.length === 0) {
        _fotoBtnReset(btn, '📸');
        _fotoToast('Nenhum vídeo encontrado. Aguarde o cliente entrar na chamada.', true);
        return;
      }

      // Ordena por área: maior = participante principal (cliente)
      videos.sort(function (a, b) {
        return (b.videoWidth * b.videoHeight) - (a.videoWidth * a.videoHeight);
      });

      // Se houver mais de 1, tenta excluir o self-view (vídeo menor ou em container de self)
      var alvo = videos[0];
      if (videos.length > 1) {
        var remoto = videos.find(function (v) {
          var el = v;
          while (el && el !== document.body) {
            var cls = (el.getAttribute('data-self-name') || '') +
                      (el.className || '') +
                      (el.getAttribute('jsname') || '');
            if (/self|local|you|preview/i.test(cls)) return false;
            el = el.parentElement;
          }
          return true;
        });
        if (remoto) alvo = remoto;
      }

      // Redimensiona para max 800px (evita mensagem gigante)
      var maxW   = 800;
      var scale  = Math.min(1, maxW / alvo.videoWidth);
      var canvas = document.createElement('canvas');
      canvas.width  = Math.round(alvo.videoWidth  * scale);
      canvas.height = Math.round(alvo.videoHeight * scale);
      canvas.getContext('2d').drawImage(alvo, 0, 0, canvas.width, canvas.height);

      var dataURL;
      try {
        dataURL = canvas.toDataURL('image/jpeg', 0.82);
      } catch (e) {
        // Canvas taint — abre o VS sem foto
        _fotoBtnReset(btn, '📸');
        _fotoToast('Captura bloqueada. Use "Fazer Upload" no Visual Scenario.', true);
        if (chrome.runtime && chrome.runtime.id) {
          chrome.runtime.sendMessage({ tipo: 'abrirCenario', url: CONFIG.backendUrl + '/visual-scenario?meeting=' + MEETING_ID });
        }
        return;
      }

      // Persiste no storage da extensão (sem limite cross-origin, sobrevive ao SW sleep)
      chrome.storage.local.set({ saleia_foto_pendente: { foto: dataURL, meetingId: MEETING_ID } }, function () {
        if (chrome.runtime && chrome.runtime.id) {
          chrome.runtime.sendMessage({
            tipo: 'abrirCenarioComFoto',
            url: CONFIG.backendUrl + '/visual-scenario?meeting=' + MEETING_ID,
            meetingId: MEETING_ID,
          });
        }
      });

      _fotoBtnReset(btn, '✅');
      _fotoToast('Foto capturada! Abrindo Visual Scenario...', false);
      setTimeout(function () { _fotoBtnReset(btn, '📸'); }, 3000);

    } catch (e) {
      _fotoBtnReset(btn, '📸');
      _fotoToast('Erro: ' + e.message, true);
    }
  }

  function _fotoBtnReset(btn, icon) {
    if (!btn) return;
    btn.textContent = icon;
    btn.disabled = false;
  }

  function _fotoToast(msg, erro) {
    var t = document.getElementById('saleia-foto-toast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'saleia-foto-toast';
      t.style.cssText = [
        'position:fixed', 'bottom:70px', 'right:16px', 'z-index:999999',
        'background:#252338', 'color:#F8FAFC', 'border-radius:8px',
        'padding:10px 16px', 'font-size:12px', 'max-width:260px',
        'box-shadow:0 4px 16px rgba(0,0,0,.5)', 'transition:opacity .3s',
        'border:1px solid ' + (erro ? 'rgba(239,68,68,.4)' : 'rgba(20,184,166,.4)'),
      ].join(';');
      document.body.appendChild(t);
    }
    t.style.color = erro ? '#FCA5A5' : '#2DD4BF';
    t.textContent = msg;
    t.style.opacity = '1';
    clearTimeout(t._hide);
    t._hide = setTimeout(function () { t.style.opacity = '0'; }, 4000);
  }

  function _fotoAbrirVS() {
    if (!chrome.runtime || !chrome.runtime.id) return;
    chrome.runtime.sendMessage({
      tipo: 'abrirCenario',
      url: CONFIG.backendUrl + '/visual-scenario?meeting=' + MEETING_ID,
    });
  }

})();
