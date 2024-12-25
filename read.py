# read https://t.me/vienna_vape_channel/660

import json
from aiogram import Bot, types
from aiogram.types import FSInputFile
import asyncio
with open('config.json', 'r') as file:
    config = json.load(file)

bot = Bot(token=config['manager_bot_token'])

async def read_message(message_id):
    message = await bot.get_message(CHANNEL_ID, message_id)
    return message	

