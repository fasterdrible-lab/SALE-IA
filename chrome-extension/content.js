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
    // A11 (V.1.4.19): 60s → 20s; o backend pode ajustar via intervalo_analise_s.
    intervaloAnalise: 20,
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
    sidebarDestacada: false,
    timerContador: null,
    timerEnvio: null,
    backendOnline: true,
    ultimoIndexEnviado: 0,  // tracks last committed entry sent to DB
    envioEmAndamento: 0,    // timestamp do /tempo-real em voo (0 = livre) — Tarefa A1
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
        // O vendedor é sempre o dono da extensão; vale entre reuniões.
        estado.participantes.vendedor = saved.vendedor || 'Vendedor';
        // A10 (V.1.4.20): clientes valem só na reunião em que foram
        // cadastrados. Antes, um "João" salvo em junho rotulava falas de
        // todas as reuniões seguintes.
        if (saved.meetingId === MEETING_ID) {
          if (Array.isArray(saved.clientes) && saved.clientes.length) {
            estado.participantes.clientes = saved.clientes;
          } else if (saved.cliente) {
            estado.participantes.clientes = [saved.cliente];
          }
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
        // Áudio silencioso em WebM/opus gera ~2-4KB. O corte em 10KB jogava
        // fora fala curta (auditoria T01, P19); o servidor já descarta
        // silêncio (VAD do faster-whisper) e alucinação de silêncio.
        if (e.data && e.data.size > 4096) enviarChunkWhisper(e.data);
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
    // Rejeita texto com < 3 palavras únicas (ruído de fundo / eco) — mesmo
    // filtro usado tanto pro áudio do microfone quanto pro áudio da aba.
    function passaFiltroRuidoAudio(texto) {
      var palavras = texto.toLowerCase().replace(/[^a-záéíóúãõâêîôûàçü\s]/g, '').split(/\s+/).filter(Boolean);
      var unicas = new Set(palavras);
      return !(unicas.size < 3 && palavras.length < 6);
    }

    function enviarChunkWhisper(blob) {
      if (!estado.ativo) return; // API desligada — nenhuma chamada ao backend
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
            if (!passaFiltroRuidoAudio(texto)) {
              console.log('[SALEIA] chunk descartado (ruído/repetição):', texto);
              return;
            }
            commitarFrase('Vendedor', texto, 'audio');
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

    // Fase 3 do PROMPT MESTRE ("Meetily") — captura o áudio da ABA
    // (participantes), via background.js + offscreen.js (chrome.tabCapture).
    // Achado real (19/09/2026): chrome.tabCapture só libera acesso à aba
    // quando a extensão é "invocada" por um gesto que o Chrome reconhece
    // (ícone da barra de ferramentas) — um clique num botão injetado pela
    // própria página (aqui) nunca satisfaz esse requisito e sempre falha
    // com "Extension has not been invoked for the current page". Por
    // isso INICIAR a captura da aba agora só acontece pelo popup.html
    // (popup.js); a sidebar continua controlando só o microfone e, ao
    // parar, também encerra a captura da aba se ela estiver ativa.
    function pararCapturaAba() {
      if (!chrome.runtime || !chrome.runtime.id) return;
      chrome.runtime.sendMessage({ tipo: 'pararCaptura' }, function () {
        if (chrome.runtime.lastError) { /* aba já pode ter sido fechada — ignora */ }
      });
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
        pararCapturaAba(); // Fase 3: encerra também a captura do áudio da aba
        btn.textContent = '🎤 Capturar áudio (Whisper)';
        btn.style.background = '#1a1a2e'; btn.style.borderColor = '#00d4aa'; btn.style.color = '#00d4aa';
        setAudioStatus('', '');
      }
    });

    iniciarControlesGravacao();

    chrome.runtime.onMessage.addListener(function (msg) {
      if (msg.tipo === 'toggle') { estado.ativo = msg.valor; atualizarStatusSidebar(); }
      if (msg.tipo === 'backendUrl') { CONFIG.backendUrl = msg.valor; }
      // Fase 3 do PROMPT MESTRE — texto transcrito do áudio da ABA
      // (participantes), vindo de background.js/offscreen.js. Rotulado
      // "Cliente" (normalizado por rotuloParticipante, mesmo padrão das
      // legendas) pra diferenciar do microfone do vendedor.
      if (msg.tipo === 'transcricaoAudio') {
        var textoAba = (msg.texto || '').trim();
        if (textoAba && passaFiltroRuidoAudio(textoAba)) {
          commitarFrase(msg.fonte === 'aba' ? 'Cliente' : 'Vendedor', textoAba, 'audio');
          enviarParaBackend();
        }
      }
      if (msg.tipo === 'backendStatus') {
        // Enquanto a API estiver desligada, o status já mostra "API desligada" —
        // não sobrescrever com o resultado do heartbeat.
        if (!estado.ativo) return;
        const dot = document.querySelector('#saleia-status .saleia-dot');
        const txt = document.getElementById('saleia-status');
        if (dot && txt) {
          dot.style.background = msg.online ? '#00d4aa' : '#ff4444';
          txt.childNodes[1].textContent = msg.online ? ' Conectado' : ' Desconectado';
        }
      }
    });
  }

  // ── T02: gravação contínua — trilha do microfone + indicador ──────────
  // Começa só a pedido do background (popup, depois da confirmação de que os
  // participantes foram avisados). A permissão de microfone usada aqui é a
  // do próprio Meet. Gravador e fila: gravacao_rules.js.
  var gravadorMic = null;
  var streamMic = null;
  var configGravacaoMic = null;
  var estadoGravacao = null;
  var timerGravacao = null;

  function enviarGravacao(tipo, corpo) {
    if (!chrome.runtime || !chrome.runtime.id) return Promise.resolve();
    return chrome.runtime.sendMessage({ tipo: tipo, corpo: corpo }).catch(function (e) {
      console.warn('[SALEIA] ' + tipo + ' não chegou ao background:', e && e.message);
    });
  }

  function iniciarGravacaoMicrofone(cfg) {
    if (gravadorMic && gravadorMic.gravando()) return Promise.resolve({ ok: true });
    configGravacaoMic = cfg;
    return navigator.mediaDevices.getUserMedia({ audio: true, video: false }).then(function (stream) {
      streamMic = stream;
      var mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
      gravadorMic = SaleiaGravacao.criarGravadorContinuo({
        stream: stream, trackId: 'microfone', meetingId: MEETING_ID, mimeType: mime,
        blocoMs: (cfg.bloco_s || 5) * 1000, rotacaoMs: (cfg.rotacao_s || 600) * 1000,
        aoIniciar: function (info) { return enviarGravacao('gravacaoIniciar', info); },
        aoBloco: function (bloco) {
          return SaleiaGravacao.prepararConteudo(bloco.blob).then(function (c) {
            var corpo = Object.assign({}, bloco, c);
            delete corpo.blob;
            return enviarGravacao('gravacaoBloco', corpo);
          });
        },
        aoEncerrar: function (fim) { return enviarGravacao('gravacaoEncerrar', fim); },
        aoErro: function (e) { console.error('[SALEIA] gravação do microfone:', e); },
        // Microfone desconectado/liberado: a gravação já foi encerrada pelo gravador.
        aoFimDoAudio: function () {
          gravadorMic = null;
          streamMic = null;
          enviarGravacao('gravacaoTrilhaAcabou', { track_id: 'microfone' });
        },
      });
      gravadorMic.iniciar();
      return { ok: true };
    }).catch(function (e) {
      return { ok: false, error: (e && (e.name || e.message)) || 'erro' };
    });
  }

  function controlarGravacaoMicrofone(acao) {
    if (acao === 'retomar' && !gravadorMic && configGravacaoMic) return iniciarGravacaoMicrofone(configGravacaoMic);
    if (!gravadorMic) return Promise.resolve({ ok: true });
    if (acao === 'pausar') gravadorMic.pausar();
    if (acao === 'retomar') gravadorMic.retomar();
    if (acao === 'parar') {
      var g = gravadorMic;
      gravadorMic = null;
      g.parar();
      if (streamMic) { streamMic.getTracks().forEach(function (t) { t.stop(); }); streamMic = null; }
    }
    return Promise.resolve({ ok: true });
  }

  var AVISOS_GRAVACAO = {
    login: 'Login expirado: entre de novo na extensão. O áudio fica guardado e é enviado depois.',
    sem_conexao: 'Sem conexão: o áudio fica guardado e é enviado quando a conexão voltar.',
    desligada: 'Gravação desativada no servidor.',
    fila_cheia: 'Muito áudio sem enviar: parte da gravação não está sendo guardada.',
  };

  function formatarDuracao(ms) {
    var s = Math.max(0, Math.floor(ms / 1000));
    var p = function (n) { return (n < 10 ? '0' : '') + n; };
    return p(Math.floor(s / 3600)) + ':' + p(Math.floor(s / 60) % 60) + ':' + p(s % 60);
  }

  function renderizarGravacao(est) {
    estadoGravacao = est;
    var caixa = document.getElementById('saleia-gravacao');
    if (!caixa) return;
    if (!est || !est.ativa) {
      caixa.style.display = 'none';
      if (timerGravacao) { clearInterval(timerGravacao); timerGravacao = null; }
      return;
    }
    caixa.style.display = 'block';
    document.getElementById('saleia-gravacao-texto').textContent = est.pausada ? '⏸ Gravação pausada' : '● Gravando a reunião';
    document.getElementById('saleia-gravacao-pausar').textContent = est.pausada ? 'Retomar' : 'Pausar';
    var avisos = [];
    if (est.ultimo_erro && AVISOS_GRAVACAO[est.ultimo_erro]) avisos.push(AVISOS_GRAVACAO[est.ultimo_erro]);
    if (est.microfone && est.microfone !== 'gravando') avisos.push('Seu microfone não está sendo gravado (' + est.microfone.replace(/^erro: /, '') + ').');
    else if (!est.pausada && !gravadorMic) avisos.push('Seu microfone parou (página recarregada?). Clique em Pausar e depois em Retomar.');
    document.getElementById('saleia-gravacao-aviso').textContent = avisos.join(' ');
    var atualizarTempo = function () {
      var el = document.getElementById('saleia-gravacao-tempo');
      if (el && estadoGravacao && estadoGravacao.inicio_ms) el.textContent = formatarDuracao(Date.now() - estadoGravacao.inicio_ms);
    };
    atualizarTempo();
    if (!timerGravacao) timerGravacao = setInterval(atualizarTempo, 1000);
  }

  function iniciarControlesGravacao() {
    var btnPausar = document.getElementById('saleia-gravacao-pausar');
    var btnEncerrar = document.getElementById('saleia-gravacao-encerrar');
    if (btnPausar) btnPausar.addEventListener('click', function () {
      var acao = estadoGravacao && estadoGravacao.pausada ? 'retomar' : 'pausar';
      chrome.runtime.sendMessage({ tipo: 'controleGravacao', acao: acao });
    });
    if (btnEncerrar) btnEncerrar.addEventListener('click', function () {
      chrome.runtime.sendMessage({ tipo: 'controleGravacao', acao: 'parar' });
    });
    chrome.runtime.onMessage.addListener(function (msg, _sender, sendResponse) {
      if (msg.tipo === 'gravarMicrofone') {
        iniciarGravacaoMicrofone(msg).then(sendResponse);
        return true;
      }
      if (msg.tipo === 'controleGravacaoMic') {
        controlarGravacaoMicrofone(msg.acao).then(sendResponse);
        return true;
      }
      if (msg.tipo === 'statusGravacao') renderizarGravacao(msg.estado);
    });
    // Página recarregada no meio da gravação: mostra o estado (e o aviso do microfone).
    chrome.runtime.sendMessage({ tipo: 'statusGravacao' }, function (est) {
      if (chrome.runtime.lastError) return;
      if (est && est.ativa && est.meeting_id === MEETING_ID) renderizarGravacao(est);
    });

    // Página fechando/recarregando: o gravador do microfone morre junto e não
    // consegue encerrar sozinho — o background encerra pelo que tem na fila.
    window.addEventListener('pagehide', function () {
      if (!gravadorMic) return;
      try { chrome.runtime.sendMessage({ tipo: 'gravacaoMicrofoneSaiu' }); } catch (e) { /* extensão recarregada */ }
    });

    // Saiu da reunião ou a chamada acabou (tela "Participar novamente"):
    // encerra as 2 trilhas. Em 12/10/2026 a gravação seguiu aberta depois do fim.
    var fimJaAvisado = false;
    setInterval(function () {
      if (!estadoGravacao || !estadoGravacao.ativa) { fimJaAvisado = false; return; }  // reentrou e gravou de novo
      if (fimJaAvisado || estadoGravacao.meeting_id !== MEETING_ID) return;
      var botoes = Array.prototype.map.call(document.querySelectorAll('button'), function (b) { return b.textContent; });
      if (!SaleiaGravacao.reuniaoAcabou(window.location.pathname, MEETING_ID, botoes)) return;
      fimJaAvisado = true;
      console.log('[SALEIA] reunião encerrada: parando a gravação.');
      chrome.runtime.sendMessage({ tipo: 'controleGravacao', acao: 'parar' });
    }, 5000);
  }

  // Permite arrastar a sidebar pela barra de título (#saleia-header) para
  // qualquer posição da tela. Posição é salva em chrome.storage.local e
  // restaurada nas próximas reuniões.
  function ativarArrastarSidebar(sidebar) {
    var header = document.getElementById('saleia-header');
    if (!header) return;
    var arrastando = false;
    var offsetX = 0;
    var offsetY = 0;

    function aplicarPosicao(left, top) {
      var maxLeft = Math.max(window.innerWidth - sidebar.offsetWidth, 0);
      var maxTop = Math.max(window.innerHeight - 40, 0);
      left = Math.min(Math.max(left, 0), maxLeft);
      top = Math.min(Math.max(top, 0), maxTop);
      sidebar.style.left = left + 'px';
      sidebar.style.right = 'auto';
      sidebar.style.top = top + 'px';
    }

    chrome.storage.local.get(['saleiaSidebarPos'], function (result) {
      var pos = result.saleiaSidebarPos;
      if (pos && typeof pos.left === 'number' && typeof pos.top === 'number') {
        aplicarPosicao(pos.left, pos.top);
      }
    });

    header.addEventListener('mousedown', function (e) {
      if (estado.sidebarDestacada) return;
      if (e.target && e.target.closest('button')) return;
      arrastando = true;
      var rect = sidebar.getBoundingClientRect();
      offsetX = e.clientX - rect.left;
      offsetY = e.clientY - rect.top;
      header.classList.add('saleia-arrastando');
      e.preventDefault();
    });

    document.addEventListener('mousemove', function (e) {
      if (!arrastando) return;
      aplicarPosicao(e.clientX - offsetX, e.clientY - offsetY);
    });

    document.addEventListener('mouseup', function () {
      if (!arrastando) return;
      arrastando = false;
      header.classList.remove('saleia-arrastando');
      var rect = sidebar.getBoundingClientRect();
      chrome.storage.local.set({ saleiaSidebarPos: { left: rect.left, top: rect.top } });
    });
  }

  // Destaca a sidebar numa janela flutuante real do SO (Document Picture-in-
  // Picture) — pode ser movida pra fora da janela do Meet, inclusive pra
  // outro monitor. Requer Chrome 116+; em navegadores sem suporte, avisa.
  var _pipWindow = null;
  function ativarPictureInPicture(sidebar) {
    var pipBtn = document.getElementById('saleia-pip-btn');
    if (!pipBtn) return;

    pipBtn.addEventListener('click', async function () {
      if (_pipWindow) {
        _pipWindow.close();
        return;
      }
      if (!('documentPictureInPicture' in window)) {
        alert('Seu Chrome não suporta janela flutuante (precisa do Chrome 116 ou mais recente).');
        return;
      }
      var larguraOriginal = sidebar.style.width;
      try {
        _pipWindow = await window.documentPictureInPicture.requestWindow({
          width: 300,
          height: 560,
        });
      } catch (e) {
        _pipWindow = null; // usuário cancelou o prompt, ou navegador bloqueou
        return;
      }

      // A janela PiP nasce com um document em branco, sem nenhum CSS.
      // Um <link href="chrome-extension://..."> inserido nesse document
      // não carregou (o document da PiP não fica reconhecido como
      // meet.google.com pra fins de web_accessible_resources) — busca o
      // texto do sidebar.css via fetch (executado no contexto do content
      // script, que sempre pode ler os próprios arquivos da extensão) e
      // injeta como <style> inline, que não depende de nenhuma política
      // de carregamento de recurso externo.
      _pipWindow.document.documentElement.style.height = '100%';
      _pipWindow.document.body.style.height = '100%';
      _pipWindow.document.body.style.margin = '0';
      _pipWindow.document.body.style.background = '#000';
      _pipWindow.document.body.style.overflow = 'hidden';
      fetch(chrome.runtime.getURL('sidebar.css'))
        .then(function (resposta) { return resposta.text(); })
        .then(function (css) {
          var style = document.createElement('style');
          style.textContent = css;
          _pipWindow.document.head.appendChild(style);
        })
        .catch(function () { /* pior caso: janela PiP fica sem estilo, mas funcional */ });

      // Reencaixa a sidebar pra ocupar 100% da janela flutuante
      estado.sidebarDestacada = true;
      sidebar.style.position = 'static';
      sidebar.style.width = '100%';
      sidebar.style.height = '100%';
      sidebar.style.maxHeight = 'none';
      sidebar.style.borderRadius = '0';
      pipBtn.textContent = '↩';
      pipBtn.title = 'Voltar sidebar pro Meet';
      _pipWindow.document.body.appendChild(sidebar);

      // Quando a janela flutuante é fechada (pelo usuário ou pelo botão ↩),
      // a sidebar volta pro Meet no lugar/tamanho de sempre.
      _pipWindow.addEventListener('pagehide', function () {
        estado.sidebarDestacada = false;
        sidebar.style.position = 'fixed';
        sidebar.style.width = larguraOriginal || (estado.sidebarMinimizada ? '44px' : '280px');
        sidebar.style.height = '';
        sidebar.style.maxHeight = 'calc(100vh - 80px)';
        sidebar.style.borderRadius = '8px 0 0 8px';
        pipBtn.textContent = '🗗';
        pipBtn.title = 'Destacar em janela flutuante';
        document.body.appendChild(sidebar);
        _pipWindow = null;
      }, { once: true });
    });
  }

  function criarSidebar() {
    const sidebar = document.createElement('div');
    sidebar.id = 'saleia-sidebar';
    sidebar.innerHTML = `
      <div id="saleia-header">
        <button id="saleia-toggle-btn" title="Minimizar/Expandir">≡</button>
        <span>🤖 SALEIA AO VIVO</span>
        <button id="saleia-pip-btn" title="Destacar em janela flutuante">🗗</button>
      </div>
      <div id="saleia-body">
        <div id="saleia-status"><span class="saleia-dot"></span> Conectando...</div>
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

        <div id="saleia-nbq" class="saleia-secao saleia-nbq-box">
          <div class="saleia-secao-titulo">🎯 PRÓXIMA AÇÃO / PERGUNTA</div>
          <div id="saleia-nbq-badges"></div>
          <div id="saleia-nbq-objetivo" class="saleia-nbq-objetivo"></div>
          <div id="saleia-nbq-pergunta" class="saleia-nbq-pergunta">Aguardando análise...</div>
          <div id="saleia-nbq-motivo" class="saleia-nbq-motivo"></div>
          <div id="saleia-nbq-evite" class="saleia-nbq-evite" style="display:none"></div>
          <div id="saleia-nbq-risco" class="saleia-nbq-risco" style="display:none"></div>
          <div id="saleia-nbq-followup" class="saleia-nbq-followup" style="display:none"></div>
          <div id="saleia-nbq-impacto" class="saleia-nbq-impacto"></div>
          <button id="saleia-nbq-copiar" class="saleia-discreto-btn" style="margin-top:6px;display:none">📋 Copiar</button>
        </div>

        <div id="saleia-legenda-aviso" class="saleia-secao saleia-aviso" style="display:none">
          ⚠️ Ative as legendas no Meet:<br>
          Clique em "CC" na barra inferior do Meet
        </div>
        <div id="saleia-login-aviso" class="saleia-secao saleia-aviso" style="display:none"></div>
        <div id="saleia-debug-count" style="font-size:.75rem;color:#666;margin-top:4px"></div>
        <button id="saleia-btn-audio-capture"
          style="margin:6px 0 2px;width:100%;padding:7px;background:#1a1a2e;border:1px solid #00d4aa;
                 color:#00d4aa;border-radius:6px;font-size:.8rem;font-weight:600;cursor:pointer">
          🎤 Capturar áudio (Whisper)
        </button>
        <div id="saleia-audio-status" style="font-size:.73rem;min-height:1.1em;margin-bottom:2px;padding:0 2px"></div>
        <div id="saleia-gravacao" role="status" aria-live="polite"
          style="display:none;margin:6px 0;padding:7px 8px;border:1px solid #ff4444;border-radius:6px;background:#2d0a0a">
          <div style="font-size:.8rem;font-weight:600;color:#ff6b6b">
            <span id="saleia-gravacao-texto">● Gravando a reunião</span>
            <span id="saleia-gravacao-tempo" style="float:right;font-variant-numeric:tabular-nums">00:00:00</span>
          </div>
          <div id="saleia-gravacao-aviso" style="font-size:.72rem;color:#ffb347;margin-top:3px"></div>
          <div style="display:flex;gap:6px;margin-top:6px">
            <button id="saleia-gravacao-pausar" type="button"
              style="flex:1;padding:5px;background:#1a1a2e;border:1px solid #888;color:#ddd;border-radius:5px;font-size:.75rem;cursor:pointer">Pausar</button>
            <button id="saleia-gravacao-encerrar" type="button"
              style="flex:1;padding:5px;background:#1a1a2e;border:1px solid #ff4444;color:#ff6b6b;border-radius:5px;font-size:.75rem;cursor:pointer">Encerrar gravação</button>
          </div>
        </div>
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
    ativarArrastarSidebar(sidebar);
    ativarPictureInPicture(sidebar);
    document.getElementById('saleia-toggle-btn').addEventListener('click', function () {
      estado.sidebarMinimizada = !estado.sidebarMinimizada;
      const body = document.getElementById('saleia-body');
      body.style.display = estado.sidebarMinimizada ? 'none' : 'block';
      this.textContent = estado.sidebarMinimizada ? '▶' : '≡';
      sidebar.style.width = estado.sidebarMinimizada ? '44px' : '280px';
    });
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

  // A10 (V.1.4.20): fala cujo falante a legenda não revelou. Nunca vira o
  // nome de um cliente — a IA tratava fala do vendedor como do cliente.
  var ROTULO_NAO_IDENTIFICADO = 'Não identificado';

  function rotuloParticipante(speaker) {
    var nome = String(speaker || '').trim();
    var normalizado = normalizarNomeParticipante(nome);
    var vendedor = estado.participantes.vendedor || 'Vendedor';
    var clientes = estado.participantes.clientes || ['Cliente'];
    var primeiroCliente = clientes[0] || 'Cliente';

    if (!normalizado || normalizado === 'participante' || normalizado === normalizarNomeParticipante(ROTULO_NAO_IDENTIFICADO)) {
      return ROTULO_NAO_IDENTIFICADO;
    }
    // "Cliente" só vem do áudio da aba (Whisper), que é sempre o outro lado.
    if (normalizado === 'cliente') return primeiroCliente;
    if (normalizado === 'voce' || normalizado === 'you' || normalizado === 'vendedor' || normalizado === normalizarNomeParticipante(vendedor)) return vendedor;
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
    chrome.storage.local.set({
      saleiaParticipantes: {
        meetingId: MEETING_ID,
        vendedor: estado.participantes.vendedor,
        clientes: estado.participantes.clientes,
      },
    });
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
  let legendasDetectadas = false;
  let verificacaoLegendaTimer = null;

  // Quando uma fala entra (igual, pedaço, versão mais completa, mesma fala
  // por legenda e áudio): chrome-extension/transcricao_rules.js (auditoria
  // T01 — P8, P11, P12). Antes, um conjunto com os 50 primeiros caracteres
  // (limpo a cada 60s) descartava a versão completa de uma frase longa e
  // deixava a varredura regravar legendas antigas.
  // fonte: 'audio' quando o texto veio do Whisper (microfone ou aba).
  function commitarFrase(speaker, texto, fonte) {
    if (!texto || texto.trim().length < 10) return;
    if (eRuidoUI(texto.trim())) return;
    speaker = rotuloParticipante(speaker);
    var t = texto.trim();
    var nova = { speaker: speaker, text: t, timestamp: new Date().toISOString(), fonte: fonte || 'legenda' };
    var decisao = SaleiaTranscricao.decidirCommit(estado.transcricao, nova, estado.ultimoIndexEnviado);
    if (decisao.acao === 'ignorar') return;
    if (decisao.acao === 'substituir') {
      estado.transcricao[decisao.indice].text = t;
      return;
    }
    estado.transcricao.push(nova);
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
    // Texto vazado de OUTRAS extensões injetadas na mesma aba (ex.: EasySub) —
    // o MutationObserver observa document.body inteiro (nao so o Meet), entao
    // qualquer painel flutuante de outra extensao pode ser capturado como se
    // fosse fala real. Ver achado de 05/09/2026: "Nenhuma reuniao ativa" do
    // widget do EasySub estava sendo tratado como transcricao.
    if (/^Nenhuma reuni[aã]o ativa$/i.test(texto)) return true;
    if (/^Finalizar captura$/i.test(texto)) return true;
    if (/^Capturar [aá]udio( \(Whisper\))?$/i.test(texto)) return true;
    // Recursos nativos "Gemini" do proprio Google Meet (banners/tooltips) —
    // achado em 05/09/2026, mesmo dia do achado do EasySub acima. Match por
    // frase EXATA (nao "contem Gemini") para nao descartar uma fala real do
    // cliente que mencione o produto Gemini durante a reuniao.
    if (/^Notifica[cç][oõ]es do recurso Pe[cç]a ao Gemini$/i.test(texto)) return true;
    if (/^Pe[cç]a ao Gemini$/i.test(texto)) return true;
    if (/^Fazer anota[cç][oõ]es com o Gemini$/i.test(texto)) return true;
    // Tarefa A1 (24/09/2026) — ruído de UI achado em transcripts reais de
    // produção, sempre por frase exata/prefixo de sistema, nunca "contém".
    if (/^O Gemini vai analisar sua conversa/i.test(texto)) return true;
    if (/^Saiba mais$/i.test(texto)) return true;
    if (/^h[aá] \d+ (segundos?|minutos?|horas?)$/i.test(texto)) return true;
    if (/^\d+ (segundos?|minutos?) restantes?$/i.test(texto)) return true;
    if (/^(Transcribing|Transcri[cç][aã]o|Transcrevendo): /i.test(texto)) return true;
    if (/^Configurar o modo de exibi[cç][aã]o/i.test(texto)) return true;
    // Declarações CSS (texto de <style> capturado como folha de texto)
    if (/[a-z-]+\s*:\s*[^;{}]+;/i.test(texto) && /^[\sa-z0-9%:;.,#(){}"'\/-]+$/i.test(texto)) return true;
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

  // ── A10 (V.1.4.20): falante pela estrutura da legenda ──────────────
  // O Meet troca as classes ofuscadas (zs7s8d, NWpY1...) sem aviso, e
  // aí todo falante virava "Participante". A estrutura é estável: cada
  // bloco de legenda tem a foto (avatar) do falante, o nome curto e, depois,
  // o texto. Sobe do texto até o menor bloco com foto e pega o 1º texto
  // com cara de nome.
  var PARTICULAS_NOME = { da: 1, de: 1, di: 1, do: 1, das: 1, dos: 1, e: 1 };

  function pareceNomeDeFalante(texto) {
    var t = String(texto || '').trim();
    if (t.length < 2 || t.length > 40) return false;
    if (/[.,!?;:…"“”_@#()\d]/.test(t)) return false;
    var palavras = t.split(/\s+/);
    if (palavras.length > 4) return false;
    if (normalizarNomeParticipante(t) === 'voce' || normalizarNomeParticipante(t) === 'you') return true;
    // Nome: toda palavra começa com maiúscula, exceto partículas (da, de, dos...).
    // Fala ("Tudo bem com você") quase nunca passa nisso.
    return palavras.every(function (p, i) {
      if (i > 0 && PARTICULAS_NOME[p]) return true;
      return /^[A-ZÁÉÍÓÚÂÊÔÃÕÀÇ]/.test(p);
    });
  }

  function folhasDeTexto(raiz) {
    var folhas = [];
    raiz.querySelectorAll('*').forEach(function (n) {
      if (n.children.length === 0 && n.textContent.trim() && !n.closest('style,script,noscript,template')) folhas.push(n);
    });
    if (!folhas.length && raiz.textContent.trim()) folhas.push(raiz);
    return folhas;
  }

  function blocoDoFalante(el) {
    var atual = el;
    for (var i = 0; i < 6 && atual && atual !== document.body; i++) {
      var fotos = atual.querySelectorAll ? atual.querySelectorAll('img, [role="img"]').length : 0;
      // Mais de uma foto = já subiu até a área com vários falantes; o
      // nome achado ali seria de outra pessoa.
      if (fotos > 1) return null;
      if (fotos === 1 && folhasDeTexto(atual).length >= 2) return atual;
      atual = atual.parentElement;
    }
    return null;
  }

  // { nome, eONome }: eONome = el é o próprio elemento do nome (ignorar).
  function detectarFalantePorEstrutura(el) {
    var bloco = blocoDoFalante(el);
    if (!bloco) return { nome: null, eONome: false };
    var folhas = folhasDeTexto(bloco);
    var nomeEl = null;
    for (var i = 0; i < folhas.length - 1; i++) {  // nome nunca é o último (depois dele vem a fala)
      if (pareceNomeDeFalante(folhas[i].textContent)) { nomeEl = folhas[i]; break; }
    }
    if (!nomeEl) return { nome: null, eONome: false };
    if (nomeEl === el) return { nome: null, eONome: true };
    // O nome tem de vir antes da fala (ou estar dentro do elemento recebido).
    var antes = el.contains(nomeEl) || (nomeEl.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING);
    return { nome: antes ? nomeEl.textContent.trim() : null, eONome: false };
  }

  // Sem o nome, deixa no console o HTML ao redor da legenda (1x/min) para
  // ajustar a detecção: F12 → Console → filtrar "SALEIA-FALANTE".
  var _ultimoAvisoFalante = 0;
  function avisarFalanteNaoIdentificado(el, texto) {
    var agora = Date.now();
    if (agora - _ultimoAvisoFalante < 60000) return;
    _ultimoAvisoFalante = agora;
    var raiz = el;
    for (var i = 0; i < 4 && raiz.parentElement && raiz.parentElement !== document.body; i++) raiz = raiz.parentElement;
    console.warn('[SALEIA-FALANTE] falante não identificado para "' + texto.substring(0, 60) + '". HTML ao redor:\n' +
      (raiz.outerHTML || '').substring(0, 3000));
  }

  // ── A12 (V.1.4.21): só a área de legendas ──────────────────────────
  // O observador vê a página inteira; a lista de exclusão (eRuidoUI) nunca
  // acompanhou o Meet: 22,6% das linhas de 50 reuniões eram texto de tela
  // (avisos do Gemini, botões, nomes de dispositivo, painel do Tactiq).
  // Quando a área de legendas existe, só o texto de dentro dela vale. Sem
  // ela (Meet mudou o rótulo), volta ao comportamento antigo.
  var REGIAO_LEGENDAS_SEL = '[role="region"][aria-label*="egenda" i], [role="region"][aria-label*="aption" i]';
  var _regiaoLegendas = null;
  var _regiaoLegendasEm = 0;
  var _modoLegendaLogado = '';

  function regiaoLegendas() {
    var agora = Date.now();
    if (agora - _regiaoLegendasEm > 3000 || (_regiaoLegendas && !_regiaoLegendas.isConnected)) {
      _regiaoLegendas = null;
      document.querySelectorAll(REGIAO_LEGENDAS_SEL).forEach(function (r) {
        if (!_regiaoLegendas && !r.closest('#saleia-sidebar')) _regiaoLegendas = r;
      });
      _regiaoLegendasEm = agora;
      var modo = _regiaoLegendas ? 'so-area-de-legendas' : 'pagina-inteira';
      if (modo !== _modoLegendaLogado) {
        _modoLegendaLogado = modo;
        console.log('[SALEIA-LEGENDA] modo de captura: ' + modo);
      }
    }
    return _regiaoLegendas;
  }

  function processarElementoLegenda(el) {
    if (!el || !el.textContent) return;
    if (el.closest && el.closest('#saleia-sidebar')) return;
    var regiao = regiaoLegendas();
    if (regiao && !regiao.contains(el)) return;
    // Tarefa A1: <style>/<script> são "folhas" de texto para o observer e
    // vazavam CSS ("height: 100%;") como se fosse fala.
    if (el.closest && el.closest('style,script,noscript,template')) return;
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
    if (speaker === 'Participante') {
      // A10: as classes acima mudaram no Meet; tenta pela estrutura.
      var falante = detectarFalantePorEstrutura(el);
      if (falante.eONome) return;  // o próprio nome do falante, não é fala
      if (falante.nome) speaker = falante.nome;
      else avisarFalanteNaoIdentificado(el, texto);
    }

    // Remove o nome do speaker do início do texto se estiver concatenado (ex: "VocêQue nos ajudou")
    if (speaker !== 'Participante' && texto.toLowerCase().startsWith(speaker.toLowerCase())) {
      texto = texto.substring(speaker.length).trim();
      if (!texto || texto.length < 15 || texto.split(/\s+/).length < 3) return;
    }

    // Ignora a legenda ainda na tela que já foi gravada igual (varredura a cada 2s)
    speaker = rotuloParticipante(speaker);
    if (SaleiaTranscricao.jaGravada(estado.transcricao, speaker, texto)) return;

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
  // Tarefa B8: /tempo-real devolve auth_status. Sem isso, token expirado
  // virava anônimo em silêncio e a reunião ficava sem vendedor. O aviso
  // só orienta o vendedor — nunca mostra detalhe técnico (regra da
  // sidebar desde a V.1.4.40).
  var TEXTOS_AVISO_LOGIN = {
    expirado: '🔒 Sua sessão expirou. Clique no ícone da SALEIA na barra do Chrome e entre de novo para que esta reunião fique no seu histórico.',
    invalido: '🔒 Sua sessão não é mais válida. Clique no ícone da SALEIA na barra do Chrome e entre de novo.',
    anonimo: '👤 Você não está conectado. Entre pelo ícone da SALEIA na barra do Chrome para esta reunião ficar no seu histórico.',
  };

  function tratarSessaoDaResposta(dados) {
    if (!dados || !dados.auth_status) return;
    if (dados.token_renovado || dados.auth_status === 'expirado' || dados.auth_status === 'invalido') {
      if (chrome.runtime && chrome.runtime.id) {
        chrome.runtime.sendMessage({
          tipo: 'atualizarSessao',
          token_renovado: dados.token_renovado || null,
          encerrar: dados.auth_status === 'expirado' || dados.auth_status === 'invalido',
        });
      }
    }
    var aviso = document.getElementById('saleia-login-aviso');
    if (!aviso) return;
    var texto = TEXTOS_AVISO_LOGIN[dados.auth_status];
    aviso.textContent = texto || '';
    aviso.style.display = texto ? 'block' : 'none';
  }

  function exibirAvisoLegenda() { const a = document.getElementById('saleia-legenda-aviso'); if (a) a.style.display = 'block'; }
  function ocultarAvisoLegenda() { const a = document.getElementById('saleia-legenda-aviso'); if (a) a.style.display = 'none'; }

  // Primeira checagem bem mais cedo que o ciclo normal (60s) — setInterval
  // só dispara pela primeira vez depois do intervalo inteiro passar, então
  // sem isso a extensão fica ate 60s sem tentar nenhuma analise mesmo com
  // legenda/audio ja sendo capturados desde o segundo 0 (achado real,
  // 05/09/2026 — "Próxima análise em: 60s" parado no início de toda
  // reunião). Ciclos seguintes continuam no ritmo normal, sem mudar o
  // custo de IA em regime estável.
  var PRIMEIRA_ANALISE_SEGUNDOS = 20;

  function iniciarContadorRegressivo() {
    estado.contador = PRIMEIRA_ANALISE_SEGUNDOS;
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

  function checarEEnviar() {
    if (!estado.ativo) return;
    // Só analisa se houver entradas novas desde o último envio — evita análise de silêncio
    if (estado.transcricao.length <= estado.ultimoIndexEnviado) return;
    enviarParaBackend();
  }

  // A11: o backend devolve intervalo_analise_s em /tempo-real — o ritmo
  // muda sem reinstalar a extensão. Fora de 10-120s é ignorado.
  function aplicarIntervaloDoServidor(segundos) {
    var s = parseInt(segundos, 10);
    if (!s || s < 10 || s > 120 || s === CONFIG.intervaloAnalise) return;
    CONFIG.intervaloAnalise = s;
    if (estado.timerEnvio) {
      clearInterval(estado.timerEnvio);
      estado.timerEnvio = setInterval(checarEEnviar, s * 1000);
    }
  }

  function iniciarEnvioPeriodico() {
    // Primeira checagem em PRIMEIRA_ANALISE_SEGUNDOS (não CONFIG.intervaloAnalise) —
    // setTimeout dispara uma vez, depois o setInterval assume o ritmo normal.
    setTimeout(function () {
      checarEEnviar();
      estado.timerEnvio = setInterval(checarEEnviar, CONFIG.intervaloAnalise * 1000);
    }, PRIMEIRA_ANALISE_SEGUNDOS * 1000);
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
    if (!estado.ativo) return; // API desligada — nenhuma chamada ao backend
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
    if (!estado.ativo) return; // API desligada — nenhuma chamada ao backend
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
    if (!estado.ativo) return; // API desligada — nenhuma chamada ao backend
    const transcricaoParcial = montarTranscricaoParcial();

    // GUARDA: só envia se houver transcrição real com pelo menos 20 caracteres
    // Evita chamadas ao backend quando não há conversa no Meet
    if (!transcricaoParcial || transcricaoParcial.trim().length < 20) {
      exibirAvisoLegenda();
      return;
    }

    // Tarefa A1: só 1 envio em andamento por vez. Sem isso, cada chunk do
    // Whisper (~15s) disparava um novo envio enquanto a análise anterior
    // ainda rodava, reenviando o mesmo delta (ultimoIndexEnviado só avança
    // na resposta) — o backend anexava de novo e rodava IA à toa. O timer
    // periódico pega o que ficou pendente. Trava liberada em toda resposta
    // e, por segurança, após 120s sem resposta.
    if (estado.envioEmAndamento && Date.now() - estado.envioEmAndamento < 120000) return;
    estado.envioEmAndamento = Date.now();

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
    if (!chrome.runtime || !chrome.runtime.id) { estado.envioEmAndamento = 0; return; }
    console.log('[SALEIA-DBG] enviando /tempo-real, tamanho da transcricao:', transcricaoParcial.length);
    chrome.runtime.sendMessage(
      { tipo: 'fetchBackend', url: url, payload: payload },
      function (resp) {
        estado.envioEmAndamento = 0;
        if (chrome.runtime.lastError) {
          console.error('[SALEIA] sendMessage falhou (fetchBackend):', chrome.runtime.lastError.message);
          estado.backendOnline = false;
          return;
        }
        if (!resp || !resp.ok) {
          console.error('[SALEIA] /tempo-real falhou:', resp && resp.error);
          estado.backendOnline = false;
          return;
        }
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
          tratarSessaoDaResposta(dados);
          if (dados.perfil_disc && dados.perfil_disc.tipo) estado.perfilDiscAtual = dados.perfil_disc.tipo;
          aplicarIntervaloDoServidor(dados.intervalo_analise_s);
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

    // 🎯 PRÓXIMA AÇÃO / PRÓXIMA PERGUNTA / POR QUÊ / EVITE
    renderizarNBQ(dados);

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

  function renderizarNBQ(dados) {
    // Prefere next_best_action (novo), cai em next_best_question (legacy)
    var nba = dados.next_best_action;
    var nbq = dados.next_best_question;
    var perguntaEl = document.getElementById('saleia-nbq-pergunta');
    var badgesEl   = document.getElementById('saleia-nbq-badges');
    var objetivoEl = document.getElementById('saleia-nbq-objetivo');
    var motivoEl   = document.getElementById('saleia-nbq-motivo');
    var eviteEl    = document.getElementById('saleia-nbq-evite');
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
      if (eviteEl)    { eviteEl.textContent = ''; eviteEl.style.display = 'none'; }
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

    // --- Evite (só quando o backend enviar; nunca inferido) ---
    if (eviteEl) {
      var evite = nba && nba.evite;
      if (evite) {
        eviteEl.textContent = '🚫 ' + evite;
        eviteEl.style.display = 'block';
      } else {
        eviteEl.textContent = '';
        eviteEl.style.display = 'none';
      }
    }

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


  function animarAtualizacao() {
    const body = document.getElementById('saleia-body');
    if (!body) return;
    body.classList.remove('saleia-fade-in');
    void body.offsetWidth;
    body.classList.add('saleia-fade-in');
  }

  function exibirErroBackend() {
    const statusEl = document.getElementById('saleia-status');
    if (statusEl) statusEl.innerHTML = '<span class="saleia-dot saleia-dot-vermelho"></span> Desconectado';
  }

  function atualizarStatusSidebar() {
    const statusEl = document.getElementById('saleia-status');
    if (!statusEl) return;
    if (estado.ativo) {
      statusEl.innerHTML = '<span class="saleia-dot"></span> Conectado';
    } else {
      statusEl.innerHTML = '<span class="saleia-dot saleia-dot-cinza"></span> API desligada';
    }
  }

})();
