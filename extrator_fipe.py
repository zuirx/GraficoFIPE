import json
import logging
import re
import sqlite3
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ============================================================
# CONFIGURAÇÃO
# ============================================================

DB_PATH = "fipe.db"

REQUEST_TIMEOUT = 220

# Quantidade de tentativas em caso de erro HTTP/rede
MAX_RETRIES = 50

# Tempo entre requisições para não sobrecarregar a API
REQUEST_DELAY = 0.5

# Tipos de veículos
TIPO_CARROS = 1
TIPO_MOTOS = 2
TIPO_CAMINHOES = 3


# ============================================================
# LOG
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logger = logging.getLogger("fipe")


# ============================================================
# BANCO DE DADOS
# ============================================================

class Database:

    def __init__(self, path=DB_PATH):
        self.path = path

        self.conn = sqlite3.connect(
            self.path,
            timeout=60,
        )

        self.conn.row_factory = sqlite3.Row

        # Melhor desempenho para muitas inserções.
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

        self.create_tables()

    # --------------------------------------------------------
    # SCHEMA
    # --------------------------------------------------------

    def create_tables(self):

        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS tabelas_fipe (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            codigo INTEGER NOT NULL UNIQUE,

            mes TEXT NOT NULL,

            criado_em TEXT NOT NULL
        );


        CREATE TABLE IF NOT EXISTS tipos_veiculo (
            id INTEGER PRIMARY KEY,

            nome TEXT NOT NULL
        );


        CREATE TABLE IF NOT EXISTS marcas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            tipo_veiculo_id INTEGER NOT NULL,

            codigo INTEGER NOT NULL,

            nome TEXT NOT NULL,

            UNIQUE (
                tipo_veiculo_id,
                codigo
            ),

            FOREIGN KEY (
                tipo_veiculo_id
            )
            REFERENCES tipos_veiculo(id)
        );


        CREATE TABLE IF NOT EXISTS modelos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            marca_id INTEGER NOT NULL,

            codigo INTEGER NOT NULL,

            nome TEXT NOT NULL,

            UNIQUE (
                marca_id,
                codigo
            ),

            FOREIGN KEY (
                marca_id
            )
            REFERENCES marcas(id)
        );


        CREATE TABLE IF NOT EXISTS versoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            modelo_id INTEGER NOT NULL,

            codigo_ano TEXT NOT NULL,

            ano_modelo INTEGER,

            codigo_combustivel INTEGER,

            descricao TEXT,

            UNIQUE (
                modelo_id,
                codigo_ano
            ),

            FOREIGN KEY (
                modelo_id
            )
            REFERENCES modelos(id)
        );


        CREATE TABLE IF NOT EXISTS valores_fipe (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            tabela_id INTEGER NOT NULL,

            versao_id INTEGER NOT NULL,

            codigo_fipe TEXT,

            marca TEXT,

            modelo TEXT,

            ano_modelo INTEGER,

            combustivel TEXT,

            valor REAL,

            mes TEXT,

            data_importacao TEXT NOT NULL,

            resposta_json TEXT,

            UNIQUE (
                tabela_id,
                versao_id
            ),

            FOREIGN KEY (
                tabela_id
            )
            REFERENCES tabelas_fipe(id),

            FOREIGN KEY (
                versao_id
            )
            REFERENCES versoes(id)
        );


        CREATE TABLE IF NOT EXISTS importacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            tabela_id INTEGER NOT NULL,

            tipo_veiculo_id INTEGER NOT NULL,

            status TEXT NOT NULL,

            iniciado_em TEXT NOT NULL,

            finalizado_em TEXT,

            erro TEXT,

            UNIQUE (
                tabela_id,
                tipo_veiculo_id
            ),

            FOREIGN KEY (
                tabela_id
            )
            REFERENCES tabelas_fipe(id)
        );


        CREATE INDEX IF NOT EXISTS idx_marcas_tipo
        ON marcas(tipo_veiculo_id);


        CREATE INDEX IF NOT EXISTS idx_modelos_marca
        ON modelos(marca_id);


        CREATE INDEX IF NOT EXISTS idx_versoes_modelo
        ON versoes(modelo_id);


        CREATE INDEX IF NOT EXISTS idx_valores_tabela
        ON valores_fipe(tabela_id);


        CREATE INDEX IF NOT EXISTS idx_valores_versao
        ON valores_fipe(versao_id);


        CREATE INDEX IF NOT EXISTS idx_valores_codigo_fipe
        ON valores_fipe(codigo_fipe);


        CREATE INDEX IF NOT EXISTS idx_valores_ano
        ON valores_fipe(ano_modelo);
        """)

        self.conn.executemany(
            """
            INSERT OR IGNORE INTO tipos_veiculo
                (id, nome)
            VALUES
                (?, ?)
            """,
            [
                (TIPO_CARROS, "Carros"),
                (TIPO_MOTOS, "Motos"),
                (TIPO_CAMINHOES, "Caminhões"),
            ],
        )

        self.conn.commit()

    # --------------------------------------------------------
    # TABELA FIPE
    # --------------------------------------------------------

    def salvar_tabela(self, codigo, mes):

        agora = datetime.now().isoformat()

        self.conn.execute(
            """
            INSERT INTO tabelas_fipe
                (codigo, mes, criado_em)
            VALUES
                (?, ?, ?)

            ON CONFLICT(codigo)
            DO UPDATE SET
                mes = excluded.mes
            """,
            (
                codigo,
                mes,
                agora,
            ),
        )

        self.conn.commit()

        row = self.conn.execute(
            """
            SELECT id
            FROM tabelas_fipe
            WHERE codigo = ?
            """,
            (codigo,),
        ).fetchone()

        return row["id"]

    # --------------------------------------------------------
    # MARCA
    # --------------------------------------------------------

    def salvar_marca(
        self,
        tipo_veiculo,
        codigo,
        nome,
    ):

        self.conn.execute(
            """
            INSERT INTO marcas
                (
                    tipo_veiculo_id,
                    codigo,
                    nome
                )
            VALUES
                (?, ?, ?)

            ON CONFLICT(
                tipo_veiculo_id,
                codigo
            )
            DO UPDATE SET
                nome = excluded.nome
            """,
            (
                tipo_veiculo,
                codigo,
                nome,
            ),
        )

        row = self.conn.execute(
            """
            SELECT id
            FROM marcas
            WHERE tipo_veiculo_id = ?
              AND codigo = ?
            """,
            (
                tipo_veiculo,
                codigo,
            ),
        ).fetchone()

        return row["id"]

    # --------------------------------------------------------
    # MODELO
    # --------------------------------------------------------

    def salvar_modelo(
        self,
        marca_id,
        codigo,
        nome,
    ):

        self.conn.execute(
            """
            INSERT INTO modelos
                (
                    marca_id,
                    codigo,
                    nome
                )
            VALUES
                (?, ?, ?)

            ON CONFLICT(
                marca_id,
                codigo
            )
            DO UPDATE SET
                nome = excluded.nome
            """,
            (
                marca_id,
                codigo,
                nome,
            ),
        )

        row = self.conn.execute(
            """
            SELECT id
            FROM modelos
            WHERE marca_id = ?
              AND codigo = ?
            """,
            (
                marca_id,
                codigo,
            ),
        ).fetchone()

        return row["id"]

    # --------------------------------------------------------
    # VERSÃO
    # --------------------------------------------------------

    def salvar_versao(
        self,
        modelo_id,
        codigo_ano,
        ano_modelo,
        codigo_combustivel,
        descricao,
    ):

        self.conn.execute(
            """
            INSERT INTO versoes
                (
                    modelo_id,
                    codigo_ano,
                    ano_modelo,
                    codigo_combustivel,
                    descricao
                )
            VALUES
                (?, ?, ?, ?, ?)

            ON CONFLICT(
                modelo_id,
                codigo_ano
            )
            DO UPDATE SET
                ano_modelo = excluded.ano_modelo,
                codigo_combustivel = excluded.codigo_combustivel,
                descricao = excluded.descricao
            """,
            (
                modelo_id,
                codigo_ano,
                ano_modelo,
                codigo_combustivel,
                descricao,
            ),
        )

        row = self.conn.execute(
            """
            SELECT id
            FROM versoes
            WHERE modelo_id = ?
              AND codigo_ano = ?
            """,
            (
                modelo_id,
                codigo_ano,
            ),
        ).fetchone()

        return row["id"]

    # --------------------------------------------------------
    # CACHE LOCAL (MARCAS, MODELOS E ANOS)
    # --------------------------------------------------------

    def obter_marcas_locais(self, tipo_veiculo):
        rows = self.conn.execute(
            """
            SELECT codigo, nome
            FROM marcas
            WHERE tipo_veiculo_id = ?
            """,
            (tipo_veiculo,)
        ).fetchall()
        return [{"Value": str(r["codigo"]), "Label": r["nome"]} for r in rows]

    def obter_modelos_locais(self, marca_id):
        rows = self.conn.execute(
            """
            SELECT codigo, nome
            FROM modelos
            WHERE marca_id = ?
            """,
            (marca_id,)
        ).fetchall()
        return [{"Value": str(r["codigo"]), "Label": r["nome"]} for r in rows]

    def obter_anos_locais(self, modelo_id):
        rows = self.conn.execute(
            """
            SELECT codigo_ano, descricao
            FROM versoes
            WHERE modelo_id = ?
            """,
            (modelo_id,)
        ).fetchall()
        return [{"Value": str(r["codigo_ano"]), "Label": r["descricao"]} for r in rows]

    # --------------------------------------------------------
    # VERIFICAR SE VALOR JÁ EXISTE
    # --------------------------------------------------------

    def valor_existe(
        self,
        tabela_id,
        versao_id,
    ):

        row = self.conn.execute(
            """
            SELECT 1
            FROM valores_fipe
            WHERE tabela_id = ?
              AND versao_id = ?
            LIMIT 1
            """,
            (
                tabela_id,
                versao_id,
            ),
        ).fetchone()

        return row is not None

    # --------------------------------------------------------
    # SALVAR VALOR
    # --------------------------------------------------------

    def salvar_valor(
        self,
        tabela_id,
        versao_id,
        resultado,
    ):

        valor = converter_valor(
            resultado.get("Valor")
        )

        codigo_fipe = resultado.get(
            "CodigoFipe"
        )

        marca = resultado.get(
            "Marca"
        )

        modelo = resultado.get(
            "Modelo"
        )

        ano_modelo = resultado.get(
            "AnoModelo"
        )

        combustivel = resultado.get(
            "Combustivel"
        )

        mes = resultado.get(
            "MesReferencia"
        )

        agora = datetime.now().isoformat()

        self.conn.execute(
            """
            INSERT INTO valores_fipe
                (
                    tabela_id,
                    versao_id,
                    codigo_fipe,
                    marca,
                    modelo,
                    ano_modelo,
                    combustivel,
                    valor,
                    mes,
                    data_importacao,
                    resposta_json
                )
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(
                tabela_id,
                versao_id
            )
            DO UPDATE SET

                codigo_fipe =
                    excluded.codigo_fipe,

                marca =
                    excluded.marca,

                modelo =
                    excluded.modelo,

                ano_modelo =
                    excluded.ano_modelo,

                combustivel =
                    excluded.combustivel,

                valor =
                    excluded.valor,

                mes =
                    excluded.mes,

                data_importacao =
                    excluded.data_importacao,

                resposta_json =
                    excluded.resposta_json
            """,
            (
                tabela_id,
                versao_id,
                codigo_fipe,
                marca,
                modelo,
                ano_modelo,
                combustivel,
                valor,
                mes,
                agora,
                json.dumps(
                    resultado,
                    ensure_ascii=False,
                ),
            ),
        )

    # --------------------------------------------------------
    # IMPORTAÇÃO
    # --------------------------------------------------------

    def obter_status_importacao(
        self,
        tabela_id,
        tipo_veiculo,
    ):

        return self.conn.execute(
            """
            SELECT *
            FROM importacoes
            WHERE tabela_id = ?
              AND tipo_veiculo_id = ?
            """,
            (
                tabela_id,
                tipo_veiculo,
            ),
        ).fetchone()

    def iniciar_importacao(
        self,
        tabela_id,
        tipo_veiculo,
    ):

        agora = datetime.now().isoformat()

        self.conn.execute(
            """
            INSERT INTO importacoes
                (
                    tabela_id,
                    tipo_veiculo_id,
                    status,
                    iniciado_em
                )
            VALUES
                (?, ?, ?, ?)

            ON CONFLICT(
                tabela_id,
                tipo_veiculo_id
            )
            DO UPDATE SET

                status = excluded.status,

                iniciado_em =
                    excluded.iniciado_em,

                finalizado_em = NULL,

                erro = NULL
            """,
            (
                tabela_id,
                tipo_veiculo,
                "em_andamento",
                agora,
            ),
        )

        self.conn.commit()

    def finalizar_importacao(
        self,
        tabela_id,
        tipo_veiculo,
        status="concluido",
        erro=None,
    ):

        self.conn.execute(
            """
            UPDATE importacoes
            SET
                status = ?,
                finalizado_em = ?,
                erro = ?
            WHERE tabela_id = ?
              AND tipo_veiculo_id = ?
            """,
            (
                status,
                datetime.now().isoformat(),
                erro,
                tabela_id,
                tipo_veiculo,
            ),
        )

        self.conn.commit()

    # --------------------------------------------------------

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


# ============================================================
# UTILITÁRIOS
# ============================================================

def converter_valor(valor) -> Optional[float]:

    if valor is None:
        return None

    if isinstance(valor, (int, float)):
        return float(valor)

    valor = str(valor)

    # Exemplo:
    # R$ 123.456,78

    valor = (
        valor
        .replace("R$", "")
        .replace(" ", "")
        .strip()
    )

    if not valor:
        return None

    # Formato brasileiro
    valor = valor.replace(".", "")
    valor = valor.replace(",", ".")

    try:
        return float(
            Decimal(valor)
        )
    except InvalidOperation:
        return None


def extrair_ano(codigo_ano):

    if not codigo_ano:
        return None

    match = re.match(
        r"^(\d{4})",
        str(codigo_ano),
    )

    if not match:
        return None

    return int(match.group(1))


# ============================================================
# CLIENTE FIPE
# ============================================================

class Fipe:

    BASE_URL = (
        "https://veiculos.fipe.org.br/api/veiculos"
    )

    TIPO_CARROS = 1
    TIPO_MOTOS = 2
    TIPO_CAMINHOES = 3

    def __init__(
        self,
        tipo_veiculo=TIPO_CARROS,
    ):

        self.tipo_veiculo = tipo_veiculo

        self.session = requests.Session()

        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/139.0 Safari/537.36"
            ),
            "Referer":
                "https://veiculos.fipe.org.br/",
            "Origin":
                "https://veiculos.fipe.org.br",
            "Content-Type":
                "application/json",
            "Accept":
                "application/json",
        })

        retry = Retry(
            total=MAX_RETRIES,

            connect=MAX_RETRIES,

            read=MAX_RETRIES,

            status=MAX_RETRIES,

            backoff_factor=1,

            status_forcelist=[
                500,
                502,
                503,
                504,
            ],

            allowed_methods=[
                "POST",
            ],

            respect_retry_after_header=True,
        )

        adapter = HTTPAdapter(
            max_retries=retry,
        )

        self.session.mount(
            "https://",
            adapter,
        )

        self.session.mount(
            "http://",
            adapter,
        )

        self.tabela = None

    # --------------------------------------------------------
    # POST
    # --------------------------------------------------------

    def _post(
        self,
        endpoint,
        data,
    ):

        url = (
            f"{self.BASE_URL}/{endpoint}"
        )

        while True:
            time.sleep(REQUEST_DELAY)

            try:
                response = self.session.post(
                    url,
                    json=data,
                    timeout=REQUEST_TIMEOUT,
                )

                response.raise_for_status()

                return response.json()
            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"Erro de requisição ({e}). Possível limite da API Fipe. "
                    "Aguardando 5 minutos antes de tentar novamente..."
                )
                time.sleep(300)

    # --------------------------------------------------------
    # TABELAS
    # --------------------------------------------------------

    def tabelas(self):

        return self._post(
            "ConsultarTabelaDeReferencia",
            {},
        )

    # --------------------------------------------------------

    def usar_tabela(
        self,
        codigo_tabela,
    ):

        self.tabela = codigo_tabela

    # --------------------------------------------------------

    def marcas(self):

        if self.tabela is None:
            raise RuntimeError(
                "Nenhuma tabela selecionada."
            )

        return self._post(
            "ConsultarMarcas",
            {
                "codigoTabelaReferencia":
                    self.tabela,

                "codigoTipoVeiculo":
                    self.tipo_veiculo,
            },
        )

    # --------------------------------------------------------

    def modelos(
        self,
        codigo_marca,
    ):

        return self._post(
            "ConsultarModelos",
            {
                "codigoTabelaReferencia":
                    self.tabela,

                "codigoTipoVeiculo":
                    self.tipo_veiculo,

                "codigoMarca":
                    codigo_marca,
            },
        )["Modelos"]

    # --------------------------------------------------------

    def anos(
        self,
        codigo_marca,
        codigo_modelo,
    ):

        return self._post(
            "ConsultarAnoModelo",
            {
                "codigoTabelaReferencia":
                    self.tabela,

                "codigoTipoVeiculo":
                    self.tipo_veiculo,

                "codigoMarca":
                    codigo_marca,

                "codigoModelo":
                    codigo_modelo,
            },
        )

    # --------------------------------------------------------

    def valor(
        self,
        codigo_marca,
        codigo_modelo,
        ano_combustivel,
    ):

        try:

            ano, combustivel = (
                ano_combustivel
                .split("-")
            )

        except ValueError:

            raise ValueError(
                f"Código de ano inválido: "
                f"{ano_combustivel}"
            )

        return self._post(
            "ConsultarValorComTodosParametros",
            {
                "codigoTabelaReferencia":
                    self.tabela,

                "codigoTipoVeiculo":
                    self.tipo_veiculo,

                "codigoMarca":
                    codigo_marca,

                "codigoModelo":
                    codigo_modelo,

                "ano":
                    ano_combustivel,

                "codigoTipoCombustivel":
                    int(combustivel),

                "anoModelo":
                    int(ano),

                "tipoConsulta":
                    "tradicional",

                "modeloCodigoExterno":
                    "",
            },
        )


# ============================================================
# IMPORTADOR
# ============================================================

class FipeImporter:

    def __init__(
        self,
        db_path=DB_PATH,
    ):

        self.db = Database(
            db_path
        )

    # --------------------------------------------------------
    # IMPORTAR TODAS AS COMPETÊNCIAS
    # --------------------------------------------------------

    def importar_tudo(self):

        fipe = Fipe()

        logger.info(
            "Consultando tabelas FIPE..."
        )

        tabelas_brutas = fipe.tabelas()

        meses_map = {
            "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, 
            "maio": 5, "junho": 6, "julho": 7, "agosto": 8, 
            "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12
        }

        tabelas = []
        for tabela in tabelas_brutas:
            try:
                nome_mes, ano_str = tabela["Mes"].split("/")
                ano = int(ano_str)
                mes_num = meses_map.get(nome_mes.lower().strip(), 0)
                
                # Filtra de janeiro de 2020 até setembro de 2026
                if ano < 2020 or ano > 2026:
                    continue
                if ano == 2026 and mes_num > 9:
                    continue
                    
                tabelas.append(tabela)
            except Exception:
                continue

        logger.info(
            "Encontradas %d competências (de Jan/2020 a Set/2026).",
            len(tabelas),
        )

        for tabela in tabelas:

            codigo_tabela = int(
                tabela["Codigo"]
            )

            mes = tabela["Mes"]

            logger.info(
                ""
            )

            logger.info(
                "======================================"
            )

            logger.info(
                "Competência: %s",
                mes,
            )

            logger.info(
                "Código: %s",
                codigo_tabela,
            )

            logger.info(
                "======================================"
            )

            tabela_id = (
                self.db.salvar_tabela(
                    codigo_tabela,
                    mes,
                )
            )

            for tipo in [
                Fipe.TIPO_CARROS,
                Fipe.TIPO_MOTOS,
                Fipe.TIPO_CAMINHOES,
            ]:

                self.importar_competencia(
                    codigo_tabela,
                    mes,
                    tabela_id,
                    tipo,
                )

    # --------------------------------------------------------
    # IMPORTAR UMA COMPETÊNCIA
    # --------------------------------------------------------

    def importar_competencia(
        self,
        codigo_tabela,
        mes,
        tabela_id,
        tipo_veiculo,
    ):

        nomes = {
            1: "CARROS",
            2: "MOTOS",
            3: "CAMINHÕES",
        }

        nome_tipo = nomes.get(
            tipo_veiculo,
            str(tipo_veiculo),
        )

        status = (
            self.db.obter_status_importacao(
                tabela_id,
                tipo_veiculo,
            )
        )

        # ----------------------------------------------------
        # IMPORTAÇÃO JÁ FINALIZADA
        # ----------------------------------------------------

        if (
            status
            and status["status"] == "concluido"
        ):

            logger.info(
                "[%s] Competência %s já importada. "
                "Pulando.",
                nome_tipo,
                mes,
            )

            return

        logger.info(
            "[%s] Importando competência %s...",
            nome_tipo,
            mes,
        )

        self.db.iniciar_importacao(
            tabela_id,
            tipo_veiculo,
        )

        fipe = Fipe(
            tipo_veiculo
        )

        fipe.usar_tabela(
            codigo_tabela
        )

        try:

            marcas = self.db.obter_marcas_locais(tipo_veiculo)
            if not marcas:
                marcas = fipe.marcas()

            logger.info(
                "[%s] %d marcas encontradas.",
                nome_tipo,
                len(marcas),
            )

            for indice_marca, marca in enumerate(
                marcas,
                start=1,
            ):

                try:

                    self.importar_marca(
                        fipe=fipe,
                        tabela_id=tabela_id,
                        tipo_veiculo=tipo_veiculo,
                        marca=marca,
                        numero_marca=indice_marca,
                        total_marcas=len(marcas),
                        mes=mes,
                    )

                except Exception as exc:

                    logger.exception(
                        "[%s] Erro na marca %s: %s",
                        nome_tipo,
                        marca.get("Label"),
                        exc,
                    )

                    # Continua para próxima marca
                    continue

            self.db.finalizar_importacao(
                tabela_id,
                tipo_veiculo,
                status="concluido",
            )

            logger.info(
                "[%s] Competência %s concluída.",
                nome_tipo,
                mes,
            )

        except Exception as exc:

            logger.exception(
                "[%s] Erro geral na competência %s",
                nome_tipo,
                mes,
            )

            self.db.finalizar_importacao(
                tabela_id,
                tipo_veiculo,
                status="erro",
                erro=str(exc),
            )

    # --------------------------------------------------------
    # MARCA
    # --------------------------------------------------------

    def importar_marca(
        self,
        fipe,
        tabela_id,
        tipo_veiculo,
        marca,
        numero_marca,
        total_marcas,
        mes,
    ):

        codigo_marca = int(
            marca["Value"]
        )

        nome_marca = marca["Label"]

        logger.info(
            "[%d/%d] Marca: %s",
            numero_marca,
            total_marcas,
            nome_marca,
        )

        marca_id = (
            self.db.salvar_marca(
                tipo_veiculo,
                codigo_marca,
                nome_marca,
            )
        )

        modelos = self.db.obter_modelos_locais(marca_id)
        if not modelos:
            modelos = fipe.modelos(
                codigo_marca
            )

        logger.info(
            "    %d modelos",
            len(modelos),
        )

        for modelo in modelos:

            try:

                self.importar_modelo(
                    fipe=fipe,
                    tabela_id=tabela_id,
                    marca_id=marca_id,
                    codigo_marca=codigo_marca,
                    modelo=modelo,
                    mes=mes,
                )

            except Exception as exc:

                logger.exception(
                    "Erro no modelo %s: %s",
                    modelo.get("Label"),
                    exc,
                )

                continue

        self.db.commit()

    # --------------------------------------------------------
    # MODELO
    # --------------------------------------------------------

    def importar_modelo(
        self,
        fipe,
        tabela_id,
        marca_id,
        codigo_marca,
        modelo,
        mes,
    ):

        codigo_modelo = int(
            modelo["Value"]
        )

        nome_modelo = modelo["Label"]

        logger.info(
            "Consultando -> Competência: %s | Modelo: %s",
            mes,
            nome_modelo,
        )

        modelo_id = (
            self.db.salvar_modelo(
                marca_id,
                codigo_modelo,
                nome_modelo,
            )
        )

        anos = self.db.obter_anos_locais(modelo_id)
        if not anos:
            anos = fipe.anos(
                codigo_marca,
                codigo_modelo,
            )

        for ano in anos:

            codigo_ano = str(
                ano["Value"]
            )

            descricao = ano.get(
                "Label"
            )

            ano_modelo = (
                extrair_ano(
                    codigo_ano
                )
            )

            codigo_combustivel = None

            try:

                partes = (
                    codigo_ano
                    .split("-")
                )

                if len(partes) >= 2:
                    codigo_combustivel = (
                        int(partes[1])
                    )

            except (
                ValueError,
                TypeError,
            ):
                pass

            versao_id = (
                self.db.salvar_versao(
                    modelo_id=modelo_id,

                    codigo_ano=codigo_ano,

                    ano_modelo=ano_modelo,

                    codigo_combustivel=(
                        codigo_combustivel
                    ),

                    descricao=descricao,
                )
            )

            # ------------------------------------------------
            # IMPORTAÇÃO INCREMENTAL
            # ------------------------------------------------

            if self.db.valor_existe(
                tabela_id,
                versao_id,
            ):

                continue

            try:

                resultado = fipe.valor(
                    codigo_marca,
                    codigo_modelo,
                    codigo_ano,
                )

                self.db.salvar_valor(
                    tabela_id,
                    versao_id,
                    resultado,
                )

            except Exception as exc:

                logger.warning(
                    "Falha ao consultar "
                    "%s / %s / %s: %s",
                    codigo_marca,
                    codigo_modelo,
                    codigo_ano,
                    exc,
                )

                continue

        self.db.commit()

    # --------------------------------------------------------

    def close(self):

        self.db.close()


# ============================================================
# MAIN
# ============================================================

def main():

    importer = FipeImporter(
        DB_PATH
    )

    try:

        importer.importar_tudo()

    except KeyboardInterrupt:

        logger.warning(
            "Importação interrompida pelo usuário."
        )

    finally:

        importer.close()


if __name__ == "__main__":
    main()