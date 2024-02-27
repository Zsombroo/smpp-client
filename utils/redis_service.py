from redis import Redis

from settings import SmppSettings


class RedisService(Redis):
    def __init__(self, settings: SmppSettings):
        super().__init__(
            host=settings.redis_host,
            port=settings.redis_port,
        )
        self.settings = settings
        
redis = RedisService(SmppSettings())