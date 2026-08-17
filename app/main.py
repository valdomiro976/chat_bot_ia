# main.py
# ALTERADO EM: 14/08/2026 às 17:28 -03

import re
from typing import Any

import mysql.connector

from fastapi import FastAPI
from fastapi import HTTPException

from pydantic import BaseModel
from pydantic import Field

from .ai import gerar_resposta
from .ai import interpretar_pesquisa
from .config import settings
from .db import populate_table
from .db import search_table
from .db import table_exists


app = FastAPI(
    title="Chatbot IA MySQL",
    version="1.0.0",
)


class CreateTableRequest(BaseModel):
    tabela: str
    colunas: list[dict[str, Any]]


class PopulateRequest(BaseModel):
    tabela_destino: str
    tabela_origem: str
    mapeamento: dict[str, str]
    campos_busca: list[str] = Field(
        default_factory=list
    )


class ChatRequest(BaseModel):
    tabela: str
    message: str
    system_prompt: str = ""
    ferramentas_prompt: str = ""
    history: list[dict[str, str]] = Field(
        default_factory=list
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
    )


def validar_nome_tabela_criacao(
    nome: str,
) -> str:
    nome = str(nome).strip()

    if not re.fullmatch(
        r"^tb_prod_[A-Za-z0-9_-]+$",
        nome,
    ):
        raise ValueError(
            (
                "Nome de tabela inválido. "
                "Use tb_prod_[CNPJ]-[APLICATIVO]."
            )
        )

    if len(nome) > 64:
        raise ValueError(
            "O nome da tabela é muito grande."
        )

    return nome


def validar_nome_coluna_criacao(
    nome: str,
) -> str:
    nome = str(nome).strip()

    if not nome:
        raise ValueError(
            "Nome de coluna vazio."
        )

    if len(nome) > 64:
        raise ValueError(
            f"Nome de coluna muito grande: {nome}"
        )

    if not re.fullmatch(
        r"^[^\W\d][\w-]*$",
        nome,
        re.UNICODE,
    ):
        raise ValueError(
            f"Nome de coluna inválido: {nome}"
        )

    return nome


def criar_tabela_destino(
    nome_tabela: str,
    colunas: list[dict[str, Any]],
) -> dict[str, Any]:
    nome_tabela = validar_nome_tabela_criacao(
        nome_tabela
    )

    if not colunas:
        raise ValueError(
            "Nenhuma coluna informada."
        )

    tipos_permitidos = re.compile(
        r"^(TINYINT|SMALLINT|MEDIUMINT|INT|"
        r"INTEGER|BIGINT|DECIMAL|NUMERIC|"
        r"FLOAT|DOUBLE|CHAR|VARCHAR|TEXT|"
        r"TINYTEXT|MEDIUMTEXT|LONGTEXT|"
        r"DATE|DATETIME|TIMESTAMP|TIME|"
        r"YEAR|JSON|BLOB|MEDIUMBLOB|LONGBLOB)"
        r"(?:\([0-9, ]+\))?$",
        re.IGNORECASE,
    )

    definicoes: list[str] = []
    nomes: set[str] = set()
    chave_primaria: str | None = None

    for coluna in colunas:
        if not isinstance(coluna, dict):
            raise ValueError(
                "Cada coluna deve ser um objeto JSON."
            )

        nome = validar_nome_coluna_criacao(
            coluna.get("nome", "")
        )

        tipo = str(
            coluna.get("tipo", "")
        ).strip().upper()

        if not tipos_permitidos.fullmatch(
            tipo
        ):
            raise ValueError(
                f"Tipo de coluna inválido: {tipo}"
            )

        if nome in nomes:
            raise ValueError(
                f"Coluna duplicada: {nome}"
            )

        nomes.add(nome)

        nulo = (
            "NULL"
            if coluna.get("nulo", True)
            else "NOT NULL"
        )

        padrao = ""

        if "padrao" in coluna:
            valor = coluna["padrao"]

            if valor is None:
                padrao = " DEFAULT NULL"

            elif isinstance(valor, bool):
                padrao = (
                    " DEFAULT "
                    + ("1" if valor else "0")
                )

            elif isinstance(valor, (int, float)):
                padrao = (
                    f" DEFAULT {valor}"
                )

            else:
                valor_sql = (
                    str(valor)
                    .replace("'", "''")
                )

                padrao = (
                    f" DEFAULT '{valor_sql}'"
                )

        auto_increment = ""

        if coluna.get(
            "auto_increment",
            False,
        ):
            tipos_numericos = (
                "TINYINT",
                "SMALLINT",
                "MEDIUMINT",
                "INT",
                "INTEGER",
                "BIGINT",
            )

            if not tipo.startswith(
                tipos_numericos
            ):
                raise ValueError(
                    (
                        "AUTO_INCREMENT só pode "
                        "ser usado em coluna numérica: "
                        f"{nome}"
                    )
                )

            auto_increment = (
                " AUTO_INCREMENT"
            )

        definicoes.append(
            (
                f"`{nome}` {tipo} "
                f"{auto_increment} "
                f"{nulo}"
                f"{padrao}"
            )
        )

        if coluna.get(
            "chave_primaria",
            False,
        ):
            if chave_primaria is not None:
                raise ValueError(
                    "Informe somente uma chave primária."
                )

            chave_primaria = nome

    if "texto_busca" not in nomes:
        definicoes.append(
            "`texto_busca` TEXT NULL"
        )
        nomes.add("texto_busca")

    if chave_primaria is None:
        raise ValueError(
            "Informe uma chave primária."
        )

    definicoes.append(
        f"PRIMARY KEY (`{chave_primaria}`)"
    )

    indices: set[str] = set()

    for coluna in colunas:
        if not coluna.get(
            "indice",
            False,
        ):
            continue

        nome = validar_nome_coluna_criacao(
            coluna.get("nome", "")
        )

        base = re.sub(
            r"[^A-Za-z0-9_]",
            "_",
            nome,
        )[:40]

        indice = f"idx_{base}"
        contador = 2

        while indice in indices:
            indice = f"idx_{base}_{contador}"
            contador += 1

        indices.add(indice)

        definicoes.append(
            f"INDEX `{indice}` (`{nome}`)"
        )

    definicoes.append(
        (
            "FULLTEXT KEY "
            "`ft_texto_busca` "
            "(`texto_busca`)"
        )
    )

    sql_create = f"""
        CREATE TABLE IF NOT EXISTS
        `{settings.db_name_destino}`.`{nome_tabela}` (
            {", ".join(definicoes)}
        )
        ENGINE=InnoDB
        DEFAULT CHARACTER SET utf8mb4
        COLLATE=utf8mb4_unicode_ci
    """

    print(
        "=== SQL CREATE REAL ===",
        flush=True,
    )
    print(
        sql_create,
        flush=True,
    )
    print(
        "=== FIM SQL CREATE REAL ===",
        flush=True,
    )

    conn = mysql.connector.connect(
        host=settings.db_servername,
        port=settings.db_port,
        database=settings.db_name_destino,
        user=settings.db_username,
        password=settings.db_password,
    )

    cursor = conn.cursor()

    try:
        cursor.execute(sql_create)
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()

    return {
        "tabela": nome_tabela,
        "colunas": sorted(nomes),
        "criada": True,
        "fulltext": True,
    }


def normalizar_consultas(
    filtros: Any,
) -> list[str]:
    if not isinstance(
        filtros,
        dict,
    ):
        return []

    consultas = filtros.get(
        "consultas"
    )

    if isinstance(
        consultas,
        str,
    ):
        consultas = [
            consultas
        ]

    if isinstance(
        consultas,
        list,
    ):
        resultado: list[str] = []

        for item in consultas:
            if isinstance(
                item,
                dict,
            ):
                item = (
                    item.get("consulta")
                    or item.get("categoria")
                    or item.get("tipo")
                    or ""
                )

            texto = str(
                item
            ).strip()

            if (
                texto
                and texto not in resultado
            ):
                resultado.append(texto)

        if resultado:
            return resultado

    consulta = filtros.get(
        "consulta"
    )

    if isinstance(
        consulta,
        list,
    ):
        resultado = [
            str(item).strip()
            for item in consulta
            if str(item).strip()
        ]

        if resultado:
            return resultado

    if consulta is not None:
        texto = str(
            consulta
        ).strip()

        if texto:
            return [texto]

    categoria = filtros.get(
        "categoria"
    )

    if categoria is not None:
        texto = str(
            categoria
        ).strip()

        if texto:
            return [texto]

    tipo = filtros.get(
        "tipo"
    )

    if tipo is not None:
        texto = str(
            tipo
        ).strip()

        if texto:
            return [texto]

    return []


def pesquisar_consultas(
    tabela: str,
    consultas: list[str],
    limite: int,
) -> list[dict[str, Any]]:
    encontrados: dict[
        str,
        dict[str, Any],
    ] = {}

    for consulta in consultas:
        registros = search_table(
            nome_tabela=tabela,
            consulta=consulta,
            limite=limite,
        )

        for registro in registros:
            codigo = registro.get(
                "CodigoDoProduto"
            )

            chave = str(
                codigo
                if codigo is not None
                else len(encontrados)
            )

            encontrados[chave] = registro

    return list(
        encontrados.values()
    )[:limite]


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
    }


@app.post("/api/v1/tabela/criar")
def criar_tabela(
    request: CreateTableRequest,
) -> dict[str, Any]:
    try:
        resultado = criar_tabela_destino(
            nome_tabela=request.tabela,
            colunas=request.colunas,
        )

        return {
            "sucesso": True,
            "mensagem": "Tabela criada com sucesso.",
            "resultado": resultado,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao criar tabela: {exc}",
        ) from exc


@app.post("/api/v1/tabela/popular")
def popular_tabela(
    request: PopulateRequest,
) -> dict[str, Any]:
    try:
        resultado = populate_table(
            tabela_destino=request.tabela_destino,
            tabela_origem=request.tabela_origem,
            mapeamento=request.mapeamento,
            campos_busca=request.campos_busca,
        )

        return {
            "sucesso": True,
            "resultado": resultado,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao popular tabela: {exc}",
        ) from exc


@app.get(
    "/api/v1/tabela/{tabela}/existe"
)
def verificar_tabela(
    tabela: str,
) -> dict[str, Any]:
    try:
        existe = table_exists(tabela)

        return {
            "sucesso": True,
            "tabela": tabela,
            "existe": existe,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao verificar tabela: {exc}",
        ) from exc


@app.post("/api/v1/chat")
def conversar(
    request: ChatRequest,
) -> dict[str, Any]:
    try:
        if not table_exists(request.tabela):
            raise HTTPException(
                status_code=404,
                detail=(
                    f"A tabela '{request.tabela}' "
                    "não foi encontrada."
                ),
            )

        filtros = interpretar_pesquisa(
            message=request.message,
            history=request.history,
            system_prompt=request.system_prompt,
            ferramentas_prompt=request.ferramentas_prompt,
        )

        if not isinstance(
            filtros,
            dict,
        ):
            filtros = {}

        if filtros.get(
            "precisa_esclarecimento",
            False,
        ):
            pergunta = filtros.get(
                "pergunta"
            ) or "Pode informar mais detalhes?"

            return {
                "sucesso": True,
                "answer": pergunta,
                "filters": filtros,
                "items": [],
            }

        consultas = normalizar_consultas(
            filtros=filtros,
        )

        if not consultas:
            return {
                "sucesso": False,
                "answer": (
                    "Não consegui identificar "
                    "a categoria do produto "
                    "pesquisado."
                ),
                "filters": filtros,
                "items": [],
            }

        filtros["consultas"] = consultas

        registros = pesquisar_consultas(
            tabela=request.tabela,
            consultas=consultas,
            limite=request.limit,
        )

        resposta = gerar_resposta(
            message=request.message,
            filtros=filtros,
            registros=registros,
            system_prompt=request.system_prompt,
            ferramentas_prompt=request.ferramentas_prompt,
        )

        return {
            "sucesso": True,
            "answer": resposta,
            "filters": filtros,
            "items": registros,
        }

    except HTTPException:
        raise

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Erro no chatbot: {exc}",
        ) from exc