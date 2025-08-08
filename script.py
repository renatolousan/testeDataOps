import time
import json
import pandas as pd
from fake_useragent import UserAgent
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from logger_config import setup_logger, log_method
from parser import CaixaPropertyParser, CaixaHtmlExtractor
logger = setup_logger(name="scraper_caixa", log_file="scraper_caixa.log")

class CaixaScraperSP:

    def __init__(self, estado="SP", cidade="SAO PAULO"):
        self.base_url = "https://venda-imoveis.caixa.gov.br"
        self.search_url = f"{self.base_url}/sistema/busca-imovel.asp"
        self.ua = UserAgent()
        self.delay_between_requests = 2  # segundos
        self.scraped_properties = []
        self.driver = None
        
        # Configurar logger para esta instância
        self.logger = logger
        
        # Inicializar parser e extrator
        self.parser = CaixaPropertyParser()
        self.html_extractor = CaixaHtmlExtractor(self.parser)
        
        # Parâmetros configuráveis
        self.estado = estado
        self.cidade = cidade
        self.search_params = {
            'sltTipoBusca': 'imoveis',
            'sltEstado': estado,
            'sltCidade': cidade
        }
        
        logger.info(f"Scraper configurado para Estado: {estado}, Cidade: {cidade}")
    
    @log_method
    def setup_selenium(self):
        """Configura o driver do Selenium"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(f"--user-agent={self.ua.random}")
        
        # Usar WebDriver Manager
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        
        return True
    
    @log_method
    def extract_bairros_disponiveis(self):
        """Extrai a lista de bairros disponíveis do elemento #listabairros"""
        return self.html_extractor.extract_bairros_from_html(self.driver)
    
    @log_method
    def navigate_to_results_with_selenium(self):

        url = f"{self.search_url}?sltTipoBusca=imoveis"
        self.driver.get(url)
        
        # Aguardar carregamento
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Preencher Estado
        logger.info(f"Selecionando estado {self.estado}...")
        estado_select = Select(self.driver.find_element(By.NAME, "cmb_estado"))
        estado_select.select_by_value(self.estado)
        time.sleep(3)  # Aguardar carregamento das cidades
        
        # Listar opções de cidade disponíveis
        logger.info("Listando cidades disponíveis...")
        cidade_select = Select(self.driver.find_element(By.NAME, "cmb_cidade"))
        options = cidade_select.options
        for option in options[:10]:  # Mostrar primeiras 10
            logger.info(f"Cidade opção: value='{option.get_attribute('value')}' text='{option.text}'")
        
        # Buscar e selecionar a cidade especificada
        cidade_found = False
        for option in options:
            if option.text == self.cidade:
                logger.info(f"Selecionando cidade: {option.text}")
                cidade_select.select_by_visible_text(option.text)
                cidade_found = True
                break
        
        if not cidade_found:
            raise Exception(f"Cidade '{self.cidade}' não encontrada nas opções disponíveis")
        
        time.sleep(2)
        
        # Extrair bairros disponíveis após selecionar estado e cidade
        logger.info("Extraindo lista de bairros disponíveis...")
        self.extract_bairros_disponiveis()
        
        # Clicar no botão "Próximo" - com tratamento para overlays
        logger.info("Clicando no botão Próximo...")
        try:
            # Primeiro, tentar fechar qualquer modal/overlay que possa estar aberto
            overlays = self.driver.find_elements(By.CLASS_NAME, "ui-widget-overlay")
            if overlays:
                logger.info("Detectado overlay, tentando fechar...")
                # Tentar clicar fora do overlay ou pressionar ESC
                self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                time.sleep(1)
            
            # Tentar diferentes estratégias para clicar no botão
            next_button = self.driver.find_element(By.ID, "btn_next0")
            
            # Estratégia 1: Scroll até o elemento e clique normal
            self.driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
            time.sleep(1)
            next_button.click()
            
        except Exception as click_error:
            logger.warning(f"Clique normal falhou: {click_error}")
            try:
                # Estratégia 2: JavaScript click
                logger.info("Tentando clique via JavaScript...")
                next_button = self.driver.find_element(By.ID, "btn_next0")
                self.driver.execute_script("arguments[0].click();", next_button)
                
            except Exception as js_error:
                logger.warning(f"Clique JavaScript falhou: {js_error}")
                try:
                    # Estratégia 3: Aguardar elemento ser clicável
                    logger.info("Aguardando elemento ser clicável...")
                    next_button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.ID, "btn_next0"))
                    )
                    next_button.click()
                    
                except Exception as wait_error:
                    logger.error(f"Todas as estratégias de clique falharam: {wait_error}")
                    raise
        
        # Aguardar transição para próxima etapa
        time.sleep(3)
        
        # Verificar se há um segundo "Próximo" ou botão de busca
        try:
            # Procurar por botões na segunda etapa
            buttons = self.driver.find_elements(By.XPATH, "//button[contains(@class, 'submit')]")
            for button in buttons:
                button_text = button.text.lower()
                if any(word in button_text for word in ['próximo', 'buscar', 'pesquisar']):
                    logger.info(f"Clicando no botão: {button.text}")
                    button.click()
                    time.sleep(3)
                    break
        except Exception as e:
            logger.info(f"Não foi possível encontrar botão adicional: {e}")
        
        # Obter HTML da página de resultados
        page_source = self.driver.page_source
        
        # Salvar para debug
        self.debug_save_html(page_source, "debug_results_selenium.html")
        
        return page_source
    
    @log_method
    def close_selenium(self):
        """Fecha o driver do Selenium"""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def debug_save_html(self, html_content, filename="debug_page.html"):
        """Salva HTML para debug"""
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info(f"HTML salvo para debug: {filename}")
    
    @log_method
    def extract_properties_from_page(self, html_content):
        """Extrai todos os imóveis de uma página de resultados"""
        return self.html_extractor.extract_properties_from_page(html_content)
    
    @log_method
    def get_pagination_info_selenium(self):
        """Obtém informações de paginação usando Selenium"""
        # Buscar campos ocultos com informações de paginação
        total_pages_element = self.driver.find_element(By.ID, "hdnQtdPag")
        current_page_element = self.driver.find_element(By.ID, "hdnPagNum")
        total_properties_element = self.driver.find_element(By.ID, "hdnQtdRegistros")
        
        pagination_info = {
            'total_pages': int(total_pages_element.get_attribute('value')),
            'current_page': int(current_page_element.get_attribute('value')),
            'total_properties': int(total_properties_element.get_attribute('value'))
        }
        
        return pagination_info
    
    @log_method
    def navigate_to_next_page_selenium(self, page_number):
        """Navega para uma página específica usando Selenium"""
        # A CAIXA usa a função JavaScript carregaListaImoveis(page_number)
        script = f"carregaListaImoveis({page_number});"
        logger.info(f"🔄 Executando: {script}")
        
        self.driver.execute_script(script)
        time.sleep(3)  # Aguardar carregamento da página
        
        # Verificar se a página mudou verificando o hdnPagNum
        current_page_element = self.driver.find_element(By.ID, "hdnPagNum")
        actual_page = int(current_page_element.get_attribute('value'))
        
        if actual_page == page_number:
            logger.info(f"✓ Navegação bem-sucedida para página {page_number}")
            return True
        else:
            logger.warning(f"⚠️ Página esperada: {page_number}, página atual: {actual_page}")
            return False

    @log_method
    def scrape_all_properties(self):
        """Método principal para extrair todos os imóveis"""
        properties = self.navigate_with_selenium_all_pages()
        logger.info(f"Total de imóveis extraídos: {len(self.scraped_properties)}")
        return self.scraped_properties
    
    @log_method
    def navigate_with_selenium_all_pages(self):
        """Navega por todas as páginas e extrai todos os imóveis usando Selenium"""
        self.setup_selenium()
        if not self.driver:
            return []
        
        all_properties = []
        
        try:
            # Navegar para a primeira página de resultados
            success = self.navigate_to_results_with_selenium()
            
            if not success:
                raise Exception("Falha ao navegar para a página de resultados")
            
            # Extrair da primeira página
            current_html = self.driver.page_source
            properties = self.extract_properties_from_page(current_html)
            all_properties.extend(properties)
            
            # Obter informações de paginação
            pagination_info = self.get_pagination_info_selenium()
            if not pagination_info:
                logger.warning("Não foi possível obter informações de paginação")
                return all_properties
            
            current_page = pagination_info['current_page']
            total_pages = pagination_info['total_pages']
            total_properties = pagination_info['total_properties']
            
            logger.info(f"📊 Paginação detectada:")
            logger.info(f"   Página atual: {current_page}")
            logger.info(f"   Total de páginas: {total_pages}")
            logger.info(f"   Total de imóveis: {total_properties}")
            
            # Navegar pelas páginas restantes
            for page_num in range(2, total_pages + 1):
                logger.info(f"🔄 Navegando para página {page_num}/{total_pages}...")
                
                success = self.navigate_to_next_page_selenium(page_num)
                if not success:
                    logger.warning(f"Falha ao navegar para página {page_num}")
                    break
                
                time.sleep(2)
                
                current_html = self.driver.page_source
                properties = self.extract_properties_from_page(current_html)
                all_properties.extend(properties)
                
                logger.info(f"✓ Página {page_num}: {len(properties)} imóveis extraídos")
                logger.info(f"📈 Total acumulado: {len(all_properties)} imóveis")
                
                time.sleep(1)
                
                if len(all_properties) >= total_properties:
                    logger.info(f"Coletados {len(all_properties)} imóveis")
                    break
        
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("Driver selenium parou de rodar (driver.quit())")
        
        self.scraped_properties = all_properties
        return all_properties

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
        properties_with_value = [p for p in self.scraped_properties if p['valor']]
        properties_with_address = [p for p in self.scraped_properties if p['endereco']]
        properties_with_area = [p for p in self.scraped_properties if p['area']]
        
        print(f"Com valor preenchido: {len(properties_with_value)}")
        print(f"Com endereço preenchido: {len(properties_with_address)}")
        print(f"Com área preenchida: {len(properties_with_area)}")
        
        # Mostrar algumas amostras
        print(f"\n=== AMOSTRAS DOS DADOS ===")
        for i, prop in enumerate(self.scraped_properties[:3]):
            print(f"\nImóvel {i+1}:")
            print(f"  Código: {prop['codigo']}")
            print(f"  Endereço: {prop['endereco']}")
            print(f"  Valor: {prop['valor']}")
            print(f"  Área: {prop['area']}")