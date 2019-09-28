import configparser

_config = configparser.ConfigParser()

_config.read('config.ini')

_bot_config = _config['bot']
bot_token = _bot_config.get('token')
log_file = _bot_config.get('log_file')
