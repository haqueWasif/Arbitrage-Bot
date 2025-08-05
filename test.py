import asyncio
from binance import AsyncClient
import sys
import platform


if platform.system() == "Windows":
    if sys.version_info >= (3, 8):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def main():
    client = await AsyncClient.create(
       "0whRWTBAZBTErloICqyPdGrfzUyjYLBrChW9DhjdLTyPeZpfi53giGT37pGkI95",
       "Ovys0hvsYuTpCAnu7egsdDKT4CfmTdPMwrYAQSCaY1DvfdAGZnsyMaE246HjAXC4",
        testnet=True
    )
    pong = await client.ping()
    print("Ping:", pong)
    await client.close_connection()

if __name__ == "__main__":
    asyncio.run(main())
