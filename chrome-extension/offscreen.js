/**
 * SALEIA — offscreen.js
 * Documento offscreen para captura de áudio via chrome.tabCapture.
 * Roda em contexto de página (tem acesso a MediaRecorder e getUserMedia).
 * Recebe mensagens do background.js via chrome.runtime.onMessage.
 */
'use strict';

let mediaRecorder = null;

chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {

  // ── Iniciar gravação ──────────────────────────────────────────────────
  if (msg.tipo === 'iniciarGravacaoOffscreen') {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      sendResponse({ ok: true }); // já está gravando
      return true;
    }

    // Captura microfone — audioCapture permission (não requer invocação da extensão)
    navigator.mediaDevices.getUserMedia({
      audio: true,
      video: false,
    }).then(function (stream) {
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';

      mediaRecorder = new MediaRecorder(stream, { mimeType: mimeType });

      mediaRecorder.ondataavailable = function (e) {
        if (!e.data || e.data.size < 1024) return; // ignora chunks muito pequenos (<1KB)
        const reader = new FileReader();
        reader.onloadend = function () {
          chrome.runtime.sendMessage({
            tipo: 'audioChunk',
            base64: reader.result,   // formato: "data:audio/webm;base64,XXXX"
            mimeType: mimeType,
          });
        };
        reader.readAsDataURL(e.data);
      };

      // Chunk a cada 15 segundos — bom equilíbrio para Whisper (mín ~5s, máx ~120s)
      mediaRecorder.start(15000);
      sendResponse({ ok: true });
    }).catch(function (err) {
      console.error('[SALEIA-OFFSCREEN] getUserMedia erro:', err.message);
      sendResponse({ ok: false, error: err.message });
    });

    return true; // resposta assíncrona
  }

  // ── Parar gravação ────────────────────────────────────────────────────
  if (msg.tipo === 'pararGravacaoOffscreen') {
    if (mediaRecorder) {
      if (mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
        mediaRecorder.stream.getTracks().forEach(function (t) { t.stop(); });
      }
      mediaRecorder = null;
    }
    sendResponse({ ok: true });
    return true;
  }
});
