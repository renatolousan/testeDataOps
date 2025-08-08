import logging
import sys
import time
from functools import wraps
from datetime import datetime


def setup_logger(name="scraper_caixa", log_file="scraper_caixa.log", level=logging.INFO):
    logger = logging.getLogger(name)
 
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger


def log_method(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        logger = getattr(self, 'logger', logging.getLogger('scraper_caixa'))
        
        method_name = func.__name__
        class_name = self.__class__.__name__
        
        if args or kwargs:
            params = []
            if args:
                params.extend([str(arg)[:50] for arg in args])
            if kwargs:
                params.extend([f"{k}={str(v)[:50]}" for k, v in kwargs.items()])
            params_str = f" com parâmetros: {', '.join(params)}" if params else ""
        else:
            params_str = ""
            
        logger.info(f"🔄 Iniciando {class_name}.{method_name}{params_str}")
        
        try:
            
            start_time = time.time()
            result = func(self, *args, **kwargs)
            duration = time.time() - start_time
            
            if result is not None:
                if isinstance(result, (list, dict)):
                    result_info = f" - Retornou {len(result)} itens" if hasattr(result, '__len__') else ""
                elif isinstance(result, bool):
                    result_info = f" - Status: {'✓ Sucesso' if result else '✗ Falha'}"
                else:
                    result_info = f" - Resultado: {str(result)[:50]}"
            else:
                result_info = ""
                
            logger.info(f"✅ Concluído {class_name}.{method_name} em {duration:.2f}s{result_info}")
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ Erro em {class_name}.{method_name} após {duration:.2f}s: {e}")
            raise
            
    return wrapper


def log_progress(current, total, item_name="item"):
    logger = logging.getLogger('scraper_caixa')
    percentage = (current / total) * 100 if total > 0 else 0
    logger.info(f"📈 Progresso: {current}/{total} {item_name}s ({percentage:.1f}%)")


def log_summary(data, title="Resumo"):
    logger = logging.getLogger('scraper_caixa')
    logger.info(f"📊 {title}:")
    for key, value in data.items():
        logger.info(f"   {key}: {value}")


def log_section(title):
    logger = logging.getLogger('scraper_caixa')
    separator = "=" * 50
    logger.info(f"\n{separator}")
    logger.info(f"{title}")
    logger.info(separator)


def configure_verbose_logging():
    logger = logging.getLogger('scraper_caixa')
    logger.setLevel(logging.DEBUG)
    
    for handler in logger.handlers:
        handler.setLevel(logging.DEBUG)
    
    logger.debug("🔍 Logging verbose ativado")
