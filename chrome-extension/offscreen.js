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
});

async function iniciarGravacaoAba(tabStreamId) {
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

  const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
    ? 'audio/webm;codecs=opus'
    : 'audio/webm';

  mediaRecorder = new MediaRecorder(tabStream, { mimeType: mimeType });

  mediaRecorder.ondataavailable = function (e) {
    if (!e.data || e.data.size < 1024) return; // ignora chunks muito pequenos (<1KB)
    const reader = new FileReader();
    reader.onloadend = function () {
      chrome.runtime.sendMessage({
        tipo: 'audioChunk',
        base64: reader.result,   // formato: "data:audio/webm;base64,XXXX"
        mimeType: mimeType,
        fonte: 'aba',
      });
    };
    reader.readAsDataURL(e.data);
  };

  // Chunk a cada 15 segundos — bom equilíbrio para Whisper (mín ~5s, máx ~120s)
  mediaRecorder.start(15000);
  console.log('[SALEIA-OFFSCREEN] Gravação do áudio da aba iniciada.');
}

function pararGravacaoAba() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
  }
  mediaRecorder = null;

  if (tabStream) { tabStream.getTracks().forEach(function (t) { t.stop(); }); tabStream = null; }
  if (audioContext) { audioContext.close().catch(function () {}); audioContext = null; }
}
