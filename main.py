import argparse
from logger_config import setup_logger
from script import CaixaScraperSP

logger = setup_logger(name="main", log_file="scraper_caixa.log")


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Scraper de Imóveis CAIXA - Extrai imóveis por estado e cidade',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  python main.py                             # SP, SAO PAULO (padrão)
  python main.py --estado RJ --cidade "RIO DE JANEIRO"
  python main.py -e MG -c "BELO HORIZONTE"
  python main.py --list-cities -e AM         # Lista cidades disponíveis para AM
  python main.py --help                      # Mostra esta ajuda
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
    """Função principal da aplicação"""
    args = parse_arguments()
    
    if args.verbose:
        from logger_config import configure_verbose_logging
        configure_verbose_logging()
    
    # Se usuário quer listar cidades, fazer isso e sair
    if args.list_cities:
        print(f"=== CIDADES DISPONÍVEIS PARA {args.estado} ===")
        try:
            scraper = CaixaScraperSP(estado=args.estado, cidade="")  # cidade temporária
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
    
    scraper = CaixaScraperSP(estado=args.estado, cidade=args.cidade)
    
    try:
        properties = scraper.scrape_all_properties()
        
        if properties:
            csv_file = scraper.save_to_csv()
            json_file = scraper.save_to_json()
            
            scraper.print_summary()
            
            print(f"\n=== ARQUIVOS GERADOS ===")
            print(f"CSV: {csv_file}")
            print(f"JSON: {json_file}")
            
            logger.info("=== SCRAPER CONCLUÍDO COM SUCESSO ===")
            
        else:
            print("Nenhum imóvel foi extraído. Verifique os logs para mais detalhes.")
            logger.warning("Nenhum imóvel extraído")
        
    except KeyboardInterrupt:
        logger.info("Execução interrompida pelo usuário")
        print("\nExecução interrompida. Dados parciais podem ter sido salvos.")
    except Exception as e:
        logger.error(f"Erro durante execução: {e}")
        print(f"Erro: {e}")
        raise


if __name__ == "__main__":
    main()
