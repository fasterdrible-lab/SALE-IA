/**
 * popup.js — Lógica do popup da extensão SALEIA
 * Gerencia seleção de LLM e chaves de API por provedor
 */

/* ─────────────────────────────────────────────
   SELEÇÃO DE MODELO DE IA
───────────────────────────────────────────── */

// Ao clicar em uma opção de LLM, seleciona e mostra o campo de chave correspondente
document.querySelectorAll('.llm-option').forEach(option => {
  option.addEventListener('click', () => {
    // Remove seleção anterior
    document.querySelectorAll('.llm-option').forEach(o => o.classList.remove('selected'));
    option.classList.add('selected');

    const llm = option.dataset.llm;
    const provider = option.dataset.provider;

    // Mostra apenas o campo de chave do provedor selecionado
    document.querySelectorAll('.api-key-group').forEach(g => g.classList.add('hidden'));
    const keyGroup = document.getElementById(`key-${provider}`);
    if (keyGroup) keyGroup.classList.remove('hidden');

    // Persiste a seleção no storage local da extensão
    chrome.storage.local.set({ selectedLlm: llm, selectedProvider: provider }, () => {
      mostrarSalvo();
    });
  });
});

/* ─────────────────────────────────────────────
   SALVAR CHAVES DE API
───────────────────────────────────────────── */

// Salva a chave digitada ao sair do campo (evento change)
['openai', 'anthropic', 'google'].forEach(provider => {
  const input = document.getElementById(`input-${provider}-key`);
  if (!input) return;

  input.addEventListener('change', (e) => {
    const value = e.target.value.trim();

    // Não sobrescreve com o valor mascarado (••••)
    if (value.startsWith('••••••••')) return;

    const keys = {};
    keys[`apiKey_${provider}`] = value;

    chrome.storage.local.set(keys, () => {
      const status = document.getElementById(`status-${provider}`);
      if (status) status.textContent = value ? '✅' : '⚪';
      mostrarSalvo();
    });
  });
});

/* ─────────────────────────────────────────────
   CONFIGURAÇÃO DO BACKEND
───────────────────────────────────────────── */

// Salva a URL do backend ao sair do campo
const inputBackend = document.getElementById('input-backend-url');
if (inputBackend) {
  inputBackend.addEventListener('change', (e) => {
    const url = e.target.value.trim();
    chrome.storage.local.set({ saleliaBackendUrl: url }, () => {
      mostrarSalvo();
    });
  });
}

// Testa a conexão com o backend ao clicar em "Testar"
const btnTestar = document.getElementById('btn-test-backend');
if (btnTestar) {
  btnTestar.addEventListener('click', () => {
    const url = inputBackend ? inputBackend.value.trim() || 'http://localhost:8000' : 'http://localhost:8000';
    const statusEl = document.getElementById('backend-status');
    if (statusEl) statusEl.textContent = '⏳ Testando...';

    fetch(`${url}/health`)
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(() => {
        if (statusEl) statusEl.textContent = '✅ Conectado!';
      })
      .catch(() => {
        if (statusEl) statusEl.textContent = '❌ Sem conexão — verifique o servidor';
      });
  });
}

/* ─────────────────────────────────────────────
   CARREGAR CONFIGURAÇÕES SALVAS
───────────────────────────────────────────── */

chrome.storage.local.get(
  ['selectedLlm', 'selectedProvider', 'apiKey_openai', 'apiKey_anthropic', 'apiKey_google', 'saleliaBackendUrl'],
  (data) => {
    // Restaura modelo selecionado
    if (data.selectedLlm) {
      document.querySelectorAll('.llm-option').forEach(o => {
        o.classList.toggle('selected', o.dataset.llm === data.selectedLlm);
      });
    }

    // Mostra o campo de chave do provedor ativo
    const provider = data.selectedProvider || 'openai';
    document.querySelectorAll('.api-key-group').forEach(g => g.classList.add('hidden'));
    const keyGroup = document.getElementById(`key-${provider}`);
    if (keyGroup) keyGroup.classList.remove('hidden');

    // Exibe chaves mascaradas se já salvas
    if (data.apiKey_openai) {
      const el = document.getElementById('input-openai-key');
      if (el) el.value = '••••••••' + data.apiKey_openai.slice(-4);
      const st = document.getElementById('status-openai');
      if (st) st.textContent = '✅';
    }
    if (data.apiKey_anthropic) {
      const el = document.getElementById('input-anthropic-key');
      if (el) el.value = '••••••••' + data.apiKey_anthropic.slice(-4);
      const st = document.getElementById('status-anthropic');
      if (st) st.textContent = '✅';
    }
    if (data.apiKey_google) {
      const el = document.getElementById('input-google-key');
      if (el) el.value = '••••••••' + data.apiKey_google.slice(-4);
      const st = document.getElementById('status-google');
      if (st) st.textContent = '✅';
    }

    // Restaura URL do backend
    if (data.saleliaBackendUrl && inputBackend) {
      inputBackend.value = data.saleliaBackendUrl;
    }
  }
);

/* ─────────────────────────────────────────────
   HELPERS
───────────────────────────────────────────── */

// Exibe brevemente a mensagem de confirmação de salvamento
function mostrarSalvo() {
  const el = document.getElementById('save-status');
  if (!el) return;
  el.textContent = '✅ Salvo!';
  setTimeout(() => {
    el.textContent = '✅ Configurações salvas automaticamente';
  }, 1500);
}
