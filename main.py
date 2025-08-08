import argparse
from logger_config import setup_logger
from script import CaixaScraper

logger = setup_logger(name="main", log_file="scraper_caixa.log")


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Scraper de Imóveis CAIXA - Extrai imóveis por estado e cidade',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  python main.py                             
  python main.py --estado RJ --cidade "RIO DE JANEIRO"
  python main.py -e MG -c "BELO HORIZONTE"
  python main.py --list-cities -e AM         
  python main.py --help                      
        """
    )
    
    parser.add_argument(
        '--estado', '-e',
        default='SP',
        help='Estado para busca (padrão: SP)'
    )
    
    parser.add_argument(
        '--cidade', '-c',
        default='SAO PAULO',
        help='Cidade para busca (padrão: SAO PAULO)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Ativa logs mais detalhados'
    )
    
    parser.add_argument(
        '--list-cities', '-l',
        action='store_true',
        help='Lista todas as cidades disponíveis para o estado especificado e sai'
    )
    
    return parser.parse_args()


def main():
    args = parse_arguments()
    
    if args.verbose:
        from logger_config import configure_verbose_logging
        configure_verbose_logging()
    
    
    if args.list_cities:
        print(f"=== CIDADES DISPONÍVEIS PARA {args.estado} ===")
        try:
            scraper = CaixaScraper(estado=args.estado, cidade="")  
            cities = scraper.list_available_cities(args.estado)
            if cities:
                print(f"Encontradas {len(cities)} cidades:")
                for i, city in enumerate(cities, 1):
                    print(f"  {i:2d}. {city}")
            else:
                print("Nenhuma cidade encontrada para este estado.")
        except Exception as e:
            print(f"Erro ao buscar cidades: {e}")
        return
    
    print("=== SCRAPER FOCADO - IMÓVEIS CAIXA ===")
    print(f"Estado: {args.estado}")
    print(f"Cidade: {args.cidade}")
    print("URL: https://venda-imoveis.caixa.gov.br/sistema/busca-imovel.asp?sltTipoBusca=imoveis")
    print()
    
    logger.info(f"=== INICIANDO SCRAPER CAIXA - {args.estado}/{args.cidade} ===")
    
    scraper = CaixaScraper(estado=args.estado, cidade=args.cidade)
    
    try:
        imoveis = scraper.scrapeImoveis()
        
        if imoveis:
            csv_file = scraper.export_CSV()
            json_file = scraper.export_JSON()
            
            scraper.print_resumo()
            
            print(f"\n=== ARQUIVOS GERADOS ===")
            print(f"CSV: {csv_file}")
            print(f"JSON: {json_file}")
            
            logger.info("=== SCRAPER CONCLUÍDO COM SUCESSO ===")
            
        else:
            logger.warning("Nenhum imóvel extraído")
        
    except KeyboardInterrupt:
        logger.info("Execução interrompida pelo usuário")
    except Exception as e:
        logger.error(f"Erro durante execução: {e}")
        print(f"Erro: {e}")
        raise


if __name__ == "__main__":
    main()
