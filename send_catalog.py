import asyncio
from aiogram import Bot, types
from aiogram.types import FSInputFile
import json
import os

# Load config
with open('config.json', 'r', encoding='utf-8') as file:
    config = json.load(file)

# Initialize bot with your token
bot = Bot(token=config['manager_bot_token'])
link_bot_start = "https://t.me/ViennVapebot?start=start"

# Channel ID where to send messages (replace with your channel ID)
CHANNEL_ID = -1002267350500  # e.g. "@mychannel" or "-100123456789"

# Add new variable for navigation message ID
navigation_message_id = None

async def send_price_list():
    price_list = "<b>💰 Прайс-лист</b>\n\n<blockquote>"
    for collection in config['catalog']['collections']:
        price_list += f"<b>{collection['name']}</b> - <code>{collection['price']}€💸</code>\n"
    
    price_list += "</blockquote>\n\n"
    price_msg = await bot.send_message(CHANNEL_ID, price_list, parse_mode="HTML")
    return price_msg.message_id  # Return message ID for linking

async def send_navigation_message(price_list_id):
    global navigation_message_id
    # Initial navigation message with price list link but without collection links
    nav_text = (
        "<b>📑 НАВИГАЦИЯ</b>\n\n"
        f"<a href='https://t.me/c/{str(CHANNEL_ID)[4:]}/{price_list_id}'>💰 ПРАЙС-ЛИСТ</a>\n\n"
        "<b>КОЛЛЕКЦИИ:</b>\n"
    )
    
    nav_msg = await bot.send_message(CHANNEL_ID, nav_text, parse_mode="HTML")
    navigation_message_id = nav_msg.message_id

async def send_catalog(price_list_id):
    message_ids = []  # Store message IDs and collection names
    for collection in config['catalog']['collections']:
        tastes = "\n".join([f"• {item['name']}" for item in collection['items']])
        message_text = (
            f"🆕 <b>{collection['name'].upper()}</b>\n\n"
            f"ℹ️ <b>О ТОВАРЕ</b>\n"
            f"<blockquote>{collection['description']}</blockquote>\n\n"
            f"🎯 <b>ДОСТУПНЫЕ ВКУСЫ</b>\n"
            f"<blockquote>{tastes}</blockquote>\n\n"
            f"💎 <b>ЦЕНА</b> <code>{collection['price']}€💸</code>\n\n"
        )
        
        try:
            image_path = f"images/{collection['id']}.jpeg"
            if os.path.exists(image_path):
                msg = await bot.send_photo(
                    CHANNEL_ID,
                    photo=FSInputFile(image_path),
                    caption=message_text,
                    parse_mode="HTML",
                    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                        [types.InlineKeyboardButton(text="↖️ Вернуться к навигации", url=f"https://t.me/c/{str(CHANNEL_ID)[4:]}/{navigation_message_id}")],
                        [types.InlineKeyboardButton(text="🛍 ЗАКАЗАТЬ", url=link_bot_start)]
                    ])
                )
            else:
                msg = await bot.send_message(
                    CHANNEL_ID, 
                    message_text, 
                    parse_mode="HTML",
                    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                        [types.InlineKeyboardButton(text="↖️ Вернуться к навигации", url=f"https://t.me/c/{str(CHANNEL_ID)[4:]}/{navigation_message_id}")],
                        [types.InlineKeyboardButton(text="🛍 ЗАКАЗАТЬ", url=link_bot_start)]
                    ])
                )
            
            message_ids.append((msg.message_id, collection['name']))
            await asyncio.sleep(1)
        except Exception as e:
            print(f"Error sending message for {collection['name']}: {e}")
    
    # Initialize nav_text with the base navigation text
    nav_text = (
        "<b>📑 НАВИГАЦИЯ</b>\n\n"
        f"<blockquote><a href='https://t.me/c/{str(CHANNEL_ID)[4:]}/{price_list_id}'>💰 ПРАЙС-ЛИСТ</a></blockquote>\n\n"
        "<b>КОЛЛЕКЦИИ:</b>\n<blockquote>"
    )

    # Add collection links
    for msg_id, name in message_ids:
        nav_text += f"\n<a href='https://t.me/c/{str(CHANNEL_ID)[4:]}/{msg_id}'>{name}</a>"
    nav_text += "</blockquote>\n\nДля заказа пишите <a href='https://t.me/ViennVapebot'>менеджеру</a>"
    msg = await bot.edit_message_text(
        nav_text,
        chat_id=CHANNEL_ID,
        message_id=navigation_message_id,
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🛍 Связаться с менеджером", url=link_bot_start)]
        ])
    )
    await bot.pin_chat_message(
        chat_id=CHANNEL_ID,
        message_id=msg.message_id,
        disable_notification=True
    )

async def main():
    price_list_id = await send_price_list()
    await send_navigation_message(price_list_id)
    await send_catalog(price_list_id)
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())