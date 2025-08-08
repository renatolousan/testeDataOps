# Relatório

## Quais são os principais campos de dados extraídos dos imóveis?

### Campos que foram extraídos dos imóveis
- **`codigo`**: Código único do imóvel (ex: "878771259229-0")
- **`numero_item`**: Número do item no leilão (ex: "533")
- **`titulo`**: Nome do empreendimento (ex: "SAO PAULO - RESIDENCIAL CEREJEIRAS")
- **`endereco`**: Endereço completo
- **`bairro`**: Bairro extraído automaticamente
- **`tipo_imovel`**: "Apartamento" ou "Casa"
- **`area`**: Área útil em m² (ex: "70,86 m²")
- **`quartos`**: Número de quartos (ex: "2 quartos")
- **`valor`**: Valor de venda (ex: "R$ 197.857,57")
- **`modalidade`**: "Leilão" ou "Venda Direta"

## Como a cadência de requisições é gerenciada pelo script?

### Estratégias Implementadas

1. **Rate Limiting**: 6 reqs por segundo
   ```python
   @sleep_and_retry
   @limits(calls=6, period=1)  # até 6 req/segundo
   def _post(self, url: str, data: dict) -> requests.Response:
   ```

2. **Delay Manual**: 0.5 segundos entre páginas
   ```python
   self.delay_between_requests = 0.5  # segundos
   # No loop principal:
   time.sleep(self.delay_between_requests)
   ```

3. **Backoff Exponencial**: 0.5-6 segundos em falhas
   ```python
   @retry(reraise=True,
          stop=stop_after_attempt(5),
          wait=wait_exponential(multiplier=0.5, min=0.5, max=6),
          retry=retry_if_exception_type(RequestException))
   ```

4. **Jitter Aleatório**: 0.5-1.5 segundos na renovação de sessão
   ```python
   def _refresh_session(self):
       # jitter aleatório antes de reabrir
       time.sleep(0.5 + random.random())
       self._init_session()
   ```

5. **Retry Automático**: 5 tentativas no máximo por requisição
   ```python
   @retry(reraise=True,
          stop=stop_after_attempt(5),  # 5 tentativas máximo
          retry=retry_if_exception_type(RequestException))
   ```

## Quais outras barreiras anti-scraping tive que lidar no código?

### Principais Barreiras Contornadas

1. **Bot Manager Radware**: indentifica e renova automaticamente a sessão.
   ```python
   def _is_captcha(self, text: str) -> bool:
       t = text[:2048].lower()
       return ("radware bot manager" in t) or ("captcha" in t and "radware" in t)
   ```

2. **User-Agent Fingerprinting**: User-Agents gerados randomicamente.
   ```python
   from fake_useragent import UserAgent
   self.ua = UserAgent()
   ua = self.ua.random  # Novo UA a cada sessão
   ```

3. **Headers HTTP**: Headers que simulam um navegador padrão.
   ```python
   s.headers.update({
       "User-Agent": ua,
       "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
       "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
       "Connection": "keep-alive",
       "Referer": self.search_url,
       "Origin": BASE_URL
   })
   ```

4. **Cookies e Sessão**: Persistência de estado.
   ```python
   def _init_session(self):
       s = requests.Session()
       s.get(self.search_url, timeout=30)  # Primeira visita para cookies
       self.session = s
   ```

5. **HTML Malformado**: REGEX para padrões quebrados
   ```python
   # HTML quebrado: <option value='260'>MANAUS<br><option value='269'>NOVA OLINDA
   option_pattern = r"<option value='([^']+)'>([^<]+)"
   matches = re.findall(option_pattern, html)
   ```

6. **Endpoints Fragmentados**: Fluxo multi-etapas para diferentes estados da página.
   ```python
   URL_CIDADES = f"{SISTEMA}/carregaListaCidades.asp"    # 1. Código da cidade
   URL_BAIRROS = f"{SISTEMA}/carregaListaBairros.asp"    # 2. Lista bairros
   URL_PESQUISA = f"{SISTEMA}/carregaPesquisaImoveis.asp" # 3. Inicia pesquisa
   URL_LISTA = f"{SISTEMA}/carregaListaImoveis.asp"      # 4. Carrega páginas
   ```

7. **Campos Hidden**: Extrai automaticamente campos dinâmicos.
   ```python
   # hdnImov1, hdnImov2, hdnImov3... para paginação
   for inp in soup.find_all('input'):
       if iid.startswith('hdnImov'):
           idx = int(iid.replace('hdnImov', ''))
           ids_por_pagina[idx] = inp.get('value')
   ```

8. **Jitter Temporal**: Delays aleatórios para melhorar a cadência das requisições.
   ```python
   def _refresh_session(self):
       time.sleep(0.5 + random.random())  # 0.5-1.5s aleatório
       self._init_session()
   ```

## Lista de features extraídas dos imóveis

- Identificação: `codigo`, `numero_item`, `titulo`
- Localização: `endereco`, `bairro`
- Características: `tipo_imovel`, `area`, `quartos`
- Comerciais: `valor`, `modalidade`

## Quais são os principais desafios que tive que resolver com esse sistema?

### Como cada desafio técnico foi resolvido:

1. **Sistema Anti-Bot Radware**: Detecção automática e renovação de sessão
   ```python
   def _is_captcha(self, text: str) -> bool:
       t = text[:2048].lower()
       return ("radware bot manager" in t) or ("captcha" in t and "radware" in t)
   
   if self._is_captcha(resp.text):
       logger.warning("CAPTCHA detectado. Renovando sessão.")
       self._refresh_session()
       raise RequestException("captcha")
   ```

2. **Fluxo Multi-Etapas**: 4 endpoints sequenciais simulando navegação humana
   ```python
   # 1) Descobrir código da cidade
   cod_cidade = self._obter_codigo_cidade(self.estado, self.cidade)
   # 2) Obter bairros disponíveis
   self._obter_bairros(self.estado, cod_cidade)
   # 3) Iniciar pesquisa e extrair metadados
   html_inicio = self._iniciar_pesquisa(self.estado, cod_cidade)
   # 4) Iterar páginas via endpoint
   frag = self._carregar_pagina_fragmento(ids)
   ```

3. **HTML Malformado**: Parsing robusto com regex especializados
   ```python
   # HTML quebrado: <option value='260'>MANAUS<br><option value='269'>
   option_pattern = r"<option value='([^']+)'>([^<]+)"
   matches = re.findall(option_pattern, html)
   # Múltiplas estratégias de parsing
   endereco_patterns = [
       r'((?:RUA|AVENIDA|AV|ALAMEDA)[^,]+(?:,[^,]+)*?)(?:,\s*,|$)',
       r'Número do imóvel:\s*[0-9\-]+\s*(.+?)(?:\s*$|despesas)',
   ]
   ```

4. **Paginação Complexa**: Extração de IDs hidden dinâmicos (`hdnImov1..N`)
   ```python
   def _extrair_ids_e_paginacao(self, html: str):
       ids_por_pagina: Dict[int, str] = {}
       for inp in soup.find_all('input'):
           iid = inp.get('id') or ''
           if iid.startswith('hdnImov'):
               idx = int(iid.replace('hdnImov', ''))
               ids_por_pagina[idx] = (inp.get('value') or '').strip()
       return ids_por_pagina, total_paginas, total_registros
   ```

5. **Mapeamento de Cidades**: Consulta dinâmica + algoritmos de matching
   ```python
   def _obter_codigo_cidade(self, estado: str, nome_cidade: str):
       # Busca exata primeiro
       if alvo in city_options:
           return city_options[alvo]
       # Busca parcial (contém)
       for city_name, city_code in city_options.items():
           if alvo in city_name:
               return city_code
       # Fallback para overrides conhecidos
       override = CITY_CODE_OVERRIDES.get((estado, alvo))
       if override:
           return override
   ```

6. **Detecção de Bairros**: Lista oficial + padrões linguísticos
   ```python
   def detect_bairro_from_endereco(self, endereco):
       # Usar lista oficial de bairros
       for bairro in self.bairros_disponiveis:
           if bairro in endereco_upper:
               return bairro
       # Padrões linguísticos
       prefixos_bairro = ['VILA ', 'CIDADE ', 'JARDIM ', 'PARQUE ']
       for prefixo in prefixos_bairro:
           if prefixo in endereco_upper:
               return endereco_upper[start_pos:].split(',')[0]
   ```

7. **Rate Limiting Agressivo**: Múltiplas camadas de controle de velocidade
   ```python
   @sleep_and_retry
   @limits(calls=6, period=1)  # 6 req/segundo
   @retry(stop=stop_after_attempt(5),
          wait=wait_exponential(multiplier=0.5, min=0.5, max=6))
   def _post(self, url: str, data: dict):
       # + delay manual entre páginas
       time.sleep(self.delay_between_requests)
   ```

8. **Limpeza de Dados**: Remoção de informações irrelevantes
   ```python
   def _clean_endereco(self, endereco_bruto):
       padroes_a_remover = [
           r'avaliação:\s*R\$[^A-Z]*',
           r'Valor mínimo de venda:[^A-Z]*',
           r'desconto de[^A-Z]*',
           r'Apartamento\s*-\s*\d+\s*quarto\(s\)\s*-[^A-Z]*'
       ]
       for padrao in padroes_a_remover:
           endereco = re.sub(padrao, '', endereco, flags=re.IGNORECASE)
   ```

9. **Recuperação de Falhas**: Retry inteligente com backoff exponencial
   ```python
   @retry(reraise=True,
          stop=stop_after_attempt(5),
          wait=wait_exponential(multiplier=0.5, min=0.5, max=6),
          retry=retry_if_exception_type(RequestException))
   def _post(self, url: str, data: dict):
       # Detecção automática de falhas e retry
   ```

10. **Estruturas Inconsistentes**: Múltiplos parsers e fallbacks
    ```python
    def extract_imoveis_from_page(self, html_content):
        # Estratégia principal
        results_section = soup.find('div', id='listaimoveispaginacao')
        if results_section:
            property_items = results_section.find_all('li', class_='group-block-item')
        else:
            # Métodos alternativos
            imoveis = self._extract_from_fallback_methods(soup)
    ```

11. **Simulação Humana**: Headers completos + timing natural
    ```python
    s.headers.update({
        "User-Agent": self.ua.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
        "Referer": self.search_url,
        "Origin": BASE_URL
    })
    # Primeira visita para estabelecer sessão
    s.get(self.search_url, timeout=30)
    ```

12. **Debugging**: Logging abrangente + salvamento de HTML
    ```python
    def debug_save_html(self, html_content, filename="debug_page.html"):
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info(f"HTML salvo para debug: {filename}")
    
    @log_method  # Decorator para logging automático
    def scrapeImoveis(self):
        logger.info("📊 Paginação detectada:")
        logger.info(f"   Total de páginas: {total_paginas}")
