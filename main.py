import json
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from datetime import datetime
import os
import random

# Load configuration
with open('config.json', 'r') as f:
    config = json.load(f)

# Initialize both bots
main_bot = Bot(token=config['api_key'])
manager_bot = Bot(token=config['manager_bot_token'])

# Configure logging
logging.basicConfig(level=logging.INFO)

# Create dispatcher for the main bot
main_dp = Dispatcher()

# States
class OrderStates(StatesGroup):
    greeting = State()
    choosing_delivery = State()
    choosing_location = State()
    choosing_collection_type = State()
    choosing_collection = State()
    choosing_aroma = State()
    waiting_for_address = State()

def create_back_button():
    return [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]

@main_dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    first_name = message.from_user.first_name or "Пользователь"
    await message.answer(
        f"👋 Добро пожаловать, {first_name}, в наш магазин электронных сигарет!\n\n"
        "Мы предлагаем широкий выбор продукции ELF BAR.\n"
        "Для продолжения нажмите кнопку ниже 👇"
    )
    
    keyboard = [[InlineKeyboardButton(text="Начать покупку 🛍", callback_data="start_shopping")]]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await message.answer("Выберите действие:", reply_markup=reply_markup)
    await state.set_state(OrderStates.greeting)

@main_dp.callback_query(lambda c: c.data == "start_shopping")
async def show_delivery_options(callback: types.CallbackQuery, state: FSMContext):
    keyboard = [
        [
            InlineKeyboardButton(text="🏪 Самовывоз", callback_data="pickup"),
            InlineKeyboardButton(text="🚚 Доставка", callback_data="delivery")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    try:
        await callback.message.edit_text(
            "Выберите способ получения:",
            reply_markup=reply_markup
        )
    except Exception as e:
        logging.error(f"Failed to edit message: {e}")
        await callback.message.answer(
            "Выберите способ получения:",
            reply_markup=reply_markup
        )
    
    await state.set_state(OrderStates.choosing_delivery)

@main_dp.callback_query(lambda c: c.data == "pickup")
async def show_locations(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(delivery_type="pickup")
    keyboard = [
        [InlineKeyboardButton(text=loc_data["name"], callback_data=f"loc_{loc_key}")]
        for loc_key, loc_data in config["locations"].items()
    ]
    keyboard.append(create_back_button())
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(
        "🏪 Выберите ближайший магазин для самовывоза:",
        reply_markup=reply_markup
    )
    await state.set_state(OrderStates.choosing_location)

@main_dp.callback_query(lambda c: c.data == "delivery")
async def request_address(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(delivery_type="delivery")
    await callback.message.edit_text(
        "📍 Пожалуйста, напишите адрес доставки:\n"
        "(укажите улицу, дом, квартиру и другие необходимые детали)"
    )
    await state.set_state(OrderStates.waiting_for_address)

@main_dp.message(OrderStates.waiting_for_address)
async def process_address(message: types.Message, state: FSMContext):
    await state.update_data(delivery_address=message.text)
    
    # Create keyboard with both HQD and Liquid collections
    keyboard = [
        [InlineKeyboardButton(text="Устройства", callback_data="type_hqd"),
         InlineKeyboardButton(text="Жидкости", callback_data="type_liquid")]
    ]
    keyboard.append(create_back_button())
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await message.answer(
        text=f"📍 Адрес доставки: {message.text}\n\n"
             f"Выберите тип продукции:",
        reply_markup=reply_markup
    )
    await state.set_state(OrderStates.choosing_collection_type)

@main_dp.callback_query(lambda c: c.data.startswith('loc_'))
async def process_location(callback: types.CallbackQuery, state: FSMContext):
    location_key = callback.data.replace('loc_', '')
    await state.update_data(location=location_key)
    
    keyboard = [
        [
            InlineKeyboardButton(text="Устройства", callback_data="type_hqd"),
            InlineKeyboardButton(text="Жидкости", callback_data="type_liquid")
        ]
    ]
    keyboard.append(create_back_button())
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard )
    
    message_text = (
        f"📍 Выбранный магазин: {config['locations'][location_key]['name']}\n\n"
        f"Выберите тип продукции:"
    )
    
    await callback.message.edit_text(
        text=message_text,
        reply_markup=reply_markup
    )
    
    await state.set_state(OrderStates.choosing_collection_type)

@main_dp.callback_query(lambda c: c.data.startswith('type_'))
async def process_collection_type(callback: types.CallbackQuery, state: FSMContext):
    collection_type = callback.data.replace('type_', '')
    await state.update_data(collection_type=collection_type)
    
    # Get the appropriate collection based on type
    collections = config["catalog"]["hqd_collections" if collection_type == "hqd" else "liquid_collections"]
    
    keyboard = [
        [InlineKeyboardButton(
            text=collection["name"], 
            callback_data=f"col_{collection['id']}"
        )]
        for collection in collections
    ]
    keyboard.append(create_back_button())
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    user_data = await state.get_data()
    # Check delivery type and construct appropriate message
    if user_data.get('delivery_type') == 'delivery':
        message_text = (
            f"📍 Адрес доставки: {user_data['delivery_address']}\n\n"
            f"Выберите коллекцию:"
        )
    else:
        message_text = (
            f"📍 Выбранный магазин: {config['locations'][user_data['location']]['name']}\n\n"
            f"Выберите коллекцию:"
        )
    
    await callback.message.edit_text(
        text=message_text,
        reply_markup=reply_markup
    )
    
    await state.set_state(OrderStates.choosing_collection)

@main_dp.callback_query(lambda c: c.data.startswith('col_'))
async def process_collection(callback: types.CallbackQuery, state: FSMContext):
    collection_id = callback.data.replace('col_', '')
    user_data = await state.get_data()
    await state.update_data(collection=collection_id)
    
    # Get collections based on type
    collections = config["catalog"]["hqd_collections" if user_data['collection_type'] == "hqd" else "liquid_collections"]
    collection = next(c for c in collections if c["id"] == collection_id)
    
    keyboard = [
        [InlineKeyboardButton(
            text=item["name"], 
            callback_data=f"aroma_{item['id']}"
        )]
        for item in collection["items"]
    ]
    keyboard.append(create_back_button())
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.delete()
    
    location_info = ""
    if user_data.get('delivery_type') == 'pickup':
        location_info = f"📍 Магазин: {config['locations'][user_data['location']]['name']}"
    else:
        location_info = f"📍 Адрес доставки: {user_data['delivery_address']}"
    if os.path.exists(f'images/{collection["id"]}.jpeg'):
        photo = FSInputFile(f'images/{collection["id"]}.jpeg')
        await callback.message.answer_photo(
            photo=photo,
            caption=f"{location_info}\n"
                    f"📦 Коллекция: {collection['name']}\n\n"
                    f"Выберите вкус:",
            reply_markup=reply_markup
        )
    else:
        await callback.message.answer(
            text=f"{location_info}\n"
                 f"📦 Коллекция: {collection['name']}\n\n"
                 f"Выберите вкус:",
            reply_markup=reply_markup
        )
    await state.set_state(OrderStates.choosing_aroma)

async def send_follow_up_message(message: types.Message):
    await asyncio.sleep(random.randint(1, 30))  # Random delay between 1-30 seconds
    await message.answer("🕐 Ваш заказ обрабатывается... Мы свяжемся с вами в течение 5 минут!")

@main_dp.callback_query(lambda c: c.data.startswith('aroma_'))
async def process_aroma(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    
    delivery_type = user_data.get('delivery_type', 'pickup')
    location_info = ""
    if delivery_type == "pickup":
        location_key = user_data['location']
        location_info = f"📍 Магазин: {config['locations'][location_key]['name']}"
    else:
        location_info = f"📍 Адрес доставки: {user_data['delivery_address']}"
    
    # Get collections based on type
    collections = config["catalog"]["hqd_collections" if user_data['collection_type'] == "hqd" else "liquid_collections"]
    collection = next(c for c in collections if c["id"] == user_data['collection'])
    aroma = next(item for item in collection["items"] 
                 if str(item["id"]) == callback.data.replace('aroma_', ''))
    
    current_time = datetime.now().strftime("%d.%m.%Y %H:%M")
    username = callback.from_user.username or "Без username"
    user_fullname = callback.from_user.full_name or "Без имени"
    
    customer_message = (
        f"✅ Отлично! Ваш выбор:\n\n"
        f"{location_info}\n"
        f"📦 Коллекция: {collection['name']}\n"
        f"🎨 Вкус: {aroma['name']}\n\n"
        f"{'Ожидайте, продавец свяжется с вами для уточнения стоимости доставки!' if delivery_type == 'delivery' else 'Ждем вас в магазине!'}\n\n"
        f"Для нового заказа используйте команду /start"
    )
    
    order_id = str(abs(hash(current_time + username)))[-8:]
    manager_message = (
        f"🔔 #{order_id}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📅 ДАТА: {current_time}\n"
        f"👤 КЛИЕНТ:\n"
        f"   • TG: @{username}\n"
        f"   • Имя: {user_fullname}\n\n"
        f"🛍 ЗАКАЗ:\n"
        f"   • Серия: {collection['name']}\n"
        f"   • Вкус: {aroma['name']}\n"
        f"📍 ПОЛУЧЕНИЕ:\n"
        f"   • Тип: {'🚚 Доставка' if delivery_type == 'delivery' else '🏪 Самовывоз'}\n"
        f"   • Адрес: {location_info.split(': ')[1]}\n"
        f"━━━━━━━━━━━━━━━"
    )
    
    await callback.message.delete()
    sent_message = await callback.message.answer(customer_message)
    
    # Start sending follow-up message
    asyncio.create_task(send_follow_up_message(sent_message))
    
    # Send notification to the manager through manager bot
    try:
        await manager_bot.send_message(config['manager_id'], manager_message)
        print('message to manager sent!')
    except Exception as e:
        logging.error(f"Failed to send notification to manager: {e}")
    
    await state.clear()

@main_dp.callback_query(lambda c: c.data == "back")
async def process_back(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    user_data = await state.get_data()
    
    try:
        await callback.message.delete()
    except Exception as e:
        logging.error(f"Failed to delete message: {e}")
    
    if current_state == OrderStates.choosing_collection_type.state:
        keyboard = [
            [InlineKeyboardButton(text=loc_data["name"], callback_data=f"loc_{loc_key}")]
            for loc_key, loc_data in config["locations"].items()
        ]
        keyboard.append(create_back_button())
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await callback.message.answer(
            "🏪 Выберите ближайший магазин для самовывоза:",
            reply_markup=reply_markup
        )
        await state.set_state(OrderStates.choosing_location)
    
    elif current_state == OrderStates.choosing_collection.state:
        keyboard = [
            [
                InlineKeyboardButton(text="Устройства", callback_data="type_hqd"),
                InlineKeyboardButton(text="Жидкости", callback_data="type_liquid")
            ]
        ]
        keyboard.append(create_back_button())
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        # Check delivery type and construct appropriate message
        if user_data.get('delivery_type') == 'delivery':
            message_text = (
                f"📍 Адрес доставки: {user_data['delivery_address']}\n\n"
                f"Выберите тип продукции:"
            )
        else:
            message_text = (
                f"📍 Выбранный магазин: {config['locations'][user_data['location']]['name']}\n\n"
                f"Выберите тип продукции:"
            )
        
        await callback.message.answer(
            text=message_text,
            reply_markup=reply_markup
        )
        await state.set_state(OrderStates.choosing_collection_type)
    
    elif current_state == OrderStates.choosing_aroma.state:
        # Get collections based on type
        collections = config["catalog"]["hqd_collections" if user_data['collection_type'] == "hqd" else "liquid_collections"]
        keyboard = [
            [InlineKeyboardButton(
                text=collection["name"], 
                callback_data=f"col_{collection['id']}"
            )]
            for collection in collections
        ]
        keyboard.append(create_back_button())
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        if user_data.get('delivery_type') == 'delivery':
            message_text = (
                f"📍 Адрес доставки: {user_data['delivery_address']}\n\n"
                f"Выберите коллекцию:"
            )
        else:
            message_text = (
                f"📍 Выбранный магазин: {config['locations'][user_data['location']]['name']}\n\n"
                f"Выберите коллекцию:"
            )
        
        await callback.message.answer(
            text=message_text,
            reply_markup=reply_markup
        )
        await state.set_state(OrderStates.choosing_collection)

# Main function to run the bot
async def main():
    # Start polling the main bot
    await main_dp.start_polling(main_bot)

if __name__ == '__main__':
    asyncio.run(main())