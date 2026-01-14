# Tech Challenge - Fase 2: Pipeline Batch Bovespa | Ingestão e Arquitetura de Dados

Este projeto é o entregável principal da **Fase 2** da Pós-Graduação em **Machine Learning Engineering**. O objetivo é demonstrar habilidades em engenharia de dados, arquitetura cloud e processamento em larga escala, criando um pipeline completo para ingestão e transformação de dados da B3 (Bolsa de Valores Brasileira).

O desafio consiste em desenvolver um pipeline ETL (Extract, Transform, Load) que:
1. **Extrai** dados da B3 via web scraping do IBOV (Índice Bovespa)
2. **Transforma** os dados em formato otimizado para análise
3. **Carrega** os dados em um data lake na AWS S3

---

## 🏗️ Arquitetura do Projeto

O pipeline de dados foi estruturado em três etapas principais:

### 1. **Ingestão (Web Scraping) - `src/scraping.py`**
Um script Python automatizado que navega pelo site `https://sistemaswebb3-listados.b3.com.br/indexPage/day/IBOV`. Utiliza Selenium para fazer web scraping dinâmico dos dados do índice Bovespa, incluindo:
- Código de negociação
- Nome da ação
- Tipo de ativo
- Quantidade teórica
- Participação percentual no índice

Os dados são salvos localmente em formato **Parquet particionado por data** (`b3_data/ano_mes_dia=YYYY-MM-DD/`) e posteriormente enviados para o **AWS S3** (bucket `fiap-luiz-mlet`).

### 2. **Transformação (AWS Glue ETL) - `src/etl_glue.py`**
Um job do AWS Glue que realiza transformações sofisticadas nos dados:
- Lê dados da partição mais recente do S3
- Renomeia colunas para padrão snake_case
- Converte tipos de dados (strings para números)
- Adiciona metadados (data de referência, dias desde última atualização)
- Agrega dados por ação com totalizações
- Salva dados refinados em S3 no formato Parquet particionado

### 3. **Orquestração (AWS Lambda) - `src/lambda_function.py`**
Uma função Lambda que atua como orquestradora do pipeline:
- Monitora novos arquivos carregados no S3 (via S3 events)
- Dispara automaticamente o job Glue quando novos dados chegam
- Fornece logging e monitoramento do status de execução

---

## 🛠️ Tecnologias Utilizadas

* **Linguagem:** Python 3.9+
* **Web Scraping:** `Selenium` e `WebDriver Manager`
* **Manipulação de Dados:** `Pandas` e `PyArrow`
* **Cloud (AWS):** 
  - S3 (Data Lake)
  - Glue (ETL)
  - Lambda (Orquestração)
* **Armazenamento:** `Parquet` (formato otimizado)
* **Autenticação:** `python-dotenv` (variáveis de ambiente) 

---

## ⚙️ Instalação e Configuração

### Pré-requisitos
- Python 3.9+
- Chrome/Chromium instalado (para Selenium)
- Conta AWS com credenciais configuradas
- Variáveis de ambiente AWS (Access Key, Secret Key, Session Token)

### Passo 1: Clone o Repositório
```bash
git clone <URL_DO_REPOSITORIO>
cd postech-tech-challenge-f2
```

### Passo 2: Crie e Ative o Ambiente Virtual
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux/Mac
python -m venv .venv
source .venv/bin/activate
```

### Passo 3: Instale as Dependências
```bash
pip install -r requirements.txt
```

### Passo 4: Configure as Variáveis de Ambiente
Crie um arquivo `.env` na raiz do projeto com suas credenciais AWS:
```env
ACCESS_KEY=sua_access_key_aqui
SECRET_KEY=sua_secret_key_aqui
SESSION_TOKEN=seu_session_token_aqui
```

---

## 🚀 Execução

### Opção 1: Executar Scraping Manualmente
```bash
# Windows (via batch script)
run_scraping.bat

# Linux/Mac
python src/scraping.py
```

### Opção 2: Agendar Scraping (Windows)
O arquivo `run_scraping.bat` pode ser agendado via **Agendador de Tarefas do Windows**:
1. Abrir Agendador de Tarefas
2. Criar nova tarefa
3. Agendar para executar `run_scraping.bat` em horários específicos
4. Script ativa automaticamente o venv e executa o scraping

### Opção 3: Pipeline Completo (AWS)
1. **Carregar o job Glue no AWS:**
   - Upload do arquivo `src/etl_glue.py` para AWS Glue
   - Configurar job com role IAM apropriado
   - Usar PySpark engine

2. **Configurar Lambda para orquestração:**
   - Deploy de `src/lambda_function.py`
   - Criar trigger S3 para detectar novos dados
   - Lambda dispara automaticamente o job Glue

---

## 📊 Fluxo de Dados

```
B3 Website (IBOV)
       ↓
[Selenium Scraping] → parquet files (local)
       ↓
AWS S3 (raw/b3_data/) - Particionado por data
       ↓
[AWS Lambda Trigger]
       ↓
[AWS Glue ETL Job] - Transformação de dados
       ↓
AWS S3 (refined/b3_data/) - Dados processados
```

---

## 📂 Estrutura de Arquivos

```
postech-tech-challenge-f2/
├── README.md                 # Este arquivo
├── requirements.txt          # Dependências Python
├── run_scraping.bat          # Script batch para Windows
├── .env.example              # Template de variáveis de ambiente
├── .venv/                    # Ambiente virtual
├── b3_data/                  # Dados locais particionados por data
│   ├── ano_mes_dia=2026-01-10/
│   ├── ano_mes_dia=2026-01-11/
│   └── ...
└── src/
    ├── scraping.py           # Web scraping da B3
    ├── etl_glue.py           # ETL no AWS Glue
    └── lambda_function.py    # Orquestração Lambda
```

---

## 🔧 Classes e Funcionalidades

### `B3Scraper` (src/scraping.py)
- **Responsabilidade:** Web scraping do IBOV na B3
- **Métodos principais:**
  - `setup_driver()` - Configura Chrome headless
  - `get_all_pages_data()` - Navega e coleta dados de todas as páginas
  - `scrape()` - Executa o scraping completo

### `DataProcessor` (src/scraping.py)
- **Responsabilidade:** Processamento local dos dados
- **Métodos principais:**
  - `add_date_column()` - Adiciona coluna de data de ingestão
  - `save_to_parquet()` - Salva em formato Parquet particionado

### `S3Uploader` (src/scraping.py)
- **Responsabilidade:** Upload para AWS S3
- **Métodos principais:**
  - `upload_files()` - Envia arquivos para data lake

### `GlueETL` (src/etl_glue.py)
- **Responsabilidade:** Transformação de dados em escala
- **Métodos principais:**
  - `fetch_data()` - Lê dados do S3
  - `rename_columns()` - Normaliza nomes de colunas
  - `cast_columns()` - Converte tipos de dados
  - `aggregate_data()` - Agrega dados por ação
  - `run_etl()` - Executa pipeline completo

---

## 📈 Dados Processados

### Colunas da B3 (Brutos)
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| Código | String | Código de negociação da ação |
| Ação | String | Nome da ação |
| Tipo | String | Tipo de ativo |
| Qtde. Teórica | String | Quantidade teórica no índice |
| Part. (%) | String | Participação percentual |

### Colunas Processadas (Refinadas)
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| codigo | String | Código normalizado |
| acao | String | Nome da ação |
| tipo | String | Tipo de ativo |
| quantidade_teorica | Long | Quantidade teórica (numérica) |
| participacao_percentual | Float | Participação em % (numérica) |
| quantidade_teorica_total | Long | Total de quantidade teórica |
| quantidade_teorica_acao | Long | Total por ação |
| participacao_percentual_acao | Float | Participação agregada por ação |
| quantidade_dias_ultima_data_referencia | Int | Dias desde última atualização |
| data_referencia | Date | Data de referência |


---

## 🔍 Monitoramento e Troubleshooting

### Problemas Comuns

#### 1. Erro ao conectar no Chrome
**Erro:** `chromedriver version mismatch`
**Solução:** O `webdriver-manager` baixa automaticamente a versão correta. Verifique se o Chrome está instalado.

#### 2. Erro ao fazer upload para S3
**Erro:** `NoCredentialsError` ou `InvalidAccessKeyId`
**Solução:** Verifique se o arquivo `.env` tem as credenciais AWS corretas e se a sessão não expirou.

#### 3. Job Glue falhando
**Erro:** `Error when reading data from S3`
**Solução:** Verifique permissões IAM do role Glue, confirme que os dados foram efetivamente enviados para S3.

---

## 📝 Logging

Todos os scripts geram logs detalhados com timestamps:
- **Nível de informação:** Operações completadas com sucesso
- **Nível de alerta:** Diretórios não encontrados, arquivos vazios
- **Nível de erro:** Falhas de conexão, conversão de dados inválida

Logs são exibidos no console e podem ser redirecionados para arquivos.

---

## 🤝 Contribuindo

Para contribuir com melhorias:
1. Crie uma branch para sua feature (`git checkout -b feature/melhoria`)
2. Commit suas mudanças (`git commit -m 'Adiciona melhoria'`)
3. Push para a branch (`git push origin feature/melhoria`)
4. Abra um Pull Request

---

## 📚 Documentação Adicional

- [AWS Glue Documentation](https://docs.aws.amazon.com/glue/)
- [Selenium Documentation](https://www.selenium.dev/documentation/)
- [PyArrow / Parquet Documentation](https://arrow.apache.org/docs/python/)
- [B3 - Bovespa](https://www.b3.com.br/)

---

## 👨‍💻 Autor

**Projeto:** Tech Challenge - Fase 2  
**Pós-Graduação:** Machine Learning Engineering - FIAP  
**Data:** Janeiro 2026

---

## 📄 Licença

Este projeto é parte do currículo da FIAP e segue a política institucional de uso.

````