/**
 * SALEIA — gravacao_rules.js
 * Gravação contínua do áudio (T02 do roteiro Audio-First). Sem DOM e sem
 * chrome.*: tudo que depende do navegador é injetado, para rodar igual no
 * offscreen (trilha da aba), no content.js (trilha do microfone), no
 * service worker (fila de envio) e nos testes do Node
 * (tests/js/test_gravacao_extensao.js).
 *
 * - criarGravadorContinuo: um MediaRecorder por trilha que não para
 *   (blocos de `blocoMs` via timeslice — sem o buraco do para-e-recomeça);
 *   a cada `rotacaoMs` recomeça com recording_id novo (cabeçalho WebM novo),
 *   então um bloco perdido estraga no máximo uma gravação.
 * - criarFilaDeEnvio: guarda o que não foi enviado e reenvia em ordem
 *   (iniciar → blocos → encerrar), sobrevivendo a queda de conexão e ao
 *   service worker ser reciclado.
 */
(function (raiz) {
  'use strict';

  function gerarIdPadrao() {
    var c = raiz.crypto;
    if (c && c.randomUUID) return c.randomUUID();
    return 'rec-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
  }

  /**
   * opcoes: {stream, trackId, meetingId, blocoMs, rotacaoMs, mimeType,
   *          MediaRecorder, agora, gerarId, setTimeout, clearTimeout,
   *          aoIniciar(info), aoBloco(bloco) -> Promise, aoEncerrar(info)}
   * Os 3 callbacks rodam em ordem estrita (uma corrente de promises):
   * o encerrar de uma gravação nunca chega antes do último bloco dela.
   */
  function criarGravadorContinuo(opcoes) {
    var agora = opcoes.agora || function () { return Date.now(); };
    var gerarId = opcoes.gerarId || gerarIdPadrao;
    var agendar = opcoes.setTimeout || raiz.setTimeout;
    var desagendar = opcoes.clearTimeout || raiz.clearTimeout;
    var Recorder = opcoes.MediaRecorder || raiz.MediaRecorder;
    var corrente = Promise.resolve();
    var atual = null;   // {recorder, recordingId, sequence, inicioBloco, timer}
    var ativo = false;

    function emOrdem(fn) {
      corrente = corrente.then(fn).catch(function (e) {
        if (opcoes.aoErro) opcoes.aoErro(e);
      });
      return corrente;
    }

    function comecarGravacao() {
      var info = {
        recording_id: gerarId(), meeting_id: opcoes.meetingId, track_id: opcoes.trackId,
        codec: opcoes.mimeType || '', iniciada_em_ms: agora(),
      };
      var rec = new Recorder(opcoes.stream, opcoes.mimeType ? { mimeType: opcoes.mimeType } : undefined);
      var estado = { recorder: rec, recordingId: info.recording_id, sequence: 0, inicioBloco: info.iniciada_em_ms, timer: null };
      atual = estado;
      emOrdem(function () { return opcoes.aoIniciar && opcoes.aoIniciar(info); });
      rec.ondataavailable = function (e) {
        if (!e.data || !e.data.size) return;
        var fim = agora();
        var bloco = {
          recording_id: estado.recordingId, meeting_id: opcoes.meetingId, track_id: opcoes.trackId,
          sequence: estado.sequence++, start_ms: estado.inicioBloco, end_ms: Math.max(fim, estado.inicioBloco + 1),
          recorded_at: new Date(fim).toISOString(), blob: e.data,
        };
        estado.inicioBloco = bloco.end_ms;
        emOrdem(function () { return opcoes.aoBloco(bloco); });
      };
      rec.onstop = function () {
        var ultima = estado.sequence - 1;
        emOrdem(function () {
          return opcoes.aoEncerrar && opcoes.aoEncerrar({ recording_id: estado.recordingId, ultima_sequence: ultima });
        });
        if (atual === estado) atual = null;
        if (ativo) comecarGravacao();  // rotação: a próxima começa colada
      };
      rec.start(opcoes.blocoMs);
      estado.timer = agendar(function () {
        if (rec.state !== 'inactive') rec.stop();  // onstop recomeça (ativo continua true)
      }, opcoes.rotacaoMs);
    }

    function pararAtual() {
      if (!atual) return;
      desagendar(atual.timer);
      if (atual.recorder.state !== 'inactive') atual.recorder.stop();
    }

    return {
      iniciar: function () { if (ativo) return; ativo = true; comecarGravacao(); },
      // Pausar encerra a gravação atual; retomar abre outra. Assim o
      // relógio de cada gravação é contínuo (sem tempo "parado" no meio).
      pausar: function () { if (!ativo) return; ativo = false; pararAtual(); },
      retomar: function () { if (ativo) return; ativo = true; comecarGravacao(); },
      parar: function () { ativo = false; pararAtual(); return corrente; },
      gravando: function () { return ativo; },
      recordingAtual: function () { return atual ? atual.recordingId : null; },
      ocioso: function () { return corrente; },
    };
  }

  /** Blob → {audio_base64, content_hash (SHA-256 hex), tamanho}. */
  function prepararConteudo(blob, cripto) {
    cripto = cripto || raiz.crypto;
    return blob.arrayBuffer().then(function (buf) {
      return cripto.subtle.digest('SHA-256', buf).then(function (h) {
        var hex = Array.prototype.map.call(new Uint8Array(h), function (b) { return ('0' + b.toString(16)).slice(-2); }).join('');
        var bytes = new Uint8Array(buf);
        var bin = '';
        for (var i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
        return { audio_base64: raiz.btoa(bin), content_hash: hex, tamanho: bytes.length };
      });
    });
  }

  /**
   * Fila de envio (service worker). item: {id, tipo: 'iniciar'|'bloco'|'encerrar', corpo}
   * armazenamento (um registro por item — 1h offline não reescreve tudo a cada bloco):
   *   {listar() -> Promise<itens em ordem de id>, inserir(item), remover(id)}
   * enviar(item) -> Promise<{status}> (status HTTP; 0 = sem rede)
   */
  function criarFilaDeEnvio(opcoes) {
    var armazenamento = opcoes.armazenamento;
    var enviar = opcoes.enviar;
    var maxItens = opcoes.maxItens || 3000;  // ~4h de 2 trilhas com blocos de 5s
    var agora = opcoes.agora || function () { return Date.now(); };
    var itens = null;
    var processando = null;
    var contador = 0;

    function carregar() {
      if (itens) return Promise.resolve(itens);
      return armazenamento.listar().then(function (salvos) { itens = salvos || []; return itens; });
    }

    // id em ordem de chegada também na ordenação de texto do IndexedDB
    function novoId() {
      return ('000000000000000' + agora()).slice(-15) + '-' + ('00000' + (contador++ % 1e6)).slice(-6);
    }

    function adicionar(tipo, corpo) {
      return carregar().then(function () {
        if (itens.length >= maxItens) return { aceito: false, motivo: 'fila_cheia' };
        var item = { id: novoId(), tipo: tipo, corpo: corpo };
        return armazenamento.inserir(item).then(function () { itens.push(item); return { aceito: true }; });
      });
    }

    // Resultado por status: tirar da fila (feito / sem conserto) ou parar e tentar depois.
    function classificar(item, status) {
      if (status >= 200 && status < 300) return 'feito';
      if (status === 401) return 'parar_login';
      if (status === 0 || status === 429 || status >= 500) return 'tentar_depois';
      if (status === 403) return 'parar_desligada';
      // 400/404/409: o servidor nunca vai aceitar este item (ex.: bloco de
      // gravação já encerrada) — sai da fila para não travar o resto.
      return 'descartar';
    }

    function processar() {
      if (processando) return processando;
      processando = carregar().then(function proximo() {
        if (!itens.length) return { pendentes: 0, motivo: 'vazia' };
        var item = itens[0];
        return Promise.resolve(enviar(item)).then(function (r) { return (r && r.status) || 0; }, function () { return 0; })
          .then(function (status) {
            var resultado = classificar(item, status);
            if (resultado === 'feito' || resultado === 'descartar') {
              if (resultado === 'descartar' && opcoes.aoDescartar) opcoes.aoDescartar(item, status);
              return armazenamento.remover(item.id).then(function () { itens.shift(); return proximo(); });
            }
            return { pendentes: itens.length, motivo: resultado };
          });
      }).then(function (r) { processando = null; return r; }, function (e) { processando = null; throw e; });
      return processando;
    }

    return {
      adicionar: adicionar,
      processar: processar,
      pendentes: function () { return carregar().then(function () { return itens.length; }); },
    };
  }

  var api = {
    criarGravadorContinuo: criarGravadorContinuo,
    criarFilaDeEnvio: criarFilaDeEnvio,
    prepararConteudo: prepararConteudo,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  raiz.SaleiaGravacao = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
