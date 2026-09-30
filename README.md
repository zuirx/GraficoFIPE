# FipeData

O **FipeData** é uma plataforma simples e rápida para consultar e visualizar o histórico de preços de veículos da Tabela FIPE. Com ele, você pode buscar por carros, motos e caminhões, visualizar gráficos com a evolução de preços ao longo dos meses e encontrar as melhores opções de acordo com o seu orçamento.

## Instalação

### 1. Instalar os requisitos
Certifique-se de ter o Python instalado. No terminal, instale os pacotes necessários:
```bash
pip install -r requirements.txt
```

### 2. Atualizar a base de dados
Para garantir que você está visualizando os preços mais recentes, basta rodar o comando abaixo para baixar a Tabela FIPE atualizada:
```bash
python baixa_fipex.py
```
*(Ele baixará o histórico completo e deixará pronto para o sistema usar).*

### 3. Iniciar o site
Após baixar os dados, inicie o servidor rodando:
```bash
python app.py
```

Pronto! Agora é só abrir o seu navegador e acessar: **http://127.0.0.1:7177**

---

## Outras ferramentas (Para usuários avançados)

Caso precise de abordagens alternativas, o FipeData também inclui:
- `extrator_fipe.py`: Uma ferramenta própria para buscar os dados mês a mês diretamente na fonte e criar um banco de dados do zero.
- `app_sqlite.py`: Inicia o site utilizando o formato do extrator manual acima (banco SQLite) em vez da versão rápida (DuckDB).
- `import_duckdb.py`: Útil apenas caso você baixe o arquivo de preços manualmente da internet e queira processá-lo offline.
