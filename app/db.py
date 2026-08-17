# db.py
# ALTERADO EM: 14/08/2026 às 17:48 -03

from contextlib import contextmanager
import re
from typing import Any

import mysql.connector

from .config import settings


print(
    "DB.PY CARREGADO:",
    __file__,
    flush=True,
)


_IDENTIFIER = re.compile(
    r"^[^\W\d][\w-]*$",
    re.UNICODE,
)

_TABLE_IDENTIFIER = re.compile(
    r"^[A-Za-z0-9_-]+$"
)


@contextmanager
def connection(
    database: str | None = None,
):
    conn = mysql.connector.connect(
        host=settings.db_servername,
        port=settings.db_port,
        database=(
            database
            or settings.db_name_destino
        ),
        user=settings.db_username,
        password=settings.db_password,
    )

    try:
        yield conn
    finally:
        conn.close()


def validar_nome_tabela(
    nome: str,
) -> str:
    nome = str(nome).strip()

    if not nome.startswith("tb_prod_"):
        raise ValueError(
            "A tabela deve começar com tb_prod_."
        )

    if len(nome) > 64:
        raise ValueError(
            "O nome da tabela é muito grande."
        )

    if not _TABLE_IDENTIFIER.fullmatch(nome):
        raise ValueError(
            "Nome de tabela inválido."
        )

    return nome


def validar_nome_origem(
    nome: str,
) -> str:
    nome = str(nome).strip()

    if not nome:
        raise ValueError(
            "Nome da tabela de origem vazio."
        )

    if len(nome) > 64:
        raise ValueError(
            "O nome da tabela de origem é muito grande."
        )

    if not _TABLE_IDENTIFIER.fullmatch(nome):
        raise ValueError(
            f"Nome da tabela de origem inválido: {nome}"
        )

    return nome


def validar_coluna(
    nome: str,
) -> str:
    if not isinstance(nome, str):
        raise ValueError(
            "Nome de coluna inválido."
        )

    nome = nome.strip()

    if not nome:
        raise ValueError(
            "Nome de coluna vazio."
        )

    if len(nome) > 64:
        raise ValueError(
            f"Nome de coluna muito grande: {nome}"
        )

    if not _IDENTIFIER.fullmatch(nome):
        raise ValueError(
            f"Nome de coluna inválido: {nome}"
        )

    return nome


def proteger_tabela(
    nome: str,
) -> str:
    return f"`{validar_nome_tabela(nome)}`"


def proteger_coluna(
    nome: str,
) -> str:
    return f"`{validar_coluna(nome)}`"


def tabela_tem_coluna(
    cursor,
    tabela: str,
    coluna: str,
) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
          AND column_name = %s
        """,
        (
            settings.db_name_destino,
            tabela,
            coluna,
        ),
    )

    row = cursor.fetchone()

    return bool(
        row
        and row[0] > 0
    )


def tabela_origem_tem_coluna(
    cursor,
    tabela: str,
    coluna: str,
) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
          AND column_name = %s
        """,
        (
            settings.db_name_origem,
            tabela,
            coluna,
        ),
    )

    row = cursor.fetchone()

    return bool(
        row
        and row[0] > 0
    )


def table_exists(
    nome_tabela: str,
) -> bool:
    nome_tabela = validar_nome_tabela(
        nome_tabela
    )

    sql = """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = %s
          AND table_name = %s
    """

    with connection(
        settings.db_name_destino
    ) as conn:
        cursor = conn.cursor()

        try:
            cursor.execute(
                sql,
                (
                    settings.db_name_destino,
                    nome_tabela,
                ),
            )

            row = cursor.fetchone()

            return bool(
                row
                and row[0] == 1
            )

        finally:
            cursor.close()


def source_table_exists(
    nome_tabela: str,
) -> bool:
    nome_tabela = validar_nome_origem(
        nome_tabela
    )

    sql = """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = %s
          AND table_name = %s
    """

    with connection(
        settings.db_name_origem
    ) as conn:
        cursor = conn.cursor()

        try:
            cursor.execute(
                sql,
                (
                    settings.db_name_origem,
                    nome_tabela,
                ),
            )

            row = cursor.fetchone()

            return bool(
                row
                and row[0] == 1
            )

        finally:
            cursor.close()


def criar_definicao_tabela(
    columns: list[dict[str, Any]],
) -> str:
    if not columns:
        raise ValueError(
            "Nenhuma coluna informada."
        )

    definitions: list[str] = []
    primary_keys: list[str] = []
    indexes: list[str] = []
    index_names: set[str] = set()
    column_names: set[str] = set()

    allowed_types = re.compile(
        r"^(TINYINT|SMALLINT|MEDIUMINT|INT|"
        r"INTEGER|BIGINT|DECIMAL|NUMERIC|"
        r"FLOAT|DOUBLE|CHAR|VARCHAR|TEXT|"
        r"TINYTEXT|MEDIUMTEXT|LONGTEXT|"
        r"DATE|DATETIME|TIMESTAMP|TIME|"
        r"YEAR|JSON|BLOB|MEDIUMBLOB|LONGBLOB)"
        r"(?:\([0-9, ]+\))?$",
        re.IGNORECASE,
    )

    numeric_types = (
        "TINYINT",
        "SMALLINT",
        "MEDIUMINT",
        "INT",
        "INTEGER",
        "BIGINT",
    )

    for column in columns:
        if not isinstance(
            column,
            dict,
        ):
            raise ValueError(
                "Cada coluna deve ser um objeto JSON."
            )

        name = str(
            column.get("nome", "")
        ).strip()

        data_type = str(
            column.get("tipo", "")
        ).strip().upper()

        validar_coluna(name)

        if name in column_names:
            raise ValueError(
                f"Coluna duplicada: {name}"
            )

        if not allowed_types.fullmatch(
            data_type
        ):
            raise ValueError(
                f"Tipo de coluna inválido: {data_type}"
            )

        column_names.add(name)

        nullable = (
            "NULL"
            if column.get(
                "nulo",
                True,
            )
            else "NOT NULL"
        )

        default_sql = ""

        if "padrao" in column:
            value = column["padrao"]

            if value is None:
                default_sql = (
                    " DEFAULT NULL"
                )

            elif isinstance(
                value,
                bool,
            ):
                default_sql = (
                    " DEFAULT "
                    + (
                        "1"
                        if value
                        else "0"
                    )
                )

            elif isinstance(
                value,
                (int, float),
            ):
                default_sql = (
                    f" DEFAULT {value}"
                )

            else:
                escaped_value = (
                    str(value)
                    .replace(
                        "'",
                        "''",
                    )
                )

                default_sql = (
                    " DEFAULT "
                    f"'{escaped_value}'"
                )

        auto_increment_sql = ""

        if column.get(
            "auto_increment",
            False,
        ):
            if not data_type.startswith(
                numeric_types
            ):
                raise ValueError(
                    (
                        "AUTO_INCREMENT só pode "
                        "ser usado em coluna numérica: "
                        f"{name}"
                    )
                )

            auto_increment_sql = (
                " AUTO_INCREMENT"
            )

        definitions.append(
            (
                f"{proteger_coluna(name)} "
                f"{data_type}"
                f"{auto_increment_sql} "
                f"{nullable}"
                f"{default_sql}"
            )
        )

        if column.get(
            "chave_primaria",
            False,
        ):
            primary_keys.append(
                proteger_coluna(name)
            )

        if column.get(
            "indice",
            False,
        ):
            base_name = re.sub(
                r"[^A-Za-z0-9_]",
                "_",
                name,
            )[:35]

            index_name = f"idx_{base_name}"
            counter = 2

            while index_name in index_names:
                index_name = (
                    f"idx_{base_name}_{counter}"
                )
                counter += 1

            index_names.add(index_name)

            indexes.append(
                (
                    f"INDEX `{index_name}` "
                    f"({proteger_coluna(name)})"
                )
            )

    if "texto_busca" not in column_names:
        definitions.append(
            "`texto_busca` TEXT NULL"
        )

    if not primary_keys:
        raise ValueError(
            "Informe pelo menos uma chave primária."
        )

    definitions.append(
        (
            "PRIMARY KEY ("
            + ", ".join(primary_keys)
            + ")"
        )
    )

    definitions.extend(indexes)

    definitions.append(
        (
            "FULLTEXT KEY "
            "`ft_texto_busca` "
            "(`texto_busca`)"
        )
    )

    return ", ".join(
        definitions
    )


def montar_sql_criacao(
    tabela: str,
    columns: list[dict[str, Any]],
) -> str:
    tabela = validar_nome_tabela(
        tabela
    )

    definicoes = criar_definicao_tabela(
        columns
    )

    return f"""
        CREATE TABLE IF NOT EXISTS
        `{settings.db_name_destino}`.`{tabela}` (
            {definicoes}
        )
        ENGINE=InnoDB
        DEFAULT CHARACTER SET utf8mb4
        COLLATE=utf8mb4_unicode_ci
    """


def indice_fulltext_existe(
    cursor,
    tabela: str,
) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.statistics
        WHERE table_schema = %s
          AND table_name = %s
          AND index_name = 'ft_texto_busca'
          AND index_type = 'FULLTEXT'
          AND column_name = 'texto_busca'
        """,
        (
            settings.db_name_destino,
            tabela,
        ),
    )

    row = cursor.fetchone()

    return bool(
        row
        and row[0] > 0
    )


def garantir_colunas_sistema(
    conn,
    cursor,
    tabela: str,
) -> None:
    if not tabela_tem_coluna(
        cursor,
        tabela,
        "texto_busca",
    ):
        cursor.execute(
            f"""
            ALTER TABLE
            `{settings.db_name_destino}`.`{tabela}`
            ADD COLUMN
            `texto_busca` TEXT NULL
            """
        )

    conn.commit()


def garantir_indice_fulltext(
    conn,
    cursor,
    tabela: str,
) -> None:
    if indice_fulltext_existe(
        cursor,
        tabela,
    ):
        return

    cursor.execute(
        f"""
        ALTER TABLE
        `{settings.db_name_destino}`.`{tabela}`
        ADD FULLTEXT KEY
        `ft_texto_busca`
        (`texto_busca`)
        """
    )

    conn.commit()


def create_table(
    table_name: str,
    columns: list[dict[str, Any]],
) -> dict[str, Any]:
    table_name = validar_nome_tabela(
        table_name
    )

    sql = montar_sql_criacao(
        table_name,
        columns,
    )

    with connection(
        settings.db_name_destino
    ) as conn:
        cursor = conn.cursor()

        try:
            cursor.execute(sql)

            garantir_colunas_sistema(
                conn,
                cursor,
                table_name,
            )

            garantir_indice_fulltext(
                conn,
                cursor,
                table_name,
            )

            conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            cursor.close()

    return {
        "tabela": table_name,
        "criada": True,
        "fulltext": True,
    }


def montar_colunas_populacao(
    mapeamento: dict[str, str],
) -> list[dict[str, Any]]:
    columns: list[dict[str, Any]] = []

    for coluna_destino in mapeamento:
        nome = coluna_destino.strip()

        if nome == "CodigoDoProduto":
            tipo = "INT"
            nulo = False

        elif nome.upper() == "ATIVO":
            tipo = "TINYINT"
            nulo = True

        elif nome == "UnidadesEmEstoque":
            tipo = "INT"
            nulo = True

        else:
            tipo = "TEXT"
            nulo = True

        columns.append(
            {
                "nome": nome,
                "tipo": tipo,
                "nulo": nulo,
                "chave_primaria": (
                    nome
                    == "CodigoDoProduto"
                ),
            }
        )

    columns.append(
        {
            "nome": "texto_busca",
            "tipo": "TEXT",
            "nulo": True,
        }
    )

    return columns


def populate_table(
    tabela_destino: str,
    tabela_origem: str,
    mapeamento: dict[str, str],
    campos_busca: list[str],
) -> dict[str, Any]:
    destino = validar_nome_tabela(
        tabela_destino
    )

    origem = validar_nome_origem(
        tabela_origem
    )

    if not mapeamento:
        raise ValueError(
            "Mapeamento vazio."
        )

    if not source_table_exists(origem):
        raise ValueError(
            (
                "A tabela de origem não existe: "
                f"{origem}"
            )
        )

    colunas_destino = list(
        mapeamento.keys()
    )

    colunas_origem = list(
        mapeamento.values()
    )

    for coluna in colunas_destino:
        validar_coluna(coluna)

    for coluna in colunas_origem:
        validar_coluna(coluna)

    campos_busca = [
        validar_coluna(coluna)
        for coluna in campos_busca
    ]

    if "texto_busca" in colunas_destino:
        raise ValueError(
            "Não inclua texto_busca no mapeamento."
        )

    if "CodigoDoProduto" not in colunas_destino:
        raise ValueError(
            (
                "O mapeamento precisa conter "
                "CodigoDoProduto."
            )
        )

    with connection(
        settings.db_name_origem
    ) as conn_origem:
        cursor_origem = (
            conn_origem.cursor()
        )

        try:
            for coluna in colunas_origem:
                if not tabela_origem_tem_coluna(
                    cursor_origem,
                    origem,
                    coluna,
                ):
                    raise ValueError(
                        (
                            "A coluna de origem não existe: "
                            f"{coluna}"
                        )
                    )
        finally:
            cursor_origem.close()

    columns = montar_colunas_populacao(
        mapeamento
    )

    create_sql = montar_sql_criacao(
        destino,
        columns,
    )

    colunas_insert = (
        colunas_destino
        + ["texto_busca"]
    )

    insert_sql = ", ".join(
        proteger_coluna(coluna)
        for coluna in colunas_insert
    )

    select_sql = ", ".join(
        f"p.{proteger_coluna(coluna)}"
        for coluna in colunas_origem
    )

    campos_texto = (
        campos_busca
        if campos_busca
        else colunas_origem
    )

    texto_busca_sql = (
        "CONCAT_WS(' ', "
        + ", ".join(
            f"p.{proteger_coluna(coluna)}"
            for coluna in campos_texto
        )
        + ")"
    )

    select_sql += (
        f", {texto_busca_sql}"
    )

    update_columns = [
        coluna
        for coluna in colunas_insert
        if coluna
        != "CodigoDoProduto"
    ]

    update_sql = ", ".join(
        (
            f"{proteger_coluna(coluna)} = "
            f"VALUES({proteger_coluna(coluna)})"
        )
        for coluna in update_columns
    )

    origem_tem_nome = False

    with connection(
        settings.db_name_origem
    ) as conn_origem:
        cursor_origem = (
            conn_origem.cursor()
        )

        try:
            origem_tem_nome = (
                tabela_origem_tem_coluna(
                    cursor_origem,
                    origem,
                    "NomeDoProduto",
                )
            )
        finally:
            cursor_origem.close()

    filtro_nome = ""

    if origem_tem_nome:
        filtro_nome = """
            WHERE p.`NomeDoProduto` IS NOT NULL
              AND TRIM(p.`NomeDoProduto`) <> ''
        """

    populate_sql = f"""
        INSERT INTO
        `{settings.db_name_destino}`.`{destino}` (
            {insert_sql}
        )
        SELECT
            {select_sql}
        FROM
        `{settings.db_name_origem}`.`{origem}` AS p
        {filtro_nome}
        ON DUPLICATE KEY UPDATE
            {update_sql}
    """

    with connection(
        settings.db_name_destino
    ) as conn:
        cursor = conn.cursor()

        try:
            cursor.execute(create_sql)

            garantir_colunas_sistema(
                conn,
                cursor,
                destino,
            )

            garantir_indice_fulltext(
                conn,
                cursor,
                destino,
            )

            cursor.execute(
                populate_sql
            )

            afetados = cursor.rowcount

            conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            cursor.close()

    return {
        "banco_origem": settings.db_name_origem,
        "tabela_origem": origem,
        "banco_destino": settings.db_name_destino,
        "tabela_destino": destino,
        "colunas_destino": colunas_destino,
        "colunas_origem": colunas_origem,
        "afetados": afetados,
    }


def search_table(
    nome_tabela: str,
    consulta: str,
    limite: int,
) -> list[dict[str, Any]]:
    tabela = validar_nome_tabela(
        nome_tabela
    )

    consulta = str(
        consulta
    ).strip()

    if not consulta:
        raise ValueError(
            "Consulta vazia."
        )

    limite = max(
        1,
        min(
            int(limite),
            settings.max_search_results,
        ),
    )

    termos = [
        parte.strip()
        for parte in consulta.split()
        if parte.strip()
    ]

    if not termos:
        raise ValueError(
            "Consulta sem termos válidos."
        )

    filtros = []
    parametros: list[Any] = []

    for termo in termos:
        padrao = f"%{termo}%"

        filtros.append(
            """
            (
                `texto_busca` LIKE %s
                OR `NomeDoProduto` LIKE %s
                OR CAST(
                    `CodigoDoProduto`
                    AS CHAR
                ) LIKE %s
            )
            """
        )

        parametros.extend(
            [
                padrao,
                padrao,
                padrao,
            ]
        )

    where_termos = " AND ".join(
        filtros
    )

    sql = f"""
        SELECT
            *
        FROM
        `{settings.db_name_destino}`.`{tabela}`
        WHERE
            {where_termos}
        ORDER BY
            `NomeDoProduto` ASC
        LIMIT %s
    """

    parametros.append(
        limite
    )

    with connection(
        settings.db_name_destino
    ) as conn:
        cursor = conn.cursor(
            dictionary=True
        )

        try:
            cursor.execute(
                sql,
                tuple(parametros),
            )

            return cursor.fetchall()

        finally:
            cursor.close()