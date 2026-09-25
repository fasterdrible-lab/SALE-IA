"""Tarefa B7 de `docs/tasks-prompt-mestre-v2-restante.md` — cliente e
oportunidade criados automaticamente a partir da recapitulação.

Achado da B1 (24/09/2026): produção tinha 0 `client_profiles`, 0
`client_meetings` e 0 `opportunities` — a cadeia reunião → cliente →
oportunidade só existia se alguém clicasse no dashboard, e ninguém
clicava. Sem isso Win/Loss, Seasonality e o Learning Loop não têm dado.

Decisão confirmada com o usuário: a identificação vem da própria
recapitulação (`PROMPT_RECAPITULACAO` ganhou `cliente_identificado`,
mesma chamada de IA, sem custo extra). Regras:

- Só age com nome/empresa **explicitamente ditos** na conversa (o prompt
  proíbe inferir; aqui ainda descartamos placeholders tipo "Cliente").
- Casa com cliente existente do mesmo dono (empresa normalizada, ou nome
  normalizado quando não há empresa) antes de criar — evita duplicar o
  mesmo cliente a cada reunião.
- Oportunidade só nasce quando há dono real (vendedor): o dono da
  `MeetingMemory` ou, na recapitulação manual do dashboard (que não tem
  `MeetingMemory`), o usuário autenticado que gerou a recapitulação.
  Sem dono → só cliente + vínculo, nunca `seller_id` inventado.
- Nunca cria 2ª oportunidade: com 1 aberta, reaproveita; com 2+, não
  escolhe (mesma regra de ambiguidade da Tarefa 3.1).
- Kill-switch `AUTO_OPPORTUNITY_ENABLED` (default `true`). Melhor
  esforço: nunca lança, nunca afeta a resposta da recapitulação.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from typing import Optional

logger = logging.getLogger("saleia.auto_opportunity")

_PLACEHOLDERS = {
    "cliente", "o cliente", "a cliente", "prospect", "lead", "nao informado", "não informado",
    "desconhecido", "n/a", "na", "null", "none", "-", "empresa", "a empresa", "participante",
    # texto de exemplo do schema no PROMPT_RECAPITULACAO, caso a IA o copie
    "nome do cliente ou null", "empresa do cliente ou null",
}
_MAX_CANDIDATOS = 500
_SUFIXOS_EMPRESA = re.compile(r"\b(ltda|me|epp|eireli|s\/?a|sa|inc|llc)\.?$")


def auto_opportunity_habilitado() -> bool:
    return os.getenv("AUTO_OPPORTUNITY_ENABLED", "true").strip().lower() != "false"


def normalizar_nome(valor) -> str:
    texto = unicodedata.normalize("NFD", str(valor or "")).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^\w\s/]", " ", texto.lower())
    texto = re.sub(r"\s+", " ", texto).strip()
    return _SUFIXOS_EMPRESA.sub("", texto).strip()


def _texto_valido(valor) -> Optional[str]:
    if not isinstance(valor, str):
        return None
    limpo = re.sub(r"\s+", " ", valor).strip()
    if len(limpo) < 2 or len(limpo) > 120:
        return None
    if normalizar_nome(limpo) in {normalizar_nome(p) for p in _PLACEHOLDERS}:
        return None
    return limpo


def extrair_cliente_identificado(recapitulacao) -> Optional[dict]:
    """`{"nome", "empresa"}` com ao menos um dos dois válido, ou `None`."""
    if not isinstance(recapitulacao, dict):
        return None
    bruto = recapitulacao.get("cliente_identificado")
    if not isinstance(bruto, dict):
        return None
    nome = _texto_valido(bruto.get("nome"))
    empresa = _texto_valido(bruto.get("empresa"))
    if not nome and not empresa:
        return None
    return {"nome": nome, "empresa": empresa}


def escolher_cliente_existente(clientes: list, identificado: dict) -> Optional[str]:
    """Pura. `clientes` em ordem de preferência (mais recente primeiro).
    Empresa igual (normalizada) casa; sem empresa dos dois lados, casa
    por nome. Empresas diferentes nunca casam, mesmo com nome igual."""
    emp = normalizar_nome(identificado.get("empresa"))
    nome = normalizar_nome(identificado.get("nome"))
    for c in clientes:
        c_emp = normalizar_nome(c.get("empresa"))
        c_nome = normalizar_nome(c.get("nome"))
        if emp and c_emp:
            if emp == c_emp:
                return c["id"]
            continue
        if nome and c_nome and nome == c_nome:
            return c["id"]
        if emp and not c_emp and c_nome == emp:
            return c["id"]
    return None


def estagio_da_reuniao(memoria: Optional[dict]) -> str:
    """Estágio SPIN mais recente do diagnóstico em tempo real, se houver
    (string livre, mesma decisão de `Opportunity.stage` da Fase 2)."""
    if not memoria:
        return ""
    diag = memoria.get("current_diagnosis")
    if isinstance(diag, str):
        try:
            diag = json.loads(diag) if diag.strip() else {}
        except Exception:
            diag = {}
    estagio = (diag or {}).get("conversation_stage") if isinstance(diag, dict) else None
    if isinstance(estagio, dict):
        estagio = estagio.get("estagio") or estagio.get("stage") or estagio.get("atual")
    return str(estagio).strip()[:60] if isinstance(estagio, str) else ""


def processar_cliente_e_oportunidade(
    resultado: dict,
    meeting_id: str,
    titulo: Optional[str] = None,
    usuario_id_requisicao: Optional[str] = None,
) -> dict:
    """Orquestra a B7 após uma recapitulação. Retorna um resumo do que
    fez (`status`, `client_id`, `opportunity_id`, flags de criação)."""
    resumo = {"status": "desligado", "client_id": None, "opportunity_id": None,
              "cliente_criado": False, "opportunity_criada": False}
    try:
        if not auto_opportunity_habilitado():
            return resumo
        identificado = extrair_cliente_identificado((resultado or {}).get("recapitulacao"))
        if not identificado:
            resumo["status"] = "sem_cliente_identificado"
            return resumo

        from agent.client_intelligence import (
            buscar_cliente_por_reuniao, criar_cliente, listar_clientes, vincular_reuniao,
        )
        from api.database import (
            criar_opportunity, listar_opportunities, obter_meeting_memory, vincular_meeting_opportunity,
        )

        memoria = obter_meeting_memory(meeting_id) if meeting_id else None
        dono = (memoria or {}).get("usuario_id") or usuario_id_requisicao

        client_id = buscar_cliente_por_reuniao(meeting_id)
        if not client_id:
            # Compara em Python (normalizado), nunca via LIKE — acento/caixa
            # no LIKE dependem da collation. Sem dono, só clientes sem dono
            # (nunca liga reunião anônima a cliente de outro vendedor).
            candidatos = listar_clientes(limit=_MAX_CANDIDATOS, usuario_id=dono)
            if not dono:
                candidatos = [c for c in candidatos if not c.get("usuario_id")]
            client_id = escolher_cliente_existente(candidatos, identificado)
        if not client_id:
            client_id = criar_cliente(
                nome=identificado.get("nome") or identificado.get("empresa"),
                empresa=identificado.get("empresa") or "",
                notas="Criado automaticamente a partir da recapitulação (Tarefa B7).",
                usuario_id=dono,
            )
            resumo["cliente_criado"] = True
        resumo["client_id"] = client_id
        vincular_reuniao(client_id=client_id, meeting_id=meeting_id,
                         titulo=titulo or (resultado or {}).get("titulo") or "")

        if not dono:
            resumo["status"] = "cliente_sem_dono"
            return resumo

        abertas = listar_opportunities(client_id=client_id, status="open")
        if len(abertas) > 1:
            resumo["status"] = "oportunidade_ambigua"
            return resumo
        if abertas:
            opportunity_id = abertas[0]["id"]
        else:
            opportunity_id = criar_opportunity(
                client_id=client_id, seller_id=dono, stage=estagio_da_reuniao(memoria),
            )["id"]
            resumo["opportunity_criada"] = True
        resumo["opportunity_id"] = opportunity_id
        if memoria and not memoria.get("opportunity_id"):
            vincular_meeting_opportunity(meeting_id, opportunity_id)
        resumo["status"] = "ok"
        logger.info("[B7] meeting=%s cliente=%s (novo=%s) opportunity=%s (nova=%s)",
                    meeting_id, client_id, resumo["cliente_criado"], opportunity_id, resumo["opportunity_criada"])
        return resumo
    except Exception as e:
        logger.warning("[B7] Falha ao criar cliente/oportunidade automaticamente (melhor esforço): %s", e)
        resumo["status"] = "erro"
        return resumo
