from pydantic_settings import BaseSettings


class SmppSettings(BaseSettings):
    ''' The default settings are from a free SMSC simulator service
    https://smpp.org/smpp-testing-development.html
    '''
    smsc_host: str = 'smscsim.smpp.org'
    smsc_port: int = 2775
    smsc_system_id: str = 'gs4ITii6wu1kJBL'
    smsc_password: str = 'FpSK3c4c'
    source_addr: str = ''

    class Config:
        """Load config"""

        env_file = "secrets.env"