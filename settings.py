from pydantic_settings import BaseSettings


class SmppSettings(BaseSettings):
    ''' The default settings are from a free SMSC simulator service
    https://smpp.org/smpp-testing-development.html
    '''
    servername: str = ''
    app_name: str = 'SMPP ESME'

    smsc_host: str = 'smscsim.smpp.org'
    smsc_port: int = 2775
    smsc_system_id: str = 'gs4ITii6wu1kJBL'
    smsc_password: str = 'FpSK3c4c'
    source_addr: str = ''

    listening_host: str = '0.0.0.0'
    listening_port: int = 8383

    redis_host: str = 'localhost'
    redis_port: int = 6379
    redis_password: str = ''
    redis_sent_key: str = 'smpp:is_sent'
    redis_delivered_key: str = 'smpp:is_delivered'

    log_path: str = ''

    class Config:
        """Load config"""

        env_file = "secrets.env"


settings = SmppSettings()
