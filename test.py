from redis.asyncio import Redis

from settings import SmppSettings


settings = SmppSettings()




async def main():
    print(redis)
    await redis.set("foo", "bar")
    resp = await redis.get("foo")
    print(resp)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())