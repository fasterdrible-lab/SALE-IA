// "Quem é quem" da reunião (V.1.4.186 / ext 1.4.35): chrome-extension/quem_e_quem_rules.js.
// Run: node --test tests/js/test_quem_e_quem.js
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const Q = require('../../chrome-extension/quem_e_quem_rules.js');

test('rotular: nome do Meet → nome real informado; sem informar fica o nome do Meet', () => {
  const mapa = { fasterdrible: { nome: 'André', papel: 'cliente' } };
  assert.equal(Q.rotular(mapa, 'fasterdrible', 'Login'), 'André');
  assert.equal(Q.rotular(mapa, 'Ana Souza', 'Login'), 'Ana Souza');
});

test('rotular: "Você" → nome informado; sem informar → nome do login; sem login → Vendedor', () => {
  assert.equal(Q.rotular({ 'Você': { nome: 'Pedro', papel: 'vendedor' } }, 'Você', 'Login'), 'Pedro');
  assert.equal(Q.rotular({}, 'você', 'Login'), 'Login');
  assert.equal(Q.rotular({}, 'You', ''), 'Vendedor');
});

test('rotular: vazio/participante → Não identificado; "Cliente" (áudio) → 1º cliente informado', () => {
  assert.equal(Q.rotular({}, '', 'L'), 'Não identificado');
  assert.equal(Q.rotular({}, 'Participante', 'L'), 'Não identificado');
  assert.equal(Q.rotular({}, 'Cliente', 'L'), 'Cliente');
  assert.equal(Q.rotular({ x: { nome: 'Rita', papel: 'cliente' } }, 'Cliente', 'L'), 'Rita');
});

test('listaParaServidor: "Você" sempre primeiro (vendedor por padrão), depois cada nome do Meet uma vez', () => {
  const mapa = { fasterdrible: { nome: 'André', papel: 'cliente' } };
  assert.deepEqual(Q.listaParaServidor(mapa, ['fasterdrible', 'Ana', 'Você', 'Ana'], 'Pedro'), [
    { nome_meet: 'Você', nome: 'Pedro', papel: 'vendedor' },
    { nome_meet: 'fasterdrible', nome: 'André', papel: 'cliente' },
    { nome_meet: 'Ana', nome: 'Ana', papel: '' },
  ]);
});

test('definir: grava nome+papel; nome igual ao do Meet e sem papel apaga; papel inválido vira vazio', () => {
  let m = Q.definir({}, 'fasterdrible', ' André ', 'cliente');
  assert.deepEqual(m, { fasterdrible: { nome: 'André', papel: 'cliente' } });
  m = Q.definir(m, 'fasterdrible', 'fasterdrible', '');
  assert.deepEqual(m, {});
  m = Q.definir({}, 'Ana', 'Ana Souza', 'chefe');
  assert.deepEqual(m, { Ana: { nome: 'Ana Souza', papel: '' } });
});

test('definir não altera o mapa recebido', () => {
  const original = { a: { nome: 'A', papel: 'cliente' } };
  Q.definir(original, 'b', 'B', 'outro');
  assert.deepEqual(original, { a: { nome: 'A', papel: 'cliente' } });
});

test('nomeDePessoa: recusa texto de ícone, o próprio vendedor e o código da reunião', () => {
  assert.equal(Q.nomeDePessoa('  André Silva '), 'André Silva');
  assert.equal(Q.nomeDePessoa('fasterdrible'), 'fasterdrible');
  assert.equal(Q.nomeDePessoa('more_vert'), null);
  assert.equal(Q.nomeDePessoa('keep'), null);
  assert.equal(Q.nomeDePessoa('Você'), null);
  assert.equal(Q.nomeDePessoa('Pedro (Você)'), null);
  assert.equal(Q.nomeDePessoa('tsv-mczn-usf'), null);
  assert.equal(Q.nomeDePessoa('A'), null);
  assert.equal(Q.nomeDePessoa('Reenquadrar'), null);  // botão do próprio quadro (teste real 16/10)
});

test('resumo da sidebar', () => {
  const mapa = { fasterdrible: { nome: 'André', papel: 'cliente' } };
  assert.equal(Q.resumo(mapa, ['fasterdrible', 'Ana'], 'Pedro'), 'Pedro (vendedor) · André (cliente) · Ana');
});
