/**
 * SALEIA — offscreen.js
 * Documento offscreen para captura do ÁUDIO DA ABA via chrome.tabCapture.
 * Roda em contexto de página (tem acesso a MediaRecorder). Recebe
 * mensagens do background.js via chrome.runtime.onMessage.
 *
 * Fase 3 do PROMPT MESTRE ("Meetily"): antes disso só o microfone do
 * vendedor era capturado (content.js, getUserMedia direto na página do
 * Meet). Esse arquivo cobre o outro lado — a voz dos participantes saindo
 * pela aba — para o Whisper ter o mesmo alcance que as legendas do Google
 * já têm hoje.
 *
 * Deliberadamente NÃO captura o microfone aqui: um documento offscreen
 * não tem UI visível para o prompt de permissão do Chrome aparecer, então
 * getUserMedia({audio:true}) aqui tende a falhar silenciosamente. O
 * microfone continua sendo capturado em content.js (roda na própria
 * página do Meet, onde o prompt funciona normalmente) — as duas
 * transcrições são mescladas por TEXTO no content.js, não por áudio.
 */
'use strict';

let mediaRecorder = null;
let audioContext = null;
let tabStream = null;
let gravandoAba = false;
let cicloAbaTimer = null;
// Reunião e aba de origem vão em cada pedaço (auditoria T01, P20/P21): o
// service worker pode ter sido reciclado e esquecido os dois.
let meetingIdAba = 'default';
let tabIdAba = null;

chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {

  // ── Iniciar gravação do áudio da aba ─────────────────────────────────
  if (msg.tipo === 'iniciarGravacaoOffscreen') {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      sendResponse({ ok: true }); // já está gravando
      return true;
    }
    if (!msg.tabStreamId) {
      sendResponse({ ok: false, error: 'sem tabStreamId — tabCapture indisponível' });
      return true;
    }
    meetingIdAba = msg.meeting_id || 'default';
    tabIdAba = msg.tabId || null;

    iniciarGravacaoAba(msg.tabStreamId)
      .then(function () { sendResponse({ ok: true }); })
      .catch(function (err) {
        console.error('[SALEIA-OFFSCREEN] Erro ao capturar áudio da aba:', err.message);
        sendResponse({ ok: false, error: err.message });
      });

    return true; // resposta assíncrona
  }

  // ── Parar gravação ────────────────────────────────────────────────────
  if (msg.tipo === 'pararGravacaoOffscreen') {
    pararGravacaoAba();
    sendResponse({ ok: true });
    return true;
  }

  // ── T02: gravação contínua da trilha da aba ───────────────────────────
  if (msg.tipo === 'gravarAba') {
    iniciarGravacaoContinuaAba(msg)
      .then(function () { sendResponse({ ok: true }); })
      .catch(function (err) {
        console.error('[SALEIA-OFFSCREEN] Erro ao gravar a aba:', err.message);
        sendResponse({ ok: false, error: err.message });
      });
    return true;
  }

  if (msg.tipo === 'controleGravacaoAba') {
    if (gravadorAba && msg.acao === 'parar') {
      // Só responde depois do último bloco + "encerrar" estarem na fila do
      // background: em seguida ele pode fechar este documento (máx. 5s).
      const g = gravadorAba;
      gravadorAba = null;
      Promise.race([g.parar(), new Promise(function (r) { setTimeout(r, 5000); })]).then(function () {
        liberarStreamSeOcioso();
        sendResponse({ ok: true, gravando: false });
      });
      return true;
    }
    if (gravadorAba) {
      if (msg.acao === 'pausar') gravadorAba.pausar();
      if (msg.acao === 'retomar') gravadorAba.retomar();
    }
    sendResponse({ ok: true, gravando: !!(gravadorAba && gravadorAba.gravando()) });
    return true;
  }
});

function mimeTypeAudio() {
  return MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
}

// Um stream da aba só: o Chrome não deixa capturar a mesma aba duas vezes.
// A transcrição (ciclos de 15s) e a gravação contínua (T02) usam o mesmo.
async function obterStreamAba(tabStreamId) {
  if (tabStream && tabStream.active) return tabStream;
  if (!tabStreamId) throw new Error('sem tabStreamId — tabCapture indisponível');
  tabStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      mandatory: {
        chromeMediaSource: 'tab',
        chromeMediaSourceId: tabStreamId,
      },
    },
    video: false,
  });

  // getUserMedia com chromeMediaSource:'tab' INTERCEPTA o áudio da aba —
  // sem reconectar ao destino, o vendedor perderia o som da reunião
  // inteira enquanto a captura estivesse ativa. O AudioContext só existe
  // pra devolver esse áudio pros alto-falantes; a gravação usa o stream
  // original (tabStream), não o de saída do AudioContext.
  audioContext = new AudioContext();
  const fonte = audioContext.createMediaStreamSource(tabStream);
  fonte.connect(audioContext.destination);
  return tabStream;
}

async function iniciarGravacaoAba(tabStreamId) {
  await obterStreamAba(tabStreamId);
  gravandoAba = true;
  iniciarCicloAba(mimeTypeAudio());
  console.log('[SALEIA-OFFSCREEN] Gravação do áudio da aba iniciada.');
}

// ── T02: gravação contínua (chrome-extension/gravacao_rules.js) ─────────
let gravadorAba = null;

function enviarAoBackground(tipo, corpo) {
  return chrome.runtime.sendMessage({ tipo: tipo, corpo: corpo }).catch(function (e) {
    console.warn('[SALEIA-OFFSCREEN] ' + tipo + ' não chegou ao background:', e && e.message);
  });
}

async function iniciarGravacaoContinuaAba(msg) {
  if (gravadorAba && gravadorAba.gravando()) return;
  const stream = await obterStreamAba(msg.tabStreamId);
  const mimeType = mimeTypeAudio();
  gravadorAba = SaleiaGravacao.criarGravadorContinuo({
    stream: stream, trackId: 'aba', meetingId: msg.meeting_id, mimeType: mimeType, audioBitsPerSecond: msg.bitrate,
    blocoMs: (msg.bloco_s || 5) * 1000, rotacaoMs: (msg.rotacao_s || 600) * 1000,
    aoIniciar: function (info) { return enviarAoBackground('gravacaoIniciar', info); },
    aoBloco: function (bloco) {
      return SaleiaGravacao.prepararConteudo(bloco.blob).then(function (c) {
        const corpo = Object.assign({}, bloco, c);
        delete corpo.blob;
        return enviarAoBackground('gravacaoBloco', corpo);
      });
    },
    aoEncerrar: function (fim) { return enviarAoBackground('gravacaoEncerrar', fim); },
    aoErro: function (e) { console.error('[SALEIA-OFFSCREEN] gravação:', e); },
    // Áudio da aba acabou (aba fechada): a gravação já foi encerrada pelo gravador.
    aoFimDoAudio: function () {
      console.log('[SALEIA-OFFSCREEN] Áudio da aba terminou: gravação encerrada.');
      gravadorAba = null;
      liberarStreamSeOcioso();
      enviarAoBackground('gravacaoTrilhaAcabou', { track_id: 'aba' });
    },
  });
  gravadorAba.iniciar();
  console.log('[SALEIA-OFFSCREEN] Gravação contínua da aba iniciada.');
}

function liberarStreamSeOcioso() {
  if (gravandoAba || (gravadorAba && gravadorAba.gravando())) return;
  if (tabStream) { tabStream.getTracks().forEach(function (t) { t.stop(); }); tabStream = null; }
  if (audioContext) { audioContext.close().catch(function () {}); audioContext = null; }
}

// A12 (V.1.4.21): com start(15000) só o 1º pedaço trazia o cabeçalho do
// WebM; os seguintes não eram arquivos válidos sozinhos (o Whisper local
// recusava com "Invalid data found"). Agora cada ciclo de 15s é uma
// gravação própria (para e recomeça), igual ao microfone em content.js.
function iniciarCicloAba(mimeType) {
  if (!gravandoAba || !tabStream) return;
  const partes = [];
  const recorder = new MediaRecorder(tabStream, { mimeType: mimeType });
  mediaRecorder = recorder;
  recorder.ondataavailable = function (e) {
    if (e.data && e.data.size) partes.push(e.data);
  };
  recorder.onstop = function () {
    const blob = new Blob(partes, { type: mimeType });
    if (blob.size >= 1024) { // ignora pedaços muito pequenos (<1KB)
      const reader = new FileReader();
      reader.onloadend = function () {
        chrome.runtime.sendMessage({
          tipo: 'audioChunk',
          base64: reader.result,   // formato: "data:audio/webm;base64,XXXX"
          mimeType: mimeType,
          fonte: 'aba',
          meeting_id: meetingIdAba,
          tabId: tabIdAba,
        });
      };
      reader.readAsDataURL(blob);
    }
    iniciarCicloAba(mimeType);  // próximo ciclo (para sozinho se gravandoAba=false)
  };
  recorder.start();
  // 15s — bom equilíbrio para Whisper (mín ~5s, máx ~120s)
  cicloAbaTimer = setTimeout(function () {
    if (recorder.state !== 'inactive') recorder.stop();
  }, 15000);
}

function pararGravacaoAba() {
  gravandoAba = false;
  if (cicloAbaTimer) { clearTimeout(cicloAbaTimer); cicloAbaTimer = null; }
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();  // envia o último pedaço; o onstop não reinicia
  }
  mediaRecorder = null;
  // Parar a transcrição não pode cortar a gravação contínua (T02).
  liberarStreamSeOcioso();
}
