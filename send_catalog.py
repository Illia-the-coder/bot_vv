import asyncio
from aiogram import Bot, types
from aiogram.types import FSInputFile
import json
import os
from datetime import datetime

# Load config
with open('config.json', 'r', encoding='utf-8') as file:
    config = json.load(file)

# Initialize bot with your token
bot = Bot(token=config['manager_bot_token'])
link_bot_start = "https://t.me/ViennVapebot?start=start"
CHANNEL_ID = -1002267350500

# Use premium emojis from config
PREMIUM_EMOJIS = config['premium_emojis']

async def send_channel_description():
    """Send channel description with branding"""
    description = (
        f"<b>{PREMIUM_EMOJIS['info']} {config['branding']['channel_name']}</b>\n\n"
        f"{config['branding']['channel_description']}\n\n"
    )
    return await bot.send_message(CHANNEL_ID, description, parse_mode="HTML")

async def send_why_us():
    """Send Why Choose Us section"""
    why_us_text = (
        f"{PREMIUM_EMOJIS['info']} <b>ПОЧЕМУ МЫ?</b>\n\n"
        + "\n".join(config['menu_sections']['why_us'])
    )
    return await bot.send_message(CHANNEL_ID, why_us_text, parse_mode="HTML")

async def send_delivery_info():
    """Send delivery information"""
    delivery = config['menu_sections']['delivery']
    delivery_text = (
        f"{PREMIUM_EMOJIS['delivery']} <b>ДОСТАВКА</b>\n\n"
        f"{delivery['standard']}\n"
        f"{delivery['express']}\n"
        f"{delivery['pickup']}\n\n"
        "📍 <b>ПУНКТЫ САМОВЫВОЗА</b>\n"
        "<blockquote>\n"
    )
    
    for location in config['locations'].values():
        delivery_text += f"• {location['name']}\n"
    
    delivery_text += "</blockquote>\n"
    
    return await bot.send_message(CHANNEL_ID, delivery_text, parse_mode="HTML")

async def send_price_list():
    """Enhanced price list with premium formatting"""
    price_list = (
        f"{PREMIUM_EMOJIS['price']} <b>Price list</b>\n\n"
    )
    
    sorted_collections = sorted(config['catalog']['collections'], 
                              key=lambda x: x.get('puffs', 0))
    
    for collection in sorted_collections:
        base_price = int(collection['price'])
        tier1_price = base_price
        tier2_price = base_price - 1
        tier3_price = base_price - 2
        
        price_list += (
            f"<b>{collection['name'].upper().replace('ELF BAR ', '')}</b>\n"
            f"""▫️ 1-5 pcs: {tier1_price}\n"""
            f"""▫️ 6-7 pcs: {tier2_price}\n"""
            f"""▫️ 8-10 pcs: {tier3_price}\n\n"""
        )
    
    price_list += (
        "❕Цена формируется от общего количества\n"
        "❕The price is formed from the total quantity\n\n"
        "👇Для заказа пишите:\n\n"
        f"🐇 <a href='{link_bot_start}'>МЕНЕДЖЕР</a>\n\n"
    )
    
    price_msg = await bot.send_message(CHANNEL_ID, price_list, parse_mode="HTML")
    return price_msg.message_id

async def send_catalog(price_list_id):
    """Enhanced catalog with premium formatting"""
    message_ids = []
    sorted_collections = sorted(config['catalog']['collections'], 
                              key=lambda x: x.get('puffs', 0))
    
    for collection in sorted_collections:
        tastes = "\n".join([f"• {item['name'].upper()}" for item in collection['items']])
        specs = collection['description'].split('\n')
        
        message_text = (
            f"🐰<b><i>{collection['name'].upper()}</i></b>\n\n"
            f"{PREMIUM_EMOJIS['price']} <b>ЦЕНА:</b> <b>{collection['price']}</b>\n\n"
            f"{PREMIUM_EMOJIS['info']} <b>ХАРАКТЕРИСТИКИ</b>\n"
            f"<blockquote>• {specs[0]}\n• {specs[1]}\n• {specs[2]}\n• {specs[3]}\n• {specs[4]}</blockquote>\n\n"
            f"{PREMIUM_EMOJIS['flavors']} <b>ДОСТУПНЫЕ ВКУСЫ</b>\n"
            f"<blockquote>{tastes}</blockquote>\n\n"
            "👇 <b>Для оформления заказа пишите</b>\n\n"
            f"• 🐇 <a href='{link_bot_start}'>МЕНЕДЖЕРУ</a>\n"
            f"• 🌐 <a href='https://t.me/c/{str(CHANNEL_ID)[4:]}/{price_list_id}'>К НАВИГАЦИИ</a>"
        )

        try:
            image_path = f"images/{collection['id']}.jpeg"
            if os.path.exists(image_path):
                msg = await bot.send_photo(
                    CHANNEL_ID,
                    photo=FSInputFile(image_path),
                    caption=message_text,
                    parse_mode="HTML"
                )
            else:
                msg = await bot.send_message(
                    CHANNEL_ID, 
                    message_text, 
                    parse_mode="HTML"
                )
            
            message_ids.append((msg.message_id, collection['name']))
            await asyncio.sleep(1)
        except Exception as e:
            print(f"Error sending message for {collection['name']}: {e}")
    
    return message_ids

async def send_navigation_message(section_ids, price_list_id):
    """Enhanced navigation with all sections"""
    nav_text = (
        f"{PREMIUM_EMOJIS['navigation']} <b>НАВИГАЦИЯ</b>\n\n"
        f"<blockquote>{PREMIUM_EMOJIS['price']} <a href='https://t.me/c/{str(CHANNEL_ID)[4:]}/{price_list_id}'>ПРАЙС-ЛИСТ</a>\n\n"
        f"{PREMIUM_EMOJIS['info']} <a href='https://t.me/c/{str(CHANNEL_ID)[4:]}/{section_ids['why_us_id']}'>ПОЧЕМУ МЫ?</a>\n\n"
        f"{PREMIUM_EMOJIS['delivery']} <a href='https://t.me/c/{str(CHANNEL_ID)[4:]}/{section_ids['delivery_id']}'>ДОСТАВКА</a>\n\n"
        f"{PREMIUM_EMOJIS['payment']} <a href='https://t.me/c/{str(CHANNEL_ID)[4:]}/{section_ids['payment_id']}'>СПОСОБЫ ОПЛАТЫ</a></blockquote>\n\n"
        "<b>КОЛЛЕКЦИИ:</b>\n\n"
    )
    
    nav_msg = await bot.send_message(
        CHANNEL_ID, 
        nav_text, 
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(
                text=f"{PREMIUM_EMOJIS['order']} ЗАКАЗАТЬ",
                url=link_bot_start
            )]
        ])
    )
    return nav_msg.message_id

async def update_navigation(message_ids, nav_message_id):
    """Update navigation with all collection links"""
    nav_text = (
        f"{PREMIUM_EMOJIS['navigation']} <b>НАВИГАЦИЯ</b>\n\n"
        f"<blockquote>🐇<a href='https://t.me/c/{str(CHANNEL_ID)[4:]}/{message_ids['price_list_id']}'>ПРАЙС-ЛИСТ</a>\n\n"
        f"🐇<a href='https://t.me/c/{str(CHANNEL_ID)[4:]}/{message_ids['why_us_id']}'>ПОЧЕМУ МЫ?</a>\n\n"
        f"🐇<a href='https://t.me/c/{str(CHANNEL_ID)[4:]}/{message_ids['delivery_id']}'>ДОСТАВКА</a></blockquote>\n\n"
        "<b>УСТРОЙСТВА</b>\n<blockquote>\n"
    )

    for msg_id, name in message_ids['collections']:
        nav_text += f"<a href='https://t.me/c/{str(CHANNEL_ID)[4:]}/{msg_id}'>{name.upper().replace('ELF BAR ', '')}</a>\n"

    nav_text += "</blockquote>\n\n"
    nav_text += f"{PREMIUM_EMOJIS['manager']} Для заказа пишите <a href='{link_bot_start}'>МЕНЕДЖЕРУ</a>"

    msg = await bot.edit_message_text(
        nav_text,
        chat_id=CHANNEL_ID,
        message_id=nav_message_id,
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=f"{PREMIUM_EMOJIS['order']} ЗАКАЗАТЬ", url=link_bot_start)]
        ])
    )
    
    await bot.pin_chat_message(
        chat_id=CHANNEL_ID,
        message_id=msg.message_id,
        disable_notification=True
    )

async def main():
    """Main function to execute all channel updates"""
    await send_channel_description()
    why_us_msg = await send_why_us()
    delivery_msg = await send_delivery_info()
    price_list_id = await send_price_list()
    catalogs = await send_catalog(price_list_id)
    
    # Store all message IDs
    section_ids = {
        'why_us_id': why_us_msg.message_id,
        'delivery_id': delivery_msg.message_id,
        'payment_id': price_list_id,    # You might want to create a separate payment section
        'price_list_id': price_list_id
    }
    
    message_ids = {
        'collections': catalogs,
        'price_list_id': price_list_id,
        'why_us_id': why_us_msg.message_id,
        'delivery_id': delivery_msg.message_id,
        'payment_id': price_list_id
    }
    
    # Send navigation message with actual IDs
    nav_message_id = await send_navigation_message(section_ids, price_list_id)
    
    # Update navigation if needed (optional)
    await update_navigation(message_ids, nav_message_id)
    
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())