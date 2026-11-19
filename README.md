
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
| `refresh_index` | Atualizar o índice de arquivos. |
| `list_indexed_folders` | Consultar os diretórios indexados. |

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

## Tecnologias

- Model Context Protocol (MCP)
- Indexação e catalogação de arquivos
- Busca textual e, opcionalmente, busca semântica
- Integração com assistentes de Inteligência Artificial
