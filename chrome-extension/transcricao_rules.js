/**
 * SALEIA — transcricao_rules.js
 * Regra de quando uma fala capturada entra na transcrição da extensão.
 * Funções puras (sem DOM), carregadas antes do content.js e testadas no
 * Node (tests/js/test_transcricao_rules.js).
 *
 * Auditoria T01 (11/10/2026):
 * - P11: a versão mais completa de uma legenda já gravada era descartada
 *   (fim da frase perdido). Agora substitui a anterior enquanto ela não
 *   foi enviada; depois de enviada, entra como nova (nada se perde).
 * - P12: a pontuação do Meet ("3:30." × "3:30 a gente") impedia a junção.
 *   Comparação agora é sobre palavras normalizadas.
 * - P8: a regra de similaridade juntava falas parecidas de pessoas
 *   diferentes. Agora só junta legenda com áudio (a mesma fala por 2 fontes).
 */
(function (raiz) {
  'use strict';

  var JANELA = 20;          // falas recentes olhadas para igual/parcial
  var DEDUP_JANELA = 15;    // falas recentes olhadas para legenda × áudio
  var DEDUP_LIMIAR = 0.75;  // Dice sobre palavras (par real medido: 0.80)
  var DEDUP_MIN_CHARS = 20;

  function palavras(texto) {
    return String(texto || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/[^\w\s]/g, ' ').split(/\s+/).filter(Boolean);
  }

  function normalizar(texto) {
    return palavras(texto).join(' ');
  }

  function dice(a, b) {
    if (!a.length || !b.length) return 0;
    var contagem = {};
    a.forEach(function (w) { contagem[w] = (contagem[w] || 0) + 1; });
    var comuns = 0;
    b.forEach(function (w) { if (contagem[w] > 0) { contagem[w]--; comuns++; } });
    return (2 * comuns) / (a.length + b.length);
  }

  function comecaCom(texto, prefixo) {
    return texto.length > prefixo.length && texto.slice(0, prefixo.length + 1) === prefixo + ' ';
  }

  // Texto original depois das primeiras palavras de `prefixoNormalizado`.
  function restoDepois(texto, prefixoNormalizado) {
    var k = prefixoNormalizado ? prefixoNormalizado.split(' ').length : 0;
    var orig = String(texto || '').trim().split(/\s+/);
    var contadas = 0, i = 0;
    while (i < orig.length && contadas < k) { contadas += palavras(orig[i]).length; i++; }
    return orig.slice(i).join(' ');
  }

  /**
   * transcricao: [{speaker, text, fonte, bloco?}] (fonte 'audio' ou ausente = legenda;
   *   bloco = texto inteiro do bloco da legenda de onde a fala saiu — V.1.4.29)
   * nova: {speaker, text, fonte}
   * indiceEnviado: quantas falas já foram enviadas ao backend
   * Retorna {acao: 'ignorar'|'substituir'|'adicionar', indice?, motivo,
   *          texto?, bloco?} — texto/bloco (V.1.4.29): o que gravar quando a
   *          fala é a continuação de um bloco já gravado.
   */
  function decidirCommit(transcricao, nova, indiceEnviado) {
    var t = normalizar(nova.text);
    if (!t) return { acao: 'ignorar', motivo: 'vazia' };
    var inicio = Math.max(0, transcricao.length - JANELA);
    var ultimaDoFalante = true;
    for (var i = transcricao.length - 1; i >= inicio; i--) {
      var e = transcricao[i];
      var n = normalizar(e.text);
      if (n === t && e.speaker === nova.speaker) return { acao: 'ignorar', motivo: 'igual' };
      if (e.speaker !== nova.speaker) continue;
      // V.1.4.27: pedaço/versão completa só vale contra a ÚLTIMA fala da
      // pessoa (é a legenda que o Meet ainda está escrevendo). Antes, "Aí
      // sim." de 3 falas atrás era trocada por "Aí sim foi corrido hoje" —
      // fala nova — e a conversa saía fora de ordem.
      if (ultimaDoFalante) {
        ultimaDoFalante = false;
        // V.1.4.29: compara com o bloco inteiro da legenda. Quem fala sem
        // parar fica num bloco só que cresce; antes, a cada pausa o bloco
        // inteiro entrava de novo (teste real de 15/10: "Tá dominado" →
        // "Tá dominado Só isso…" → … em escada). Agora entra só o pedaço novo.
        var base = normalizar(e.bloco || e.text);
        if (base === t) return { acao: 'ignorar', motivo: 'igual' };
        if (comecaCom(base, t)) return { acao: 'ignorar', motivo: 'pedaco_de_gravada' };
        if (comecaCom(t, base)) {
          var resto = restoDepois(nova.text, base);
          if (!resto) return { acao: 'ignorar', motivo: 'igual' };
          if (i >= indiceEnviado) {
            return { acao: 'substituir', indice: i, motivo: 'completa_a_gravada',
                     texto: (String(e.text).trim() + ' ' + resto).trim(), bloco: nova.text };
          }
          return { acao: 'adicionar', motivo: 'completa_a_ja_enviada', texto: resto, bloco: nova.text };
        }
      }
    }
    var p = palavras(nova.text);
    if (p.join(' ').length >= DEDUP_MIN_CHARS) {
      var deAudio = nova.fonte === 'audio';
      var ini2 = Math.max(0, transcricao.length - DEDUP_JANELA);
      for (var j = transcricao.length - 1; j >= ini2; j--) {
        var outra = transcricao[j];
        if ((outra.fonte === 'audio') === deAudio) continue;
        var q = palavras(outra.text);
        if (q.join(' ').length >= DEDUP_MIN_CHARS && dice(p, q) >= DEDUP_LIMIAR) {
          return { acao: 'ignorar', motivo: 'mesma_fala_outra_fonte' };
        }
      }
    }
    return { acao: 'adicionar', motivo: 'nova' };
  }

  /** A legenda ainda na tela (varredura a cada 2s) já foi gravada igual? */
  function jaGravada(transcricao, speaker, texto) {
    var t = normalizar(texto);
    var inicio = Math.max(0, transcricao.length - JANELA);
    for (var i = transcricao.length - 1; i >= inicio; i--) {
      if (transcricao[i].speaker !== speaker) continue;
      if (normalizar(transcricao[i].text) === t) return true;
      if (transcricao[i].bloco && normalizar(transcricao[i].bloco) === t) return true;
    }
    return false;
  }

  var api = { decidirCommit: decidirCommit, jaGravada: jaGravada, normalizar: normalizar };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  raiz.SaleiaTranscricao = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
