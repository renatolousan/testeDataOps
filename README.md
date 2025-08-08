# Web Scraping de Imóveis CAIXA

## Como rodar?

### 1. Clone do Repositório
```bash
git clone https://github.com/renatolousan/testeDataOps.git
cd testeDataOps
```

### 2. Configuração do Ambiente Python
```bash
# Criar ambiente virtual
python -m venv venv

# Ativar ambiente virtual
# Linux/Mac:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# Instalar dependências
pip install -r requirements.txt
```

### 3. Execução do Script
```bash
# Executar scraping para São Paulo (padrão)
python main.py

# Executar para outras cidades
python main.py --estado RJ --cidade "RIO DE JANEIRO"
python main.py -e MG -c "BELO HORIZONTE"

# Listar cidades disponíveis
python main.py --list-cities -e AM         # Lista cidades disponíveis para AM

# Ver ajuda
python main.py --help                      # Mostra esta ajuda

# Ou executar script diretamente
python script.py
```

### 4. Arquivos de Saída
Após a execução, serão gerados:
- `imoveis_sp_sao_paulo_YYYYMMDD_HHMMSS.csv` - Dados em formato CSV
- `imoveis_sp_sao_paulo_YYYYMMDD_HHMMSS.json` - Dados em formato JSON
- `scraper_caixa.log` - Log detalhado da execução
- `debug_results_http.html` - HTML de debug (se necessário)
