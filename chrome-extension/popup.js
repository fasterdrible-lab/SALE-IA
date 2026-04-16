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
    ['saleiaAtivo', 'saleiaBackendUrl', 'saleiaUltimasDicas', 'saleiaUltimaAtualizacao'],
    function (result) {
      // Toggle on/off
      toggleAtivo.checked = result.saleiaAtivo !== false;

      // URL do backend
      if (result.saleiaBackendUrl) {
        backendUrlInput.value = result.saleiaBackendUrl;
      }

      // Últimas dicas recebidas
      if (result.saleiaUltimasDicas) {
        exibirUltimasDicas(result.saleiaUltimasDicas, result.saleiaUltimaAtualizacao);
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

    function escaparHtml(str) {
      if (str == null) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    let html = '';
    if (dicas.proxima_acao) {
      html += '<div class="popup-dica"><span class="popup-dica-icon">💬</span>' + escaparHtml(dicas.proxima_acao) + '</div>';
    }
    if (dicas.perfil_disc && dicas.perfil_disc.tipo) {
      html += '<div class="popup-dica"><span class="popup-dica-icon">🎯</span>Perfil: <strong>' + escaparHtml(dicas.perfil_disc.tipo) + '</strong></div>';
    }
    if (dicas.sinal_financeiro) {
      html += '<div class="popup-dica"><span class="popup-dica-icon">💰</span>' + escaparHtml(dicas.sinal_financeiro) + '</div>';
    }
    if (timestamp) {
      html += '<div class="popup-dica-hora">Atualizado: ' + escaparHtml(new Date(timestamp).toLocaleTimeString('pt-BR')) + '</div>';
    }
    if (html) {
      ultimasDicas.innerHTML = html;
    }
  }

  // ─────────────────────────────────────────────
  // OUVIR ATUALIZAÇÕES DO STORAGE (novas dicas)
  // ─────────────────────────────────────────────
  chrome.storage.onChanged.addListener(function (changes) {
    if (changes.saleiaUltimasDicas) {
      exibirUltimasDicas(
        changes.saleiaUltimasDicas.newValue,
        changes.saleiaUltimaAtualizacao ? changes.saleiaUltimaAtualizacao.newValue : null
      );
    }
  });
});
