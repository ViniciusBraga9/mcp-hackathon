
# Seus arquivos, encontrados fácilmente

**Menos tempo procurando. Mais tempo encontrando.**

O projeto é um servidor MCP (Model Context Protocol) desenvolvido para conectar assistentes de Inteligência Artificial a um indexador de arquivos.

Com ele, é possível encontrar documentos, imagens, planilhas, PDFs e outros arquivos utilizando perguntas em linguagem natural, sem precisar conhecer seus nomes exatos ou navegar manualmente por diversas pastas.

**Exemplos de perguntas:**

- "Encontre o PDF que contém o relatório financeiro de 2025."
- "Procure uma planilha com dados de vendas."
- "Onde está o documento que fala sobre projetos de infraestrutura?"
- "Encontre arquivos relacionados ao contrato da empresa."
- "Quais documentos foram modificados recentemente?"
- "Existe algum arquivo que menciona o nome de determinado cliente?"

## Como funciona?

O funcionamento é dividido em quatro etapas:

1. **Indexação:** o sistema analisa os diretórios autorizados e registra informações dos arquivos.
2. **Organização:** os arquivos são catalogados por nome, extensão, localização, data e, quando habilitado, conteúdo.
3. **Busca inteligente:** o servidor MCP disponibiliza ferramentas para que a IA pesquise os arquivos de acordo com as perguntas do usuário.
4. **Resultado:** a IA apresenta os arquivos encontrados, seus caminhos e informações relevantes para facilitar a identificação.

## Principais funcionalidades

- Pesquisa de arquivos por linguagem natural.
- Busca por nome, extensão e conteúdo.
- Localização de documentos em diferentes diretórios.
- Filtragem por tipo e data de modificação.
- Exibição do caminho completo dos arquivos.
- Apresentação de trechos relevantes para contextualizar os resultados.
- Atualização do índice para reconhecer novos arquivos.

O projeto utiliza o Model Context Protocol (MCP) para disponibilizar as funcionalidades do indexador aos assistentes de IA compatíveis.

A IA pode utilizar ferramentas como:

| Ferramenta | Finalidade |
|---|---|
| `search_files` | Pesquisar arquivos por palavras-chave ou contexto. |
| `get_file_info` | Consultar informações de um arquivo. |
| `read_file` | Ler o conteúdo de um arquivo autorizado. |
| `get_file_path` | Obter o caminho absoluto de um arquivo pelo nome exato ou caminho relativo. |
| `get_folder_tree` | Exibir a estrutura de arquivos e subpastas dentro das raízes autorizadas. |
| `refresh_index` | Atualizar o índice de arquivos. |
| `list_indexed_roots` | Listar os diretórios autorizados e a contagem de arquivos indexados em cada um. |

`get_file_path` recebe `name`. Para distinguir arquivos com o mesmo nome, informe o caminho relativo ou absoluto. `get_folder_tree` aceita `path`, `max_depth` (padrão 2) e `max_entries` (padrão 200). Sem `path`, a árvore parte de todas as raízes autorizadas.

## Objetivo do projeto

Criar uma maneira mais natural e eficiente de interagir com arquivos.

A proposta é eliminar a dependência de buscas manuais e permitir que qualquer usuário encontre documentos simplesmente descrevendo o que procura.

**Descreva o que precisa encontrar sem o estresse de procurar.**

## Segurança e privacidade

- Acesso limitado aos diretórios previamente autorizados.
- Respeito às permissões de acesso aos arquivos.
- Validação dos caminhos antes de qualquer leitura.
- Nenhuma execução automática de arquivos encontrados.
- Possibilidade de restringir a leitura de conteúdo e trabalhar somente com metadados.

## Execução local

Por padrão, o servidor indexa `local-search-mcp\data`. Para autorizar outras pastas, defina `LOCAL_SEARCH_ROOTS` no PowerShell antes de iniciar o servidor. Separe múltiplas pastas com `;`.

```powershell
$env:LOCAL_SEARCH_ROOTS = 'C:\Documentos;D:\Projetos'
.\local-search-mcp\.venv\Scripts\python.exe .\local-search-mcp\src\server.py
```

Sem `LOCAL_SEARCH_ROOTS`, execute apenas a segunda linha para usar a pasta padrão. A busca examina nomes, caminhos e conteúdo de arquivos de texto UTF-8 suportados; `read_file` retorna até 50.000 caracteres.

## Busca textual e semântica

A ferramenta MCP `search_files` aceita dois modos.

- **Textual** (`mode: "text"`, padrão) busca palavras no nome, caminho e conteúdo. Use `extension` e `modified_from` ou `modified_to` para filtrar os resultados. As datas usam `YYYY-MM-DD` e os limites são inclusivos em UTC. Informe pelo menos um filtro para fazer uma busca textual sem palavras-chave.
- **Semântico** (`mode: "semantic"`) compara o significado da consulta com trechos dos documentos por meio de embeddings da OpenAI. Cada arquivo aparece uma vez, com o trecho mais parecido e o valor `similarity`. Os mesmos filtros são aplicados antes da comparação. A consulta e os trechos dos arquivos que atendem aos filtros são enviados à API, que requer `OPENAI_API_KEY`.

Exemplos de argumentos para `search_files`:

```json
{"query": "relatório", "extension": "txt", "modified_from": "2025-01-01"}
```

```json
{"query": "como economizar combustível", "mode": "semantic", "extension": ".txt", "limit": 5}
```

A busca de conteúdo cobre os formatos de texto UTF-8 suportados, como TXT, Markdown e CSV, até 1 MB por arquivo. PDF, DOCX e outros binários podem ser encontrados no modo textual por nome, caminho e metadados.

## Assistente com a API da OpenAI

O assistente recebe uma pergunta, inicia o servidor MCP local via `stdio` e chama as ferramentas de arquivos solicitadas pelo modelo na Responses API. A pergunta e os resultados das ferramentas são enviados à OpenAI e podem incluir caminhos, metadados e trechos ou conteúdo de arquivos das pastas autorizadas.

Na raiz do repositório, instale as dependências e informe a chave quando o PowerShell solicitar.

```powershell
.\local-search-mcp\.venv\Scripts\python.exe -m pip install -r .\local-search-mcp\requirements.txt
$apiKey = Read-Host 'Chave da API da OpenAI' -AsSecureString
$env:OPENAI_API_KEY = ([System.Net.NetworkCredential]::new('', $apiKey)).Password
$env:LOCAL_SEARCH_ROOTS = 'C:\Documentos'
.\local-search-mcp\.venv\Scripts\python.exe .\local-search-mcp\src\assistant.py 'Encontre os arquivos sobre infraestrutura.'
```

Ajuste `LOCAL_SEARCH_ROOTS` para uma pasta que você queira pesquisar. O modelo padrão é `gpt-5-mini`. Para escolher outro modelo com suporte a chamadas de ferramentas, use `--model` ou defina `OPENAI_MODEL`. Se `LOCAL_SEARCH_POSTGRES_DSN` estiver configurada, o assistente também usa o índice PostgreSQL.

Para executar a suíte com a API simulada e o servidor MCP real, rode o comando abaixo. Os testes dispensam uma chave da OpenAI.

```powershell
.\local-search-mcp\.venv\Scripts\python.exe -B -m unittest discover -s local-search-mcp/tests -v
```

## PostgreSQL

O PostgreSQL armazena os metadados do índice. O servidor MCP continua lendo o conteúdo dos arquivos diretamente nas pastas autorizadas. Sem `LOCAL_SEARCH_POSTGRES_DSN`, o índice fica em memória.

Na raiz do repositório, instale as dependências e aplique o esquema em um banco PostgreSQL existente. O exemplo usa um banco chamado `local_search_mcp` e um usuário com permissão para criar o esquema e consultar e atualizar a tabela.

```powershell
.\local-search-mcp\.venv\Scripts\python.exe -m pip install -r .\local-search-mcp\requirements.txt
$env:LOCAL_SEARCH_POSTGRES_DSN = 'host=localhost port=5432 dbname=local_search_mcp user=local_search_mcp'
psql --dbname="$env:LOCAL_SEARCH_POSTGRES_DSN" -v ON_ERROR_STOP=1 -f .\local-search-mcp\sql\schema.sql
.\local-search-mcp\.venv\Scripts\python.exe .\local-search-mcp\src\server.py
```

Se `psql` não estiver no PATH do Windows, use o caminho para `psql.exe` na pasta `bin` da instalação do PostgreSQL. Se a conexão exigir senha, configure o arquivo de senhas do PostgreSQL (`pgpass.conf` no Windows) para que o cliente MCP possa iniciar o servidor sem uma solicitação interativa. Se o cliente iniciar o processo diretamente, configure `LOCAL_SEARCH_POSTGRES_DSN` no ambiente desse processo.

O servidor percorre recursivamente as pastas autorizadas e registra o caminho absoluto, o nome, a extensão, o tamanho em bytes e a data de modificação em UTC na tabela `local_search.indexed_files`. As ferramentas `search_files` e `list_indexed_roots` consultam os metadados do catálogo no banco.

O catálogo é sincronizado na inicialização e a cada chamada de `refresh_index`. A ferramenta retorna os caminhos completos em `changes.new`, `changes.modified` e `changes.removed`, comparando a varredura com o último estado do catálogo. Alterações são detectadas pelos metadados, como tamanho e data de modificação. O PostgreSQL grava as inclusões, atualizações e remoções na mesma transação.

## Tecnologias

- Model Context Protocol (MCP)
- Indexação e catalogação de arquivos
- Busca textual e, opcionalmente, busca semântica
- Integração com assistentes de Inteligência Artificial
