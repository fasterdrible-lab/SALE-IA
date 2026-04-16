/**
 * SALEIA — popup.js
 * Controles do popup da extensão Chrome.
 */

'use strict';

document.addEventListener('DOMContentLoaded', function () {
  const toggleAtivo = document.getElementById('toggle-ativo');
  const backendUrlInput = document.getElementById('backend-url');
  const btnSalvarUrl = document.getElementById('btn-salvar-url');
  const urlFeedback = document.getElementById('url-feedback');
  const statusTexto = document.getElementById('status-texto');
  const statusEl = document.getElementById('popup-status');
  const ultimasDicas = document.getElementById('ultimas-dicas');
  const btnRelatorio = document.getElementById('btn-relatorio');

  // ─────────────────────────────────────────────
  // CARREGAR CONFIGURAÇÕES SALVAS
  // ─────────────────────────────────────────────
  chrome.storage.local.get(
    ['saleliaAtivo', 'saleliaBackendUrl', 'saleliaUltimasDicas', 'saleliaUltimaAtualizacao'],
    function (result) {
      // Toggle on/off
      toggleAtivo.checked = result.saleliaAtivo !== false;

      // URL do backend
      if (result.saleliaBackendUrl) {
        backendUrlInput.value = result.saleliaBackendUrl;
      }

      // Últimas dicas recebidas
      if (result.saleliaUltimasDicas) {
        exibirUltimasDicas(result.saleliaUltimasDicas, result.saleliaUltimaAtualizacao);
      }
    }
  );

  // ─────────────────────────────────────────────
  // VERIFICAR SE HÁ ABA DO MEET ATIVA
  // ─────────────────────────────────────────────
  chrome.tabs.query({ url: 'https://meet.google.com/*' }, function (tabs) {
    if (tabs && tabs.length > 0) {
      statusTexto.textContent = 'Monitorando reunião...';
      statusEl.classList.remove('popup-status-aguardando');
      statusEl.classList.add('popup-status-ativo');
    } else {
      statusTexto.textContent = 'Aguardando Google Meet...';
    }
  });

  // ─────────────────────────────────────────────
  // TOGGLE ATIVAR/DESATIVAR
  // ─────────────────────────────────────────────
  toggleAtivo.addEventListener('change', function () {
    const novoValor = toggleAtivo.checked;
    chrome.runtime.sendMessage({ tipo: 'setAtivo', valor: novoValor }, function () {
      statusTexto.textContent = novoValor ? 'Monitorando reunião...' : 'Pausado pelo usuário';
    });
  });

  // ─────────────────────────────────────────────
  // SALVAR URL DO BACKEND
  // ─────────────────────────────────────────────
  btnSalvarUrl.addEventListener('click', function () {
    const url = backendUrlInput.value.trim().replace(/\/$/, '');
    if (!url) return;

    chrome.runtime.sendMessage({ tipo: 'setBackendUrl', valor: url }, function () {
      mostrarFeedback('✅ URL salva com sucesso!', 'success');
    });
  });

  // ─────────────────────────────────────────────
  // BOTÃO VER RELATÓRIO COMPLETO
  // ─────────────────────────────────────────────
  btnRelatorio.addEventListener('click', function (e) {
    e.preventDefault();
    const url = backendUrlInput.value.trim().replace(/\/$/, '') + '/relatorio';
    chrome.tabs.create({ url: url });
  });

  // ─────────────────────────────────────────────
  // FUNÇÕES AUXILIARES
  // ─────────────────────────────────────────────
  function mostrarFeedback(mensagem, tipo) {
    urlFeedback.textContent = mensagem;
    urlFeedback.style.display = 'block';
    urlFeedback.className = 'popup-feedback popup-feedback-' + tipo;
    setTimeout(function () {
      urlFeedback.style.display = 'none';
    }, 3000);
  }

  function exibirUltimasDicas(dicas, timestamp) {
    if (!dicas) return;
    let html = '';
    if (dicas.proxima_acao) {
      html += '<div class="popup-dica"><span class="popup-dica-icon">💬</span>' + dicas.proxima_acao + '</div>';
    }
    if (dicas.perfil_disc && dicas.perfil_disc.tipo) {
      html += '<div class="popup-dica"><span class="popup-dica-icon">🎯</span>Perfil: <strong>' + dicas.perfil_disc.tipo + '</strong></div>';
    }
    if (dicas.sinal_financeiro) {
      html += '<div class="popup-dica"><span class="popup-dica-icon">💰</span>' + dicas.sinal_financeiro + '</div>';
    }
    if (timestamp) {
      html += '<div class="popup-dica-hora">Atualizado: ' + new Date(timestamp).toLocaleTimeString('pt-BR') + '</div>';
    }
    if (html) {
      ultimasDicas.innerHTML = html;
    }
  }

  // ─────────────────────────────────────────────
  // OUVIR ATUALIZAÇÕES DO STORAGE (novas dicas)
  // ─────────────────────────────────────────────
  chrome.storage.onChanged.addListener(function (changes) {
    if (changes.saleliaUltimasDicas) {
      exibirUltimasDicas(
        changes.saleliaUltimasDicas.newValue,
        changes.saleliaUltimaAtualizacao ? changes.saleliaUltimaAtualizacao.newValue : null
      );
    }
  });
});
