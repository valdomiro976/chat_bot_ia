# ai.py
# ALTERADO EM: 14/08/2026 às 17:21 -03

import json
import re
import unicodedata
from typing import Any

from groq import Groq

from .config import settings


client = Groq(
    api_key=settings.groq_api_key
)


SYSTEM_INTERPRETACAO = """
Você interpreta pesquisas de produtos.

Não faça SQL.
Não consulte a internet.
Não invente produtos.
Não invente preços.
Não invente estoque.

REGRA PRINCIPAL:
A consulta deve conter somente a categoria ou o tipo
genérico do produto.

Nunca coloque na consulta:
- marca;
- modelo;
- código;
- tamanho;
- peso;
- capacidade;
- embalagem;
- número;
- nome específico;
- característica específica.

Exemplos obrigatórios:

Mensagem:
"Tem gás P13?"
Retorno:
{
  "consulta": "gás",
  "precisa_esclarecimento": false,
  "pergunta": null
}

Mensagem:
"Tem gás 13K?"
Retorno:
{
  "consulta": "gás",
  "precisa_esclarecimento": false,
  "pergunta": null
}

Mensagem:
"Que tipo de gás você tem?"
Retorno:
{
  "consulta": "gás",
  "precisa_esclarecimento": false,
  "pergunta": null
}

Mensagem:
"Quais gases estão disponíveis?"
Retorno:
{
  "consulta": "gás",
  "precisa_esclarecimento": false,
  "pergunta": null
}

Se a mensagem tiver uma categoria de produto,
use somente essa categoria.

Se houver marca, código, modelo, peso,
capacidade ou número junto da categoria,
ignore todos esses detalhes.

Exemplos:

"água mineral 500 ml" -> "água"
"botijão de gás P13" -> "gás"
"gás GLP 13 kg" -> "gás"
"cerveja lata 350 ml" -> "cerveja"
"arroz tipo 1 5 kg" -> "arroz"

A consulta deve ser curta, genérica e adequada
para localizar todos os produtos da categoria.

Retorne somente um objeto JSON válido.

Se a pesquisa estiver clara:

{
  "consulta": "categoria genérica",
  "precisa_esclarecimento": false,
  "pergunta": null
}

Se não houver nenhuma categoria de produto:

{
  "consulta": "",
  "precisa_esclarecimento": true,
  "pergunta": "Qual produto você deseja consultar?"
}

Nunca coloque mensagem de produto não encontrado
no campo pergunta.

Nunca coloque a palavra JSON dentro de pergunta.
Nunca escreva texto fora do objeto JSON.
"""


def texto_seguro(
    valor: Any,
) -> str:
    if valor is None:
        return ""

    return str(valor).strip()


def remover_acentos(
    valor: str,
) -> str:
    texto = unicodedata.normalize(
        "NFKD",
        valor,
    )

    return "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(
            caractere
        )
    )


def categoria_de_fallback(
    mensagem: str,
) -> str:
    texto = remover_acentos(
        texto_seguro(mensagem)
    ).lower()

    categorias = [
        (
            r"\b("
            r"gas|gases|botijao|"
            r"glp|p13|13k"
            r")\b",
            "gás",
        ),
        (
            r"\b(agua|aguas)\b",
            "água",
        ),
        (
            r"\b(cerveja|cervejas)\b",
            "cerveja",
        ),
        (
            r"\b(refrigerante|"
            r"refrigerantes)\b",
            "refrigerante",
        ),
        (
            r"\b(arroz)\b",
            "arroz",
        ),
        (
            r"\b(feijao|feijoes)\b",
            "feijão",
        ),
        (
            r"\b(oleo|oleos)\b",
            "óleo",
        ),
        (
            r"\b(acucar|acucares)\b",
            "açúcar",
        ),
        (
            r"\b(leite|leites)\b",
            "leite",
        ),
        (
            r"\b(cafe|cafes)\b",
            "café",
        ),
    ]

    for padrao, categoria in categorias:
        if re.search(
            padrao,
            texto,
        ):
            return categoria

    palavras = re.findall(
        r"[a-zA-ZÀ-ÿ]+",
        texto,
    )

    palavras_ignoradas = {
        "tem",
        "tenho",
        "temos",
        "voce",
        "voces",
        "qual",
        "quais",
        "que",
        "tipo",
        "tipos",
        "produto",
        "produtos",
        "disponivel",
        "disponiveis",
        "estoque",
        "vende",
        "vendem",
        "venda",
        "quero",
        "preciso",
        "me",
        "de",
        "do",
        "da",
        "dos",
        "das",
        "um",
        "uma",
        "o",
        "a",
        "os",
        "as",
        "por",
        "favor",
        "temos",
    }

    candidatos = [
        palavra
        for palavra in palavras
        if palavra not in palavras_ignoradas
        and len(palavra) > 2
    ]

    if candidatos:
        return candidatos[0]

    return ""


def converter_booleano(
    valor: Any,
) -> bool:
    if isinstance(valor, bool):
        return valor

    if isinstance(valor, str):
        return valor.strip().lower() in {
            "true",
            "1",
            "sim",
            "yes",
        }

    if isinstance(valor, (int, float)):
        return valor != 0

    return False


def montar_prompt_sistema(
    prompt_cliente: str,
    prompt_ferramentas: str,
    prompt_padrao: str,
    exigir_json: bool = False,
) -> str:
    partes: list[str] = []

    cliente = texto_seguro(
        prompt_cliente
    )

    ferramentas = texto_seguro(
        prompt_ferramentas
    )

    padrao = texto_seguro(
        prompt_padrao
    )

    if cliente:
        partes.append(cliente)
    elif padrao:
        partes.append(padrao)

    if ferramentas:
        partes.append(ferramentas)

    if exigir_json:
        partes.append(
            """
A resposta deve ser exclusivamente
um objeto JSON válido.

O objeto deve conter exatamente:
- consulta;
- precisa_esclarecimento;
- pergunta.

A consulta deve conter somente
a categoria genérica do produto.

Nunca inclua marca, modelo,
código, peso, medida, capacidade
ou número na consulta.

Quando precisa_esclarecimento for false,
pergunta deve ser null.

Não escreva texto fora do JSON.
"""
        )
    else:
        partes.append(
            """
Você está na etapa final da resposta.

Retorne somente uma mensagem normal
para o cliente, em português.

Não retorne JSON.
Não retorne filtros.
Não retorne consulta.
Não retorne precisa_esclarecimento.
Não retorne pergunta.
Não retorne markdown.
Não escreva "Aguarde... processando".
"""
        )

    return "\n\n".join(
        partes
    ).strip()


def extrair_json_resposta(
    conteudo: str,
    mensagem_original: str = "",
) -> dict[str, Any]:
    texto = texto_seguro(
        conteudo
    )

    if not texto:
        raise ValueError(
            "A IA retornou uma resposta vazia."
        )

    if texto.startswith("```"):
        linhas = texto.splitlines()

        if linhas:
            linhas = linhas[1:]

        if (
            linhas
            and linhas[-1].strip()
            == "```"
        ):
            linhas = linhas[:-1]

        texto = "\n".join(
            linhas
        ).strip()

    inicio = texto.find("{")
    fim = texto.rfind("}")

    resultado: dict[str, Any] = {}

    if inicio >= 0 and fim > inicio:
        texto_json = texto[
            inicio: fim + 1
        ]

        try:
            valor_json = json.loads(
                texto_json
            )

        except json.JSONDecodeError as exc:
            raise ValueError(
                (
                    "A IA retornou JSON inválido: "
                    f"{exc}. "
                    f"Resposta: {texto_json[:500]}"
                )
            ) from exc

        if not isinstance(
            valor_json,
            dict,
        ):
            raise ValueError(
                "A resposta da IA não é um objeto JSON."
            )

        resultado = valor_json

    consulta = texto_seguro(
        resultado.get(
            "consulta",
            "",
        )
    )

    consulta = categoria_de_fallback(
        consulta
    ) or categoria_de_fallback(
        mensagem_original
    )

    precisa = converter_booleano(
        resultado.get(
            "precisa_esclarecimento",
            False,
        )
    )

    pergunta = None

    if precisa and not consulta:
        pergunta = texto_seguro(
            resultado.get(
                "pergunta"
            )
        ) or (
            "Qual produto você deseja consultar?"
        )

    if consulta:
        precisa = False
        pergunta = None

    return {
        "consulta": consulta,
        "precisa_esclarecimento": precisa,
        "pergunta": pergunta,
    }


def interpretar_pesquisa(
    message: str,
    history: list[dict[str, str]],
    system_prompt: str = "",
    ferramentas_prompt: str = "",
) -> dict[str, Any]:
    mensagem = texto_seguro(
        message
    )

    if not mensagem:
        raise ValueError(
            "A mensagem de pesquisa está vazia."
        )

    prompt_sistema = montar_prompt_sistema(
        prompt_cliente=system_prompt,
        prompt_ferramentas=ferramentas_prompt,
        prompt_padrao=SYSTEM_INTERPRETACAO,
        exigir_json=True,
    )

    mensagens: list[dict[str, str]] = [
        {
            "role": "system",
            "content": prompt_sistema,
        }
    ]

    for item in history[-8:]:
        if not isinstance(
            item,
            dict,
        ):
            continue

        role = item.get(
            "role"
        )

        content = texto_seguro(
            item.get("content")
        )

        if role in {
            "user",
            "assistant",
        } and content:
            mensagens.append(
                {
                    "role": role,
                    "content": content,
                }
            )

    mensagens.append(
        {
            "role": "user",
            "content": mensagem,
        }
    )

    resposta = client.chat.completions.create(
        model=settings.groq_model,
        messages=mensagens,
        temperature=0,
        response_format={
            "type": "json_object"
        },
    )

    conteudo = (
        resposta.choices[0]
        .message
        .content
        or ""
    )

    return extrair_json_resposta(
        conteudo=conteudo,
        mensagem_original=mensagem,
    )


def gerar_resposta(
    message: str,
    filtros: dict[str, Any],
    registros: list[dict[str, Any]],
    system_prompt: str = "",
    ferramentas_prompt: str = "",
) -> str:
    prompt_padrao = """
Você é o atendente final de uma loja.

Sua resposta será exibida diretamente
ao cliente no WhatsApp.

Analise somente os registros recebidos.
Não invente produtos.
Não invente preços.
Não invente estoque.
Não invente informações.

Quando a consulta for uma categoria,
como "gás", apresente os tipos, modelos,
capacidades ou descrições diferentes
existentes nos registros.

Não diga que não encontrou o produto
se houver registros da categoria.

Se não houver registros, diga claramente
que não foram encontrados produtos
da categoria consultada.

Se houver registros, apresente somente
os produtos e dados presentes nos registros.

Responda em português, com clareza,
de forma comercial e objetiva.

Nunca retorne JSON.
Nunca retorne filtros internos.
Nunca retorne a estrutura de interpretação.
"""

    prompt_sistema = montar_prompt_sistema(
        prompt_cliente=system_prompt,
        prompt_ferramentas=ferramentas_prompt,
        prompt_padrao=prompt_padrao,
        exigir_json=False,
    )

    dados = (
        "Mensagem original do cliente:\n"
        + texto_seguro(message)
        + "\n\n"
        + "Categoria pesquisada:\n"
        + texto_seguro(
            filtros.get(
                "consulta",
                "",
            )
        )
        + "\n\n"
        + "Filtros internos da pesquisa:\n"
        + json.dumps(
            filtros,
            ensure_ascii=False,
        )
        + "\n\n"
        + "Registros encontrados:\n"
        + json.dumps(
            registros,
            ensure_ascii=False,
            default=str,
        )
        + "\n\n"
        + "Gere somente a resposta final "
        + "em texto para o cliente."
    )

    mensagens = [
        {
            "role": "system",
            "content": prompt_sistema,
        },
        {
            "role": "user",
            "content": dados,
        },
    ]

    resposta = client.chat.completions.create(
        model=settings.groq_model,
        messages=mensagens,
        temperature=0.2,
    )

    conteudo = (
        resposta.choices[0]
        .message
        .content
        or ""
    ).strip()

    if not conteudo:
        raise ValueError(
            "A IA retornou uma resposta vazia."
        )

    if conteudo.startswith("```json"):
        conteudo = conteudo[7:].strip()

        if conteudo.endswith("```"):
            conteudo = conteudo[:-3].strip()

    elif conteudo.startswith("```"):
        conteudo = conteudo[3:].strip()

        if conteudo.endswith("```"):
            conteudo = conteudo[:-3].strip()

    if conteudo.startswith("{"):
        try:
            possivel_json = json.loads(
                conteudo
            )

        except json.JSONDecodeError:
            possivel_json = None

        if isinstance(
            possivel_json,
            dict,
        ):
            resposta_final = (
                possivel_json.get("answer")
                or possivel_json.get("resposta")
                or possivel_json.get("mensagem")
            )

            if resposta_final:
                return texto_seguro(
                    resposta_final
                )

            return (
                "Não foi possível gerar "
                "uma resposta textual."
            )

    return conteudo