"""
Testes — Tarefa B7: cliente + oportunidade automáticos a partir da
recapitulação (agent/auto_opportunity_rules.py).

`agent.client_intelligence` é raw-pymysql (sem SQLite) — mockado por um
fake em memória; `Opportunity`/`MeetingMemory` usam SQLite real.

Run:
    python -m unittest tests.test_auto_opportunity_rules -v
"""
import logging
import os
import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

from agent.auto_opportunity_rules import (
    escolher_cliente_existente,
    estagio_da_reuniao,
    extrair_cliente_identificado,
    normalizar_nome,
    processar_cliente_e_oportunidade,
)

logging.disable(logging.CRITICAL)


def _resultado(nome="Ana Souza", empresa="Tacógrafos Brasil Ltda"):
    return {"titulo": "Reunião", "recapitulacao": {"cliente_identificado": {"nome": nome, "empresa": empresa}}}


class PurasTest(unittest.TestCase):
    def test_normalizar_remove_acento_pontuacao_e_sufixo(self):
        self.assertEqual(normalizar_nome("Tacógrafos Brasil LTDA."), "tacografos brasil")
        self.assertEqual(normalizar_nome("  Acme  S/A "), "acme")

    def test_extrair_valido(self):
        self.assertEqual(extrair_cliente_identificado(_resultado()["recapitulacao"]),
                         {"nome": "Ana Souza", "empresa": "Tacógrafos Brasil Ltda"})

    def test_extrair_descarta_placeholders_e_nulos(self):
        for bruto in ({"nome": "Cliente", "empresa": None}, {"nome": None, "empresa": "a empresa"},
                      {"nome": "nome do cliente ou null", "empresa": "empresa do cliente ou null"},
                      {"nome": "", "empresa": "  "}, None, "Ana"):
            self.assertIsNone(extrair_cliente_identificado({"cliente_identificado": bruto}), bruto)
        self.assertIsNone(extrair_cliente_identificado(None))

    def test_extrair_so_empresa(self):
        self.assertEqual(extrair_cliente_identificado({"cliente_identificado": {"nome": "Prospect", "empresa": "Acme"}}),
                         {"nome": None, "empresa": "Acme"})

    def test_escolher_por_empresa_normalizada(self):
        clientes = [{"id": "c1", "nome": "Outro", "empresa": "Beta"},
                    {"id": "c2", "nome": "Bruno", "empresa": "TACOGRAFOS BRASIL"}]
        self.assertEqual(escolher_cliente_existente(clientes, {"nome": "Ana", "empresa": "Tacógrafos Brasil Ltda"}), "c2")

    def test_empresas_diferentes_nunca_casam_mesmo_com_nome_igual(self):
        clientes = [{"id": "c1", "nome": "Ana Souza", "empresa": "Beta"}]
        self.assertIsNone(escolher_cliente_existente(clientes, {"nome": "Ana Souza", "empresa": "Acme"}))

    def test_sem_empresa_casa_por_nome(self):
        clientes = [{"id": "c1", "nome": "Ana  Souza", "empresa": ""}]
        self.assertEqual(escolher_cliente_existente(clientes, {"nome": "ana souza", "empresa": None}), "c1")

    def test_estagio_da_reuniao(self):
        self.assertEqual(estagio_da_reuniao({"current_diagnosis": '{"conversation_stage": "problema"}'}), "problema")
        self.assertEqual(estagio_da_reuniao({"current_diagnosis": {"conversation_stage": {"estagio": "implicacao"}}}), "implicacao")
        self.assertEqual(estagio_da_reuniao({"current_diagnosis": "json quebrado"}), "")
        self.assertEqual(estagio_da_reuniao(None), "")


class _FakeClientes:
    """Substituto em memória de agent.client_intelligence."""

    def __init__(self):
        self.clientes, self.vinculos = [], {}

    def criar_cliente(self, nome, empresa="", notas="", usuario_id=None, **_):
        cid = f"cli-{len(self.clientes) + 1}"
        self.clientes.insert(0, {"id": cid, "nome": nome, "empresa": empresa, "usuario_id": usuario_id})
        return cid

    def listar_clientes(self, busca="", limit=50, usuario_id=None, **_):
        b = busca.lower()
        return [c for c in self.clientes
                if (b in (c["nome"] or "").lower() or b in (c["empresa"] or "").lower())
                and (usuario_id is None or c["usuario_id"] in (usuario_id, None))][:limit]

    def vincular_reuniao(self, client_id, meeting_id, titulo="", **_):
        self.vinculos[meeting_id] = client_id
        return True

    def buscar_cliente_por_reuniao(self, meeting_id):
        return self.vinculos.get(meeting_id)


class OrquestracaoTest(unittest.TestCase):
    def setUp(self):
        import api.database as database

        self.db = database
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)
        for p in (patch.object(database, "engine", engine), patch.dict(os.environ, {"AUTO_OPPORTUNITY_ENABLED": "true"})):
            p.start()
            self.addCleanup(p.stop)
        self.fake = _FakeClientes()
        for nome in ("criar_cliente", "listar_clientes", "vincular_reuniao", "buscar_cliente_por_reuniao"):
            p = patch(f"agent.client_intelligence.{nome}", getattr(self.fake, nome))
            p.start()
            self.addCleanup(p.stop)

    def test_reuniao_com_dono_cria_cliente_oportunidade_e_vincula(self):
        self.db.registrar_transcricao_meeting("m1", "Cliente: fala suficiente para criar a memoria", usuario_id="vend-1")
        r = processar_cliente_e_oportunidade(_resultado(), "m1", "Reunião 1")
        self.assertEqual(r["status"], "ok")
        self.assertTrue(r["cliente_criado"] and r["opportunity_criada"])
        opp = self.db.obter_opportunity(r["opportunity_id"])
        self.assertEqual((opp["seller_id"], opp["client_id"], opp["status"]), ("vend-1", r["client_id"], "open"))
        self.assertEqual(self.db.obter_meeting_memory("m1")["opportunity_id"], r["opportunity_id"])
        self.assertEqual(self.fake.vinculos["m1"], r["client_id"])

    def test_segunda_reuniao_reaproveita_cliente_e_oportunidade(self):
        r1 = processar_cliente_e_oportunidade(_resultado(), "manual_1", usuario_id_requisicao="vend-1")
        r2 = processar_cliente_e_oportunidade(_resultado(nome="Carlos", empresa="TACOGRAFOS BRASIL"),
                                              "manual_2", usuario_id_requisicao="vend-1")
        self.assertEqual(r2["client_id"], r1["client_id"])
        self.assertEqual(r2["opportunity_id"], r1["opportunity_id"])
        self.assertFalse(r2["cliente_criado"] or r2["opportunity_criada"])
        self.assertEqual(len(self.db.listar_opportunities()), 1)

    def test_recap_manual_sem_meeting_memory_usa_usuario_autenticado(self):
        r = processar_cliente_e_oportunidade(_resultado(), "manual_20260924", usuario_id_requisicao="vend-2")
        self.assertEqual(r["status"], "ok")
        self.assertEqual(self.db.obter_opportunity(r["opportunity_id"])["seller_id"], "vend-2")

    def test_dono_da_meeting_tem_prioridade_sobre_quem_gerou(self):
        self.db.registrar_transcricao_meeting("m1", "Cliente: fala suficiente para criar a memoria", usuario_id="vend-1")
        r = processar_cliente_e_oportunidade(_resultado(), "m1", usuario_id_requisicao="admin-9")
        self.assertEqual(self.db.obter_opportunity(r["opportunity_id"])["seller_id"], "vend-1")

    def test_reuniao_anonima_nunca_casa_com_cliente_de_outro_vendedor(self):
        outro = self.fake.criar_cliente("Ana Souza", "Tacógrafos Brasil Ltda", usuario_id="vend-1")
        r = processar_cliente_e_oportunidade(_resultado(), "anon-2")
        self.assertNotEqual(r["client_id"], outro)
        self.assertTrue(r["cliente_criado"])

    def test_sem_dono_cria_so_cliente_nunca_oportunidade(self):
        self.db.registrar_transcricao_meeting("anon", "Cliente: fala suficiente para criar a memoria")
        r = processar_cliente_e_oportunidade(_resultado(), "anon")
        self.assertEqual(r["status"], "cliente_sem_dono")
        self.assertIsNotNone(r["client_id"])
        self.assertEqual(self.db.listar_opportunities(), [])

    def test_sem_cliente_identificado_nao_faz_nada(self):
        r = processar_cliente_e_oportunidade(_resultado(nome=None, empresa="Cliente"), "m1", usuario_id_requisicao="v")
        self.assertEqual(r["status"], "sem_cliente_identificado")
        self.assertEqual(self.fake.clientes, [])

    def test_duas_oportunidades_abertas_nao_escolhe(self):
        cid = self.fake.criar_cliente("Ana", "Acme", usuario_id="vend-1")
        self.db.criar_opportunity(client_id=cid, seller_id="vend-1")
        self.db.criar_opportunity(client_id=cid, seller_id="vend-1")
        r = processar_cliente_e_oportunidade(_resultado(nome="Ana", empresa="Acme"), "manual_x", usuario_id_requisicao="vend-1")
        self.assertEqual(r["status"], "oportunidade_ambigua")
        self.assertEqual(len(self.db.listar_opportunities()), 2)

    def test_kill_switch(self):
        with patch.dict(os.environ, {"AUTO_OPPORTUNITY_ENABLED": "false"}):
            r = processar_cliente_e_oportunidade(_resultado(), "m1", usuario_id_requisicao="v")
        self.assertEqual(r["status"], "desligado")
        self.assertEqual(self.fake.clientes, [])

    def test_falha_interna_nunca_lanca(self):
        with patch("agent.client_intelligence.criar_cliente", side_effect=RuntimeError("mysql fora")):
            r = processar_cliente_e_oportunidade(_resultado(), "m1", usuario_id_requisicao="v")
        self.assertEqual(r["status"], "erro")


if __name__ == "__main__":
    unittest.main()
