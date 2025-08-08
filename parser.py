import re
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class CaixaPropertyParser:
    def __init__(self, bairros_disponiveis=None):
        self.bairros_disponiveis = bairros_disponiveis or []
    
    def update_bairros_disponiveis(self, bairros_list):
        self.bairros_disponiveis = bairros_list or []
    
    def detect_bairro_from_endereco(self, endereco):
        if not endereco:
            logger.debug("Endereço está vazio")
            return ""
        
        endereco_upper = endereco.upper()
        logger.debug(f"Procurando bairro em: {endereco_upper}")
        
        
        if not self.bairros_disponiveis:
            logger.debug("Lista de bairros está vazia, usando detecção por padrões")
            return self.detect_bairro_by_patterns(endereco_upper)
        
        logger.debug(f"Total de bairros disponíveis: {len(self.bairros_disponiveis)}")
        
        
        bairros_ordenados = sorted(self.bairros_disponiveis, key=len, reverse=True)
        
        for bairro in bairros_ordenados:
            if bairro in endereco_upper:
                logger.debug(f"Bairro '{bairro}' encontrado no endereço: {endereco[:50]}...")
                return bairro
        
        
        bairro_pattern = self.detect_bairro_by_patterns(endereco_upper)
        if bairro_pattern:
            logger.debug(f"Bairro detectado por padrão: {bairro_pattern}")
            return bairro_pattern
        
        logger.debug(f"Nenhum bairro encontrado no endereço: {endereco[:50]}...")
        return ""
    
    def detect_bairro_by_patterns(self, endereco_upper):        
        parts = endereco_upper.split(',')
        if len(parts) >= 2:
            last_part = parts[-1].strip()
            
            if len(last_part) > 4 and last_part.isalpha():
                return last_part
        
        
        
        parts_hyphen = endereco_upper.split(' - ')
        if len(parts_hyphen) >= 2:
            
            potential_bairro = parts_hyphen[-2].strip()
            if len(potential_bairro) > 4 and potential_bairro.isalpha():
                return potential_bairro
        
        
        prefixos_bairro = ['VILA ', 'CIDADE ', 'JARDIM ', 'PARQUE ', 'CONJUNTO ']
        for prefixo in prefixos_bairro:
            if prefixo in endereco_upper:
                
                start_pos = endereco_upper.find(prefixo)
                rest_text = endereco_upper[start_pos:].split(',')[0].split(' - ')[0]
                if len(rest_text) > len(prefixo) + 3:  
                    return rest_text.strip()
        
        return ""
    
    def parse_property_from_row(self, row_cells):
        property_data = {
            'codigo': '',
            'endereco': '',
            'bairro': '',
            'modalidade': '',
            'valor': '',
            'area': '',
            'quartos': '',
            'garagem': '',
            'raw_data': ' | '.join(row_cells)
        }
        
        
        for i, cell in enumerate(row_cells):
            cell_lower = cell.lower().strip()
            
            
            if i == 0 and cell.strip():
                property_data['codigo'] = cell.strip()
            
            
            if 'r$' in cell_lower:
                property_data['valor'] = cell.strip()
            
            
            if 'm²' in cell_lower or 'm2' in cell_lower:
                property_data['area'] = cell.strip()
            
            
            if any(word in cell_lower for word in ['rua', 'av ', 'avenida', 'alameda', 'travessa']):
                property_data['endereco'] = cell.strip()
            
            
            if any(word in cell_lower for word in ['quarto', 'dorm', 'qto']):
                property_data['quartos'] = cell.strip()
                
        return property_data
    
    def extract_property_from_caixa_item(self, item_element):
        try:
            property_data = {
                'codigo': '',
                'titulo': '',
                'endereco': '',
                'bairro': '',
                'modalidade': '',
                'valor': '',
                'area': '',
                'quartos': '',
                'tipo_imovel': '',
                'numero_item': ''
            }
            
            
            title_element = None
            strong_elements = item_element.find_all('strong')
            
            
            for strong in strong_elements:
                text = strong.get_text(strip=True)
                
                if (text and 
                    not text.lower().startswith('tempo restante') and
                    not text.lower().startswith('número do item') and
                    not text.lower().startswith('despesas') and
                    len(text) > 10):  
                    title_element = strong
                    break
            
            
            if not title_element and strong_elements:
                title_element = strong_elements[0]
            
            if title_element:
                title_text = title_element.get_text(strip=True)
                
                
                if (title_text.lower().startswith('tempo restante') or 
                    title_text.lower().startswith('número do item')):
                    
                    
                    
                    link_elements = item_element.find_all('a')
                    for link in link_elements:
                        link_text = link.get_text(strip=True)
                        if (link_text and len(link_text) > 10 and 
                            not link_text.lower().startswith('tempo restante')):
                            title_text = link_text
                            break
                
                
                if '|' in title_text:
                    titulo_limpo = title_text.split('|')[0].strip()
                    property_data['titulo'] = titulo_limpo
                    
                    
                    if 'R$' in title_text:
                        parts = title_text.split('|')
                        if len(parts) >= 2:
                            property_data['valor'] = parts[-1].strip()
                else:
                    
                    property_data['titulo'] = title_text
            
            
            all_text = item_element.get_text()
            logger.debug(f"Texto completo do item: {all_text[:200]}...")
            
            
            self._extract_numero_item(all_text, property_data)
            self._extract_codigo_imovel(all_text, property_data)
            self._extract_endereco(all_text, property_data)
            self._extract_technical_info(all_text, property_data)
            
            
            if property_data['endereco']:
                bairro_detectado = self.detect_bairro_from_endereco(property_data['endereco'])
                if bairro_detectado:
                    property_data['bairro'] = bairro_detectado
                    logger.debug(f"Bairro detectado: {bairro_detectado}")
            
            return property_data if property_data['titulo'] else None
            
        except Exception as e:
            logger.error(f"Erro ao extrair imóvel: {e}")
            return None
    
    def _extract_numero_item(self, all_text, property_data):
        numero_item_match = re.search(r'número do item:\s*(\d+)', all_text, re.IGNORECASE)
        if numero_item_match:
            property_data['numero_item'] = numero_item_match.group(1)
            logger.debug(f"Número do item encontrado: {property_data['numero_item']}")
    
    def _extract_codigo_imovel(self, all_text, property_data):
        codigo_match = re.search(r'número do imóvel:\s*([0-9\-]+)', all_text, re.IGNORECASE)
        if codigo_match:
            property_data['codigo'] = codigo_match.group(1).strip()
            logger.debug(f"Código encontrado: {property_data['codigo']}")
    
    def _extract_endereco(self, all_text, property_data):
        lines = all_text.split('\n')
        endereco_encontrado = False
        
        
        for i, line in enumerate(lines):
            line_clean = line.strip()
            if 'número do item:' in line_clean.lower():
                
                for j in range(i + 1, len(lines)):
                    next_line = lines[j].strip()
                    if next_line and not next_line.lower().startswith('despesas'):
                        
                        endereco_limpo = self._clean_endereco(next_line)
                        if endereco_limpo:
                            property_data['endereco'] = endereco_limpo
                            logger.debug(f"Endereço encontrado: {endereco_limpo}")
                            endereco_encontrado = True
                            break
                break
        
        
        if not endereco_encontrado:
            endereco_patterns = [
                
                r'Número do imóvel:\s*[0-9\-]+\s*(.+?)(?:\s*$|despesas)',
                
                r'((?:RUA|AVENIDA|AV|ALAMEDA|TRAVESSA|PRAÇA)[^<\n]+?)(?:\s*<|\s*despesas)',
                
                r'número do item:\s*\d+[^<\n]*?([^<\n]+?)(?:\s*despesas|$)',
            ]
            
            for pattern in endereco_patterns:
                endereco_match = re.search(pattern, all_text, re.IGNORECASE)
                if endereco_match:
                    endereco_bruto = endereco_match.group(1).strip()
                    endereco_limpo = self._clean_endereco(endereco_bruto)
                    if endereco_limpo and len(endereco_limpo) > 10:
                        property_data['endereco'] = endereco_limpo
                        logger.debug(f"Endereço via regex: {endereco_limpo}")
                        endereco_encontrado = True
                        break
    
    def _clean_endereco(self, endereco_bruto):
        if not endereco_bruto:
            return ""
        
        endereco = endereco_bruto.strip()
        
        
        endereco_patterns = [
            
            r'((?:RUA|AVENIDA|AV|ALAMEDA|TRAVESSA|PRAÇA)\s+[^,]+,\s*N\.\s*[^,]+(?:,\s*[^,]+)*)',
            
            r'((?:RUA|AVENIDA|AV|ALAMEDA|TRAVESSA|PRAÇA)[^,]+(?:,[^,]+)*?)(?:,\s*,|$)',
            
            r'((?:RUA|AVENIDA|AV|ALAMEDA|TRAVESSA|PRAÇA)[^$]+)',
        ]
        
        endereco_encontrado = None
        for pattern in endereco_patterns:
            match = re.search(pattern, endereco, re.IGNORECASE)
            if match:
                candidato = match.group(1).strip()
                
                if not re.search(r'avaliação|valor.*venda|desconto|apartamento.*quarto|venda direta|número do imóvel', candidato, re.IGNORECASE):
                    endereco_encontrado = candidato
                    break
                elif len(candidato) > 20:  
                    
                    sub_match = re.search(r'((?:RUA|AVENIDA|AV|ALAMEDA|TRAVESSA|PRAÇA)[^,]+(?:,[^,]+){0,2})', candidato, re.IGNORECASE)
                    if sub_match:
                        endereco_encontrado = sub_match.group(1).strip()
                        break
        
        if endereco_encontrado:
            endereco = endereco_encontrado
        else:
            
            
            padroes_a_remover = [
                r'avaliação:\s*R\$[^A-Z]*',
                r'Valor mínimo de venda:[^A-Z]*',
                r'desconto de[^A-Z]*',
                r'Apartamento\s*-\s*\d+\s*quarto\(s\)\s*-[^A-Z]*',
                r'Venda Direta Online[^A-Z]*',
                r'Número do imóvel:\s*[0-9\-]+\s*',
            ]
            
            for padrao in padroes_a_remover:
                endereco = re.sub(padrao, '', endereco, flags=re.IGNORECASE)
        
        
        endereco = re.sub(r'\s+', ' ', endereco).strip()
        
        
        endereco = re.sub(r',\s*,\s*$', '', endereco).strip()
        
        
        if len(endereco) > 150:
            
            match = re.search(r'^(.{50,120}),\s*,', endereco)
            if match:
                endereco = match.group(1).strip()
        
        return endereco
    
    def _extract_technical_info(self, all_text, property_data):
        lines = all_text.split('\n')
        
        for line in lines:
            line_lower = line.lower()

            if 'apartamento' in line_lower and 'm2' in line_lower:
                property_data['tipo_imovel'] = 'Apartamento'
                area_match = re.search(r'(\d+,?\d*)\s*m2', line)
                if area_match:
                    property_data['area'] = area_match.group(1) + ' m²'
            
            elif 'casa' in line_lower:
                property_data['tipo_imovel'] = 'Casa'
            
            quartos_match = re.search(r'(\d+)\s*quarto', line_lower)
            if quartos_match:
                property_data['quartos'] = quartos_match.group(1) + ' quartos'
            
            if 'leilão' in line_lower:
                property_data['modalidade'] = 'Leilão'
            elif 'venda direta' in line_lower:
                property_data['modalidade'] = 'Venda Direta'


class CaixaHtmlExtractor:
    
    def __init__(self, parser=None):
        self.parser = parser or CaixaPropertyParser()
    
    def extract_bairros_from_html(self, driver):
        try:
            
            import time
            time.sleep(2)
            
            from selenium.webdriver.common.by import By
            
            
            listabairros_element = driver.find_element(By.ID, "listabairros")
            
            
            bairro_elements = []
            
            
            try:
                elements = listabairros_element.find_elements(By.XPATH, ".//a | .//div | .//span | .//li")
                bairro_elements.extend(elements)
            except:
                pass
            
            
            try:
                elements = listabairros_element.find_elements(By.XPATH, ".//*[text()]")
                bairro_elements.extend(elements)
            except:
                pass
            
            
            if not bairro_elements:
                bairros_text = listabairros_element.text
                
                bairros_list = re.split(r'[\n,;|]', bairros_text)
                bairros = [b.strip().upper() for b in bairros_list if b.strip() and len(b.strip()) > 2]
            else:
                bairros = []
                for element in bairro_elements:
                    bairro_text = element.text.strip()
                    if bairro_text and len(bairro_text) > 2:  
                        bairros.append(bairro_text.upper())  
            
            
            bairros_disponiveis = sorted(list(set(bairros)))
            
            logger.info(f"Extraídos {len(bairros_disponiveis)} bairros disponíveis")
            if bairros_disponiveis:
                logger.debug(f"Primeiros 10 bairros: {bairros_disponiveis[:10]}")
            else:
                logger.warning("Nenhum bairro foi extraído")
            
            
            self.parser.update_bairros_disponiveis(bairros_disponiveis)
            
            return bairros_disponiveis
            
        except Exception as e:
            logger.warning(f"Não foi possível extrair bairros: {e}")
            
            try:
                
                possible_elements = driver.find_elements(By.XPATH, "//div[contains(@id, 'bairro') or contains(@class, 'bairro')]")
                for elem in possible_elements:
                    logger.debug(f"Elemento encontrado: {elem.get_attribute('id')} - {elem.text[:100]}")
            except:
                pass
            return []
    
    def extract_imoveis_da_pag(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        imoveis = []
        
        
        results_section = soup.find('div', id='listaimoveispaginacao')
        if results_section:
            logger.info("✓ Página de resultados encontrada!")
            
            
            property_items = results_section.find_all('li', class_='group-block-item')
            logger.info(f"Encontrados {len(property_items)} itens de imóvel")
            
            for i, item in enumerate(property_items):
                property_data = self.parser.extract_property_from_caixa_item(item)
                if property_data:
                    imoveis.append(property_data)
                    logger.info(f"Imóvel {i+1}: {property_data['titulo'][:50]}...")
        
        else:
            
            form_indicators = soup.find_all(string=re.compile(r'Selecione.*modalidade.*venda', re.IGNORECASE))
            if form_indicators:
                logger.warning("Ainda estamos na página do formulário")
                return []
            
            logger.warning("Estrutura de resultados não encontrada, tentando métodos alternativos...")
            imoveis = self._extract_from_fallback_methods(soup)
        
        logger.info(f"Extraídos {len(imoveis)} imóveis desta página")
        return imoveis
    
    def _extract_from_fallback_methods(self, soup):
        imoveis = []
        
        
        tables = soup.find_all('table')
        logger.info(f"Encontradas {len(tables)} tabelas na página")
        
        for i, table in enumerate(tables):
            rows = table.find_all('tr')
            logger.info(f"Tabela {i+1}: {len(rows)} linhas")
            
            
            for j, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:  
                    cell_texts = [cell.get_text(strip=True) for cell in cells]
                    row_text = ' '.join(cell_texts).lower()
                    
                    
                    if j < 3:  
                        logger.info(f"  Linha {j+1}: {cell_texts}")
                    
                    
                    has_property_indicators = any(keyword in row_text for keyword in [
                        'r$', 'real', 'reais', 'valor', 'preço',
                        'rua', 'av ', 'avenida', 'alameda', 'travessa',
                        'm²', 'm2', 'metro',
                        'apartamento', 'casa', 'imovel', 'imóvel',
                        'dorm', 'quarto', 'qto'
                    ])
                    
                    if has_property_indicators and len(cell_texts) >= 3:
                        property_data = self.parser.parse_property_from_row(cell_texts)
                        imoveis.append(property_data)
        
        
        if not imoveis:
            logger.info("Nenhum imóvel encontrado nas tabelas. Tentando outras estruturas...")
            
            
            divs = soup.find_all('div')
            for div in divs:
                text = div.get_text(strip=True)
                if len(text) > 50 and any(keyword in text.lower() for keyword in ['r$', 'rua', 'apartamento']):
                    logger.info(f"Possível imóvel em div: {text[:100]}...")
        
        return imoveis
