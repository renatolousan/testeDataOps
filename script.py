import time
import json
import re
import random
from typing import Dict, List, Tuple
import pandas as pd
import requests
from requests.exceptions import RequestException
from fake_useragent import UserAgent
from datetime import datetime
from bs4 import BeautifulSoup

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from ratelimit import limits, sleep_and_retry
from tqdm import tqdm

from logger_config import setup_logger, log_method
from parser import CaixaPropertyParser, CaixaHtmlExtractor
logger = setup_logger(name="scraper_caixa", log_file="scraper_caixa.log")


BASE_URL = "https://venda-imoveis.caixa.gov.br"
SISTEMA = f"{BASE_URL}/sistema"
BUSCA_URL = f"{SISTEMA}/busca-imovel.asp?sltTipoBusca=imoveis"
URL_CIDADES = f"{SISTEMA}/carregaListaCidades.asp"
URL_BAIRROS = f"{SISTEMA}/carregaListaBairros.asp"
URL_PESQUISA = f"{SISTEMA}/carregaPesquisaImoveis.asp"
URL_LISTA = f"{SISTEMA}/carregaListaImoveis.asp"

# Known city code overrides for common searches
CITY_CODE_OVERRIDES: Dict[Tuple[str, str], str] = {
    ("SP", "SAO PAULO"): "9859",
    # Add more common cities as they are discovered
    # Format: (estado, cidade_normalizada): "codigo"
}


class CaixaScraperSP:

    def __init__(self, estado="SP", cidade="SAO PAULO"):
        self.base_url = BASE_URL
        self.search_url = BUSCA_URL
        self.ua = UserAgent()
        self.delay_between_requests = 0.5  # segundos
        self.scraped_properties = []
        self.session = None

        # Configurar logger para esta instância
        self.logger = logger

        # Inicializar parser e extrator (mantidos)
        self.parser = CaixaPropertyParser()
        self.html_extractor = CaixaHtmlExtractor(self.parser)

        # Parâmetros configuráveis
        self.estado = estado
        self.cidade = cidade
        self.search_params = {
            'estado': estado,
            'cidade': cidade
        }

        logger.info(f"Scraper configurado para Estado: {estado}, Cidade: {cidade}")

    def list_available_cities(self, estado: str) -> List[str]:
        """Lista todas as cidades disponíveis para um estado específico."""
        self._init_session()
        payload = {
            "cmb_estado": estado,
            "cmb_cidade": "",
            "cmb_tp_venda": "",
            "cmb_tp_imovel": "",
            "cmb_area_util": "",
            "cmb_faixa_vlr": "",
            "cmb_quartos": "",
            "cmb_vg_garagem": "",
            "strValorSimulador": "",
            "strAceitaFGTS": "",
            "strAceitaFinanciamento": "",
        }
        r = self._post(URL_CIDADES, payload)
        html = r.text
        
        # Extrair todas as opções usando regex
        import re
        option_pattern = r"<option value='([^']+)'>([^<]+)"
        matches = re.findall(option_pattern, html)
        
        cities = []
        for value, city_text in matches:
            if value and city_text.strip() and city_text.strip().upper() != "SELECIONE":
                normalized_city = self._norm(city_text.strip())
                cities.append(normalized_city)
        
        return sorted(cities)

    # --- Sessão HTTP e utilitários ---
    def _init_session(self):
        if self.session is None:
            s = requests.Session()
            ua = self.ua.random
            s.headers.update({
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "Connection": "keep-alive",
                "Referer": self.search_url,
                "Origin": BASE_URL,
                "Upgrade-Insecure-Requests": "1",
            })
            # Primeira visita para cookies/session
            s.get(self.search_url, timeout=30)
            self.session = s

    def _refresh_session(self):
        """Gera uma nova sessão e UA para tentar evitar bloqueios de bot manager."""
        try:
            if self.session:
                self.session.close()
        except Exception:
            pass
        self.session = None
        # jitter aleatório antes de reabrir
        time.sleep(0.5 + random.random())
        self._init_session()

    def _is_captcha(self, text: str) -> bool:
        if not text:
            return False
        t = text[:2048].lower()
        return ("radware bot manager" in t) or ("captcha" in t and "radware" in t) or ("<title>radware" in t)

    @sleep_and_retry
    @limits(calls=6, period=1)  # até 6 req/segundo
    @retry(reraise=True,
           stop=stop_after_attempt(5),
           wait=wait_exponential(multiplier=0.5, min=0.5, max=6),
           retry=retry_if_exception_type(RequestException))
    def _post(self, url: str, data: dict) -> requests.Response:
        assert self.session is not None, "Sessão HTTP não inicializada"
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.search_url,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "*/*",
        }
        resp = self.session.post(url, data=data, headers=headers, timeout=30)
        # Detectar bloqueio/captcha
        if self._is_captcha(resp.text):
            logger.warning("CAPTCHA detectado no POST. Renovando sessão e tentando novamente.")
            self._refresh_session()
            raise RequestException("captcha")
        if resp.status_code >= 500:
            raise RequestException(f"{url} status {resp.status_code}")
        return resp

    @sleep_and_retry
    @limits(calls=6, period=1)
    @retry(reraise=True,
           stop=stop_after_attempt(5),
           wait=wait_exponential(multiplier=0.5, min=0.5, max=6),
           retry=retry_if_exception_type(RequestException))
    def _get(self, url: str, params: dict = None) -> requests.Response:
        assert self.session is not None, "Sessão HTTP não inicializada"
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Referer": self.search_url,
        }
        resp = self.session.get(url, params=params or {}, headers=headers, timeout=30)
        if self._is_captcha(resp.text):
            logger.warning("CAPTCHA detectado no GET. Renovando sessão e tentando novamente.")
            self._refresh_session()
            raise RequestException("captcha")
        if resp.status_code >= 500:
            raise RequestException(f"{url} status {resp.status_code}")
        return resp

    def _norm(self, s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip().upper())

    # --- Fluxo HTTP ---
    @log_method
    def _obter_codigo_cidade(self, estado: str, nome_cidade: str) -> str:
        """Consulta carregaListaCidades.asp para mapear nome -> código."""
        self._init_session()
        payload = {
            "cmb_estado": estado,
            "cmb_cidade": "",
            "cmb_tp_venda": "",
            "cmb_tp_imovel": "",
            "cmb_area_util": "",
            "cmb_faixa_vlr": "",
            "cmb_quartos": "",
            "cmb_vg_garagem": "",
            "strValorSimulador": "",
            "strAceitaFGTS": "",
            "strAceitaFinanciamento": "",
        }
        r = self._post(URL_CIDADES, payload)
        html = r.text
        
        # O HTML retornado usa <br> ao invés de tags fechadas, então vamos parsear de forma especial
        # Exemplo: <option value='260'>MANAUS<br><option value='269'>NOVA OLINDA DO NORTE<br>
        import re
        
        alvo = self._norm(nome_cidade)
        
        # Extrair todas as opções usando regex
        option_pattern = r"<option value='([^']+)'>([^<]+)"
        matches = re.findall(option_pattern, html)
        
        available_cities = []
        city_options = {}
        
        for value, city_text in matches:
            if value and city_text.strip() and city_text.strip().upper() != "SELECIONE":
                normalized_city = self._norm(city_text.strip())
                available_cities.append(normalized_city)
                city_options[normalized_city] = value
        
        logger.info(f"Cidades disponíveis para {estado}: {available_cities}")
        
        # Busca exata primeiro
        if alvo in city_options:
            logger.info(f"Encontrada correspondência exata: '{alvo}' -> código {city_options[alvo]}")
            return city_options[alvo]
        
        # Se não encontrou exata, tenta busca parcial (contém)
        for city_name, city_code in city_options.items():
            if alvo in city_name:
                logger.info(f"Encontrada correspondência parcial: '{city_name}' para '{alvo}' -> código {city_code}")
                return city_code
        
        # Se ainda não encontrou, tenta busca reversa (cidade contida no nome buscado)
        for city_name, city_code in city_options.items():
            if city_name in alvo:
                logger.info(f"Encontrada correspondência reversa: '{city_name}' para '{alvo}' -> código {city_code}")
                return city_code
        
        # Fallback para mapeamento conhecido
        override = CITY_CODE_OVERRIDES.get((estado, alvo))
        if override:
            logger.info(f"Usando fallback de código de cidade para {estado}/{alvo}: {override}")
            return override
        
        # Mostrar cidades disponíveis para ajudar na correção
        logger.error(f"Cidade '{nome_cidade}' não encontrada para estado {estado}")
        logger.error(f"Cidades disponíveis: {', '.join(available_cities)}")
        raise ValueError(f"Cidade '{nome_cidade}' não encontrada para estado {estado}. Cidades disponíveis: {', '.join(available_cities)}")

    @log_method
    def _obter_bairros(self, estado: str, cod_cidade: str) -> List[str]:
        """Consulta carregaListaBairros.asp e alimenta o parser com a lista de bairros (opcional)."""
        self._init_session()
        payload = {
            "cmb_estado": estado,
            "cmb_cidade": cod_cidade,
            "hdn_bairro": "",
            "cmb_tp_venda": "",
            "cmb_tp_imovel": "",
            "cmb_area_util": "",
            "cmb_faixa_vlr": "",
            "cmb_quartos": "",
            "cmb_vg_garagem": "",
            "strValorSimulador": "",
            "strAceitaFGTS": "",
            "strAceitaFinanciamento": "",
        }
        r = self._post(URL_BAIRROS, payload)
        soup = BeautifulSoup(r.text, 'html.parser')
        bairros = []
        # Os labels carregam o nome legível
        for lab in soup.find_all('label'):
            t = self._norm(lab.get_text(" "))
            if t and len(t) > 2 and t != "SELECIONE":
                bairros.append(t)
        # Remover duplicados e ordenar
        bairros = sorted(list(set(bairros)))
        self.parser.update_bairros_disponiveis(bairros)
        logger.info(f"✅ Bairros detectados: {len(bairros)}")
        return bairros

    @log_method
    def _iniciar_pesquisa(self, estado: str, cod_cidade: str) -> str:
        """Chama carregaPesquisaImoveis.asp e retorna o HTML com hdnImovN e metadados."""
        self._init_session()
        payload = {
            "hdn_estado": estado,
            "hdn_cidade": cod_cidade,
            "hdn_bairro": "",  # todos
            "hdn_tp_venda": "",  # modalidade indiferente
            "hdn_tp_imovel": "",
            "hdn_area_util": "",
            "hdn_faixa_vlr": "",
            "hdn_quartos": "",
            "hdn_vg_garagem": "",
            "strValorSimulador": "",
            "strAceitaFGTS": "",
            "strAceitaFinanciamento": "",
        }
        r = self._post(URL_PESQUISA, payload)
        return r.text

    def _extrair_ids_e_paginacao(self, html: str) -> Tuple[Dict[int, str], int, int]:
        """Extrai hdnImovN (por página), total de páginas e total de registros."""
        soup = BeautifulSoup(html, 'html.parser')
        ids_por_pagina: Dict[int, str] = {}
        total_paginas = 1
        total_registros = 0

        # hdnQtdPag, hdnQtdRegistros
        try:
            total_pag_elem = soup.find(id="hdnQtdPag")
            if total_pag_elem and total_pag_elem.get('value'):
                total_paginas = int(total_pag_elem.get('value'))
        except Exception:
            pass
        try:
            total_reg_elem = soup.find(id="hdnQtdRegistros")
            if total_reg_elem and total_reg_elem.get('value'):
                total_registros = int(total_reg_elem.get('value'))
        except Exception:
            pass

        # hdnImov1..N
        for inp in soup.find_all('input'):
            iid = inp.get('id') or ''
            if iid.startswith('hdnImov'):
                try:
                    idx = int(iid.replace('hdnImov', ''))
                    ids_por_pagina[idx] = (inp.get('value') or '').strip()
                except Exception:
                    continue
        return ids_por_pagina, total_paginas, total_registros

    @log_method
    def _carregar_pagina_fragmento(self, ids_da_pagina: str) -> str:
        """Chama carregaListaImoveis.asp e retorna o HTML (fragmento) dessa página."""
        payload = {"hdnImov": ids_da_pagina}
        r = self._post(URL_LISTA, payload)
        return r.text

    def debug_save_html(self, html_content, filename="debug_page.html"):
        """Salva HTML para debug"""
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info(f"HTML salvo para debug: {filename}")

    @log_method
    def extract_properties_from_page(self, html_content):
        """Extrai todos os imóveis de uma página de resultados (usa o parser intacto)."""
        return self.html_extractor.extract_properties_from_page(html_content)

    @log_method
    def scrape_all_properties(self):
        """Fluxo principal HTTP: navega por todas as páginas e extrai os imóveis."""
        self._init_session()

        # 1) Descobrir código da cidade e bairros (opcional, para melhorar parser)
        cod_cidade = self._obter_codigo_cidade(self.estado, self.cidade)
        try:
            self._obter_bairros(self.estado, cod_cidade)
        except Exception as e:
            logger.warning(f"Falha ao obter bairros: {e}")

        # 2) Iniciar pesquisa e extrair metadados/paginação/ids
        html_inicio = self._iniciar_pesquisa(self.estado, cod_cidade)
        self.debug_save_html(html_inicio, "debug_results_http.html")
        ids_por_pagina, total_paginas, total_registros = self._extrair_ids_e_paginacao(html_inicio)

        if not ids_por_pagina:
            logger.warning("Não foram encontrados IDs de imóveis por página (hdnImovN)")

        logger.info("📊 Paginação detectada:")
        logger.info(f"   Total de páginas: {total_paginas}")
        logger.info(f"   Total de imóveis (site): {total_registros}")

        # 3) Iterar páginas via endpoint carregaListaImoveis.asp
        all_properties = []
        for page_num in tqdm(range(1, total_paginas + 1), desc="Páginas", unit="pág"):
            ids = ids_por_pagina.get(page_num, "")
            if not ids:
                logger.warning(f"Sem IDs para a página {page_num}, pulando...")
                continue

            frag = self._carregar_pagina_fragmento(ids)
            # O endpoint retorna apenas o innerHTML. Envolver para o parser atual reconhecer
            wrapped_html = f"<div id='listaimoveispaginacao'>{frag}</div>"
            properties = self.extract_properties_from_page(wrapped_html)
            all_properties.extend(properties)
            time.sleep(self.delay_between_requests)

        self.scraped_properties = all_properties
        logger.info(f"Total de imóveis extraídos: {len(self.scraped_properties)}")
        return self.scraped_properties

    # --- Mantém utilidades de exportação e resumo ---
    @log_method
    def save_to_csv(self, filename=None):
        """Salva os dados extraídos em CSV"""
        if not self.scraped_properties:
            logger.warning("Nenhum dado para salvar")
            return None

        if filename is None:
            filename = f"imoveis_{self.estado.lower()}_{self.cidade.lower().replace(' ', '_')}.csv"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename_with_timestamp = f"{filename.replace('.csv', '')}_{timestamp}.csv"

        # Converter para DataFrame
        df = pd.DataFrame(self.scraped_properties)

        # Salvar CSV
        df.to_csv(filename_with_timestamp, index=False, encoding='utf-8')

        return filename_with_timestamp

    @log_method
    def save_to_json(self, filename=None):
        """Salva os dados extraídos em JSON"""
        if not self.scraped_properties:
            logger.warning("Nenhum dado para salvar")
            return None

        if filename is None:
            filename = f"imoveis_{self.estado.lower()}_{self.cidade.lower().replace(' ', '_')}.json"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename_with_timestamp = f"{filename.replace('.json', '')}_{timestamp}.json"

        # Preparar dados para JSON
        export_data = {
            'timestamp': datetime.now().isoformat(),
            'total_properties': len(self.scraped_properties),
            'search_parameters': self.search_params,
            'properties': self.scraped_properties
        }

        # Salvar JSON
        with open(filename_with_timestamp, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        return filename_with_timestamp

    def print_summary(self):
        """Exibe resumo dos dados extraídos"""
        if not self.scraped_properties:
            print("Nenhum dado extraído.")
            return

        print(f"\n=== RESUMO DA EXTRAÇÃO ===")
        print(f"Total de imóveis: {len(self.scraped_properties)}")

        # Estatísticas básicas
        properties_with_value = [p for p in self.scraped_properties if p.get('valor')]
        properties_with_address = [p for p in self.scraped_properties if p.get('endereco')]
        properties_with_area = [p for p in self.scraped_properties if p.get('area')]

        print(f"Com valor preenchido: {len(properties_with_value)}")
        print(f"Com endereço preenchido: {len(properties_with_address)}")
        print(f"Com área preenchida: {len(properties_with_area)}")

        # Mostrar algumas amostras
        print(f"\n=== AMOSTRAS DOS DADOS ===")
        for i, prop in enumerate(self.scraped_properties[:3]):
            print(f"\nImóvel {i+1}:")
            print(f"  Código: {prop.get('codigo')}")
            print(f"  Endereço: {prop.get('endereco')}")
            print(f"  Valor: {prop.get('valor')}")
            print(f"  Área: {prop.get('area')}")