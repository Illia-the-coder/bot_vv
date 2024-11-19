import json
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from datetime import datetime
import os
# Load configuration
with open('config.json', 'r') as f:
    config = json.load(f)

# Initialize both bots
main_bot = Bot(token=config['api_key'])
manager_bot = Bot(token=config['manager_bot_token'])

# Create single dispatcher for both bots
dp = Dispatcher()

# States
class OrderStates(StatesGroup):
    greeting = State()
    choosing_delivery = State()
    choosing_location = State()
    choosing_collection = State()
    choosing_aroma = State()
    waiting_for_address = State()

def create_back_button():
    return [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]

@dp.message(Command("start"))
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

@dp.callback_query(lambda c: c.data == "start_shopping")
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
        print(f"Failed to edit message: {e}")
        # Optionally, send a new message instead
        await callback.message.answer(
            "Выберите способ пучения:",
            reply_markup=reply_markup
        )
    
    await state.set_state(OrderStates.choosing_delivery)

@dp.callback_query(lambda c: c.data == "pickup")
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

@dp.callback_query(lambda c: c.data == "delivery")
async def request_address(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(delivery_type="delivery")
    await callback.message.edit_text(
        "📍 Пожалуйста, напишите адрес доставки:\n"
        "(укажите улицу, дом, квартиру и другие необходимые детали)"
    )
    await state.set_state(OrderStates.waiting_for_address)

@dp.message(OrderStates.waiting_for_address)
async def process_address(message: types.Message, state: FSMContext):
    await state.update_data(delivery_address=message.text)
    
    keyboard = [
        [InlineKeyboardButton(
            text=collection["name"], 
            callback_data=f"col_{collection['id']}"
        )]
        for collection in config["catalog"]["collections"]
    ]
    keyboard.append(create_back_button())
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await message.answer(
        text=f"📍 Адрес доставки: {message.text}\n\n"
             f"Выберите коллекцию:",
        reply_markup=reply_markup
    )
    await state.set_state(OrderStates.choosing_collection)

@dp.callback_query(lambda c: c.data.startswith('loc_'))
async def process_location(callback: types.CallbackQuery, state: FSMContext):
    location_key = callback.data.replace('loc_', '')
    await state.update_data(location=location_key)
    
    keyboard = [
        [InlineKeyboardButton(
            text=collection["name"], 
            callback_data=f"col_{collection['id']}"
        )]
        for collection in config["catalog"]["collections"]
    ]
    keyboard.append(create_back_button())
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    message_text = (
        f"📍 Выбранный магазин: {config['locations'][location_key]['name']}\n\n"
        f"Выберите коллекцию:"
    )
    
    try:
        await callback.message.edit_text(
            text=message_text,
            reply_markup=reply_markup
        )
    except Exception:
        # If editing fails, send a new message
        await callback.message.answer(
            text=message_text,
            reply_markup=reply_markup
        )
    
    await state.set_state(OrderStates.choosing_collection)

@dp.callback_query(lambda c: c.data.startswith('col_'))
async def process_collection(callback: types.CallbackQuery, state: FSMContext):
    collection_id = callback.data.replace('col_', '')
    user_data = await state.get_data()
    await state.update_data(collection=collection_id)
    
    collection = next(c for c in config["catalog"]["collections"] if c["id"] == collection_id)
    
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

@dp.callback_query(lambda c: c.data.startswith('aroma_'))
async def process_aroma(callback: types.CallbackQuery, state: FSMContext):
    if callback.bot.id == main_bot.id:
        user_data = await state.get_data()
        
        delivery_type = user_data.get('delivery_type', 'pickup')
        location_info = ""
        if delivery_type == "pickup":
            location_key = user_data['location']
            location_info = f"📍 Магазин: {config['locations'][location_key]['name']}"
        else:
            location_info = f"📍 Адрес доставки: {user_data['delivery_address']}"
        
        collection = next(c for c in config["catalog"]["collections"] 
                         if c["id"] == user_data['collection'])
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
        await callback.message.answer(customer_message)
        
        # Send notification to the manager through manager bot
        try:
            await manager_bot.send_message(config['manager_id'], manager_message)
        except Exception as e:
            print(f"Failed to send notification to manager: {e}")
        
        await state.clear()

@dp.callback_query(lambda c: c.data == "back")
async def process_back(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    user_data = await state.get_data()
    
    # Create a new message instead of editing
    if current_state == OrderStates.choosing_location:
        new_callback = callback.model_copy(update={'data': "start_shopping"})
        await show_delivery_options(new_callback, state)
    elif current_state == OrderStates.choosing_collection:
        if user_data.get('delivery_type') == 'delivery':
            new_callback = callback.model_copy(update={'data': "delivery"})
            await request_address(new_callback, state)
        else:
            new_callback = callback.model_copy(update={'data': "pickup"})
            await show_locations(new_callback, state)
    elif current_state == OrderStates.choosing_aroma:
        new_callback = callback.model_copy(update={'data': f"loc_{user_data['location']}"})
        await process_location(new_callback, state)
    
    # Try to delete the original message, but don't raise an error if it fails
    try:
        await callback.message.delete()
    except Exception:
        pass

# Main function to run both bots
async def main():
    # Start both bots
    await asyncio.gather(
        dp.start_polling(main_bot),
        dp.start_polling(manager_bot)
    )

if __name__ == '__main__':
    asyncio.run(main())