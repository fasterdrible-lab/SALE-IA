/**
 * SALEIA — quem_e_quem_rules.js
 * "Quem é quem" da reunião (ext 1.4.35 / V.1.4.186). Funções puras (sem
 * DOM), carregadas antes do content.js e testadas no Node
 * (tests/js/test_quem_e_quem.js).
 *
 * A legenda do Meet não mostra e-mail, só o nome de exibição da conta
 * ("Você" para quem usa a extensão; o começo do e-mail quando a conta não
 * tem nome). No começo de cada reunião o vendedor diz, para cada nome do
 * Meet, o nome real e o papel (vendedor / cliente / outro). Vale só para
 * aquela reunião: nada de vendedor ou cliente fixo entre reuniões.
 *
 * mapa = { "<nome no Meet>": { nome: "<nome real>", papel: "vendedor"|"cliente"|"outro"|"" } }
 */
(function (raiz) {
  'use strict';

  var VOCE = 'Você';
  var NAO_IDENTIFICADO = 'Não identificado';
  var PAPEIS = ['vendedor', 'cliente', 'outro'];
  // Texto de ícone do Meet (fonte de ícones por ligadura) que aparece junto
  // do nome no quadro de cada pessoa.
  var ICONES = { keep: 1, keep_off: 1, more_vert: 1, mic_off: 1, mic_none: 1, mic: 1,
    videocam_off: 1, push_pin: 1, frame_person: 1, visual_effects: 1, back_hand: 1,
    pan_tool: 1, close: 1, remove: 1, devices: 1 };

  function normalizar(valor) {
    return String(valor || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
      .trim().toLowerCase();
  }

  function ehVoce(nome) {
    var n = normalizar(nome);
    return n === 'voce' || n === 'you' || n === 'vendedor';
  }

  function entrada(mapa, nomeMeet) {
    var e = mapa && mapa[nomeMeet];
    return (e && typeof e === 'object') ? e : null;
  }

  // Nome que vai na transcrição para a fala de `nomeMeet`.
  function rotular(mapa, nomeMeet, vendedorPadrao) {
    var bruto = String(nomeMeet || '').trim();
    var n = normalizar(bruto);
    if (!n || n === 'participante' || n === normalizar(NAO_IDENTIFICADO)) return NAO_IDENTIFICADO;
    if (ehVoce(bruto)) {
      var eu = entrada(mapa, VOCE);
      return (eu && eu.nome) || vendedorPadrao || 'Vendedor';
    }
    // "Cliente" só vem do áudio da aba (Whisper): é sempre o outro lado.
    if (n === 'cliente') {
      for (var k in (mapa || {})) {
        var c = entrada(mapa, k);
        if (c && c.papel === 'cliente') return c.nome || k;
      }
      return 'Cliente';
    }
    var e = entrada(mapa, bruto);
    return (e && e.nome) || bruto;
  }

  // Nome de pessoa lido do quadro/painel do Meet (não da legenda).
  function nomeDePessoa(texto) {
    var t = String(texto || '').trim();
    if (/\((você|voce|you)\)$/i.test(t)) return null;  // o próprio vendedor = "Você"
    if (t.length < 2 || t.length > 80) return null;
    if (ICONES[t] || /_/.test(t)) return null;
    if (/^(reenquadrar|reframe|fixar|desafixar|pin|unpin)$/i.test(t)) return null;  // botões do quadro
    if (ehVoce(t)) return null;
    if (/^[a-z]{3}-[a-z]{4}-[a-z]{3}$/i.test(t)) return null;  // código da reunião
    if (/[!?…:;"“”()\[\]{}<>|]/.test(t)) return null;
    if (t.split(/\s+/).length > 8) return null;
    return t;
  }

  // Lista enviada ao servidor: "Você" sempre (papel padrão vendedor) + cada
  // nome do Meet conhecido nesta reunião.
  function listaParaServidor(mapa, nomesConhecidos, vendedorPadrao) {
    var eu = entrada(mapa, VOCE) || {};
    var lista = [{
      nome_meet: VOCE,
      nome: eu.nome || vendedorPadrao || 'Vendedor',
      papel: eu.papel || 'vendedor',
    }];
    var vistos = {};
    vistos[VOCE] = 1;
    var todos = (nomesConhecidos || []).concat(Object.keys(mapa || {}));
    todos.forEach(function (nomeMeet) {
      var bruto = String(nomeMeet || '').trim();
      if (!bruto || vistos[bruto] || ehVoce(bruto)) return;
      vistos[bruto] = 1;
      var e = entrada(mapa, bruto) || {};
      lista.push({ nome_meet: bruto, nome: e.nome || bruto, papel: e.papel || '' });
    });
    return lista.slice(0, 30);
  }

  // Grava o que o vendedor digitou para um nome do Meet. Nome vazio e papel
  // vazio = apaga a entrada.
  function definir(mapa, nomeMeet, nome, papel) {
    var novo = Object.assign({}, mapa || {});
    var n = String(nome || '').trim().slice(0, 80);
    var p = PAPEIS.indexOf(papel) >= 0 ? papel : '';
    if (n === nomeMeet && nomeMeet !== VOCE) n = '';
    if (!n && !p) delete novo[nomeMeet];
    else novo[nomeMeet] = { nome: n, papel: p };
    return novo;
  }

  // Texto curto da sidebar: "Pedro (vendedor) · André (cliente)".
  function resumo(mapa, nomesConhecidos, vendedorPadrao) {
    return listaParaServidor(mapa, nomesConhecidos, vendedorPadrao).map(function (p) {
      return p.nome + (p.papel ? ' (' + p.papel + ')' : '');
    }).join(' · ');
  }

  var api = {
    VOCE: VOCE, NAO_IDENTIFICADO: NAO_IDENTIFICADO, PAPEIS: PAPEIS,
    normalizar: normalizar, ehVoce: ehVoce, rotular: rotular, nomeDePessoa: nomeDePessoa,
    listaParaServidor: listaParaServidor, definir: definir, resumo: resumo,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  raiz.SaleiaQuemEQuem = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
