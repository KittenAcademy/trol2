import logging

def setup_logger(name):
    # Create a logger with the given name
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO) 

    # Add a console handler only if it hasn't been added yet
    if not logger.handlers:
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger

def is_debug(log):
    return log.level == logging.DEBUG
def set_info(log):
    log.setLevel(logging.INFO)
def set_debug(log):
    log.setLevel(logging.DEBUG)

INFO=logging.INFO
DEBUG=logging.DEBUG
WARNING=logging.WARNING
ERROR=logging.ERROR
