import asyncio
from eva.core import EVA

async def main():
    eva = EVA()
    await eva.arun()

if __name__ == "__main__":
    asyncio.run(main())
