
## Repesquisa MCP

**Encontre seus arquivos conversando com uma IA.**

O Repesquisa é um servidor MCP local, desenvolvido em Python, que permite a assistentes de IA pesquisar arquivos em diretórios autorizados do computador.

A proposta é simplificar a localização de documentos por meio de perguntas em linguagem natural, sem precisar lembrar o nome exato do arquivo ou em qual pasta ele foi salvo.

Nesta versão inicial, a busca considera principalmente o nome e o caminho dos arquivos. A pesquisa dentro do conteúdo de PDFs, planilhas e documentos será adicionada em etapas futuras.

## Propósito

Transformar a maneira como as pessoas encontram seus arquivos.

Em vez de navegar manualmente por centenas ou milhares de documentos, o usuário pode simplesmente perguntar à IA o que está procurando.

**Você pergunta. O Repesquisa encontra.**

## Exemplos de utilização

- "Encontre o relatório financeiro de 2025."
- "Procure planilhas Excel na pasta Downloads."
- "Onde está aquele contrato de prestação de serviços?"
- "Encontre arquivos relacionados a projetos de infraestrutura."
- "Mostre os documentos modificados recentemente."
- "Qual é o caminho completo do arquivo encontrado?"

## O que esta versão faz

- Indexa arquivos de diretórios autorizados.
- Registra nome, caminho, extensão, tamanho e data de modificação em um banco SQLite local.
- Pesquisa por palavras presentes no nome e no caminho.
- Consulta metadados de um arquivo.
- Mostra a árvore de diretórios.
- Atualiza o índice quando solicitado.

## Compatibilidade com assistentes de IA

O Repesquisa utiliza o Model Context Protocol (MCP), permitindo sua integração com clientes de IA compatíveis.

### Claude Desktop

O Repesquisa pode ser utilizado com o **Claude Desktop**, por meio de um servidor MCP local.

A conexão é realizada através do arquivo `claude_desktop_config.json`, permitindo que o Claude utilize as ferramentas de pesquisa disponibilizadas pelo Repesquisa.

**Não é necessária uma API Key da OpenAI ou da Anthropic para essa integração local.** O Claude realiza a conversa e o Repesquisa executa as pesquisas no computador.

## Requisitos

- Python 3.11 ou superior.
- [UV](https://docs.astral.sh/uv/) para instalar e executar o projeto.
- [Claude Desktop](https://claude.com/download) para utilizar o assistente de IA.
- MCP Inspector para testes e desenvolvimento.

## Instalação

### 1. Configurar os diretórios autorizados

Edite o arquivo `config.json` e informe as pastas que o Repesquisa poderá percorrer.

Exemplo no Windows:

```json
{
  "roots": [
    "C:/Users/SEU_USUARIO/Downloads",
    "C:/Users/SEU_USUARIO/Documents",
    "D:/Arquivos"
  ]
}
```

Substitua os exemplos pelos caminhos reais existentes no seu computador.

O servidor restringe suas ferramentas aos diretórios configurados.

### 2. Instalar as dependências

Abra o terminal na pasta do projeto e execute:

```powershell
uv sync
```

Confirme que o UV está instalado:

```powershell
uv --version
```

## Configuração no Claude Desktop

O Repesquisa funciona com o Claude Desktop como servidor MCP local.

### 3.1. Localizar o arquivo de configuração

No Windows, o arquivo fica em:

```text
%APPDATA%\Claude\claude_desktop_config.json
```

Para abri-lo pelo PowerShell:

```powershell
notepad "$env:APPDATA\Claude\claude_desktop_config.json"
```

Se o arquivo não existir, crie-o.

### 3.2. Configurar o servidor Repesquisa

Adicione a seguinte configuração, substituindo `SEU_USUARIO` pelo nome da sua pasta de usuário e ajustando o caminho da pasta do projeto:

```json
{
  "mcpServers": {
    "repesquisa": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\Users\\SEU_USUARIO\\Documents\\repesquisa-mcp",
        "run",
        "server.py"
      ]
    }
  }
}
```

**Importante:**

- O caminho informado em `--directory` deve ser o caminho absoluto da pasta que contém `server.py` e `pyproject.toml`.
- Se já houver outros servidores no `claude_desktop_config.json`, não apague as configurações existentes. Apenas acrescente a entrada `repesquisa` dentro de `mcpServers`.
- Se o Claude não conseguir encontrar o comando `uv`, execute `where.exe uv` no PowerShell e utilize o caminho completo retornado no campo `command`.

### 3.3. Reiniciar e verificar

1. Salve o arquivo JSON.
2. Encerre completamente o Claude Desktop.
3. Abra novamente o Claude Desktop.
4. Acesse Settings > Developer.
5. Verifique se o Repesquisa aparece como servidor local conectado.
6. Confira as ferramentas disponíveis na área de conectores do Claude.

Se houver erro, consulte os logs de servidores MCP na área de desenvolvedor do Claude e verifique os caminhos configurados.

Documentação de referência:

- [Anthropic — Local MCP servers in Claude Desktop](https://support.anthropic.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)
- [MCP — Connect local servers](https://modelcontextprotocol.io/docs/develop/connect-local-servers)

## Testar com MCP Inspector

Também é possível testar o servidor sem o Claude Desktop.

Execute:

```powershell
uv run mcp dev server.py
```

O MCP Inspector abrirá uma interface para conectar ao servidor e testar suas ferramentas.

Exemplo de parâmetros para `search_files`:

```json
{
  "query": "relatório financeiro",
  "extension": ".pdf",
  "limit": 10
}
```

## Ferramentas MCP disponíveis

| Ferramenta | Descrição |
|---|---|
| `list_indexed_roots` | Lista os diretórios autorizados configurados. |
| `refresh_index` | Indexa ou atualiza os metadados dos arquivos. |
| `search_files` | Pesquisa por palavras no nome e no caminho. |
| `get_file_info` | Consulta metadados de um arquivo autorizado. |
| `get_folder_tree` | Mostra a estrutura de pastas de um diretório autorizado. |

## Primeira pesquisa

Depois de conectar o Repesquisa ao Claude Desktop:

1. Peça ao Claude para listar os diretórios autorizados.
2. Solicite que execute `refresh_index` para criar ou atualizar o catálogo.
3. Faça perguntas como:

- "Encontre arquivos com relatório financeiro no nome."
- "Procure planilhas Excel na pasta Downloads."
- "Mostre o caminho completo do arquivo encontrado."
- "Mostre a estrutura da pasta Documentos."

## Segurança e privacidade

- Configure somente diretórios que deseja disponibilizar para pesquisa.
- O servidor verifica os caminhos contra os diretórios autorizados antes de acessar arquivos.
- Não conceda acesso a pastas com dados sensíveis sem avaliar os riscos.
- Não execute automaticamente arquivos encontrados.
- Esta versão não envia o conteúdo dos arquivos para a OpenAI ou Anthropic.
- O texto das perguntas e os resultados retornados ao Claude ficam sujeitos às políticas de dados e privacidade do serviço Claude utilizado.

## Limitações desta versão

- A busca considera nome e caminho; ainda não pesquisa o conteúdo interno dos documentos.
- Não abre, altera ou exclui arquivos.
- Não segue links simbólicos.
- Ignora arquivos e pastas ocultos.
- A indexação é acionada pela ferramenta `refresh_index`; ainda não há monitoramento automático em segundo plano.
- O servidor utiliza transporte local `stdio`. O Claude Desktop precisa estar instalado no mesmo computador para iniciar esse processo localmente.

