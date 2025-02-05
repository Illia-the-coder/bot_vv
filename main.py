import json
import asyncio
import logging
import os
import random
import string
from datetime import datetime

import pandas as pd
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, FSInputFile
from aiogram.utils.deep_linking import create_start_link
from airtable import Airtable  # Airtable client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize configuration from config.json
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

# Retrieve configuration values
api_key = config.get('api_key')
manager_bot_token = config.get('manager_bot_token')
manager_id = config.get('manager_id')
manager_username = config.get('manager_username')  # Optional, if needed
locations = config.get('locations', {})
postavka = config.get('postavka', [])
catalog = config.get('catalog', {})
branding = config.get('branding', {})
premium_emojis = config.get('premium_emojis', {})
orders_config = config.get('orders', [])

if not all([api_key, manager_bot_token, manager_id, catalog, locations]):
    raise EnvironmentError("One or more required configurations are missing in config.json.")

# Initialize Airtable for orders and users
airtable_api_key = os.environ.get("AIRTABLE_API_KEY") or 'patiYQItaj3fkdAYR.f1c0901c38fefc439945a2f9685511ed7cc6b636fd5cfc33aa548aafa9458564'
airtable_base_id = os.environ.get("AIRTABLE_BASE_ID") or 'app3tQaubsx9JQK0z'

if not all([airtable_api_key, airtable_base_id]):
    raise EnvironmentError("AIRTABLE_API_KEY and AIRTABLE_BASE_ID must be set in environment variables.")

# Define Airtable tables
orders_airtable = Airtable(airtable_base_id, 'Orders', airtable_api_key)
users_airtable = Airtable(airtable_base_id, 'Users', airtable_api_key)  # Table for referral system

# Initialize bots
main_bot = Bot(token=api_key)
manager_bot = Bot(token=manager_bot_token)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Create dispatchers for each bot
main_dp = Dispatcher()
manager_dp = Dispatcher()

# Define FSM states
class OrderStates(StatesGroup):
    greeting = State()
    choosing_delivery = State()
    choosing_location = State()
    choosing_product_type = State()
    choosing_collection_type = State()
    choosing_aroma = State()
    waiting_for_address = State()

class ReferralStates(StatesGroup):
    dashboard = State()

def create_back_button():
    """
    Returns a back button that always sends the user
    to the general (main) menu.
    """
    return [InlineKeyboardButton(text="↩️ Главное меню", callback_data="back_to_general")]

def build_inventory(config):
    """
    Build the inventory dictionary from the 'postavka' configuration.
    """
    inventory = {key: {} for key in config["locations"].keys()}
    for postavka_entry in config.get("postavka", []):
        for loc, delivery in postavka_entry.get("deliveries", {}).items():
            item_quantities = delivery.get("items", {})
            for item_id, qty in item_quantities.items():
                inventory[loc][item_id] = inventory[loc].get(item_id, 0) + qty
    return inventory

def generate_referral_code(length=6):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

async def register_user(user_id: int, username: str, referral_code: str = None):
    existing_user = users_airtable.get_all(formula=f"{{User ID}} = '{user_id}'")
    if existing_user:
        return  # User already exists
    user_referral_code = generate_referral_code()
    user_data = {
        "User ID": str(user_id),
        "Username": username,
        "Referral Code": user_referral_code,
        "Referrer Code": referral_code or "",
        "Total Referrals": 0,
        "Discount": 0
    }
    try:
        users_airtable.insert(user_data)
        logging.info(f"User {username} registered successfully.")
    except Exception as e:
        logging.error(f"Failed to insert user data into Airtable: {e}")

async def get_user_discount(user_id: int):
    user_records = users_airtable.get_all(formula=f"{{User ID}} = {user_id}")
    if user_records:
        return user_records[0]['fields'].get("Discount", 0)
    return 0

def apply_discount(order_total, discount):
    return order_total * (1 - discount / 100)

async def send_follow_up_message(message: types.Message):
    await asyncio.sleep(random.randint(1, 30))
    await message.answer("🕐 Ваш заказ обрабатывается... Мы свяжемся с вами в течение 5 минут!")

# ----------------------------
# MAIN BOT HANDLERS
# ----------------------------

@main_dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    # Extract referral parameter if present
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []
    referral_code = args[0] if args else None

    # Register the user
    await register_user(message.from_user.id, message.from_user.username or "NoUsername", referral_code)

    # Generate referral link
    if referral_code:
        payload = referral_code
    else:
        user_records = users_airtable.get_all(formula=f"{{User ID}} = {message.from_user.id}")
        if user_records:
            payload = user_records[0]['fields'].get("Referral Code", generate_referral_code())
        else:
            payload = generate_referral_code()
    referral_link = await create_start_link(bot=main_bot, payload=str(payload), encode=True)

    first_name = message.from_user.first_name or "Пользователь"
    welcome_text = (
        f"{premium_emojis.get('flavors', '🍓')} *Добро пожаловать, {first_name}!*\n\n"
        "Мы предлагаем широкий выбор продукции ELF BAR.\n"
        "Для продолжения нажмите кнопку ниже 👇"
    )
    await message.answer(welcome_text, parse_mode="Markdown")

    promotion_message = (
        "🎉 *Новая акция!*\n\n"
        "▪️ Приведи друга, который сделает заказ — получи *10% скидку*.\n"
        "▪️ Приведи второго друга — получи ещё *10% скидки*.\n"
        "▪️ И так далее, до *50% скидки* за 5 друзей!"
    )
    await message.answer(promotion_message, parse_mode='Markdown')

    share_text = f"Приглашаю в ELF BAR: {referral_link}"
    main_menu_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 Купить продукцию", callback_data="start_shopping")],
        [InlineKeyboardButton(text="📊 Мой Кабинет", callback_data="dashboard")],
        [InlineKeyboardButton(text="🔗 Поделиться ссылкой", switch_inline_query=share_text)]
    ])
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard)
    await state.set_state(OrderStates.greeting)

@main_dp.message(Command("dashboard"))
async def cmd_dashboard(message: types.Message):
    user_records = users_airtable.get_all(formula=f"{{User ID}} = {message.from_user.id}")
    if not user_records:
        await message.answer("Вы не зарегистрированы. Используйте /start для начала.")
        return
    user = user_records[0]['fields']
    referral_code = user.get("Referral Code", "N/A")
    referrals = user.get("Total Referrals", 0)
    discount = user.get("Discount", 0)

    referred_users = users_airtable.get_all(formula=f"{{Referrer Code}} = '{referral_code}'")
    referred_list = "\n".join([f"- @{record['fields'].get('Username', 'NoUsername')}" for record in referred_users]) or "Нет рефералов."
    dashboard_message = (
        f"📊 *Мой Кабинет*\n\n"
        f"🔗 *Ваша реферальная ссылка:*\n"
        f"https://t.me/{main_bot.username}?start={referral_code}\n\n"
        f"👥 *Приглашено друзей:* {referrals}\n"
        f"💸 *Ваша скидка:* {discount}%\n\n"
        f"👥 *Список рефералов:*\n{referred_list}"
    )
    dashboard_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Поделиться кабинетом", switch_inline_query=f"Приглашаю в ELF BAR: https://t.me/{main_bot.username}?start={referral_code}")],
        [InlineKeyboardButton(text="↩️ В главное меню", callback_data="back_to_general")]
    ])
    await message.answer(dashboard_message, parse_mode="Markdown", reply_markup=dashboard_keyboard)

@main_dp.callback_query(lambda c: c.data == "dashboard")
async def show_dashboard(callback: types.CallbackQuery, state: FSMContext):
    user_records = users_airtable.get_all(formula=f"{{User ID}} = {callback.from_user.id}")
    if not user_records:
        await callback.message.answer("Вы не зарегистрированы. Используйте /start для начала.")
        return
    user = user_records[0]['fields']
    referral_code = user.get("Referral Code", "N/A")
    referrals = user.get("Total Referrals", 0)
    discount = user.get("Discount", 0)
    referred_users = users_airtable.get_all(formula=f"{{Referrer Code}} = '{referral_code}'")
    referred_list = "\n".join([f"- @{record['fields'].get('Username', 'NoUsername')}" for record in referred_users]) or "Нет рефералов."
    dashboard_message = (
        f"📊 *Мой Кабинет*\n\n"
        f"🔗 *Ваша реферальная ссылка:*\n"
        f"https://t.me/{main_bot.username}?start={referral_code}\n\n"
        f"👥 *Приглашено друзей:* {referrals}\n"
        f"💸 *Ваша скидка:* {discount}%\n\n"
        f"👥 *Список рефералов:*\n{referred_list}"
    )
    dashboard_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Поделиться кабинетом", switch_inline_query=f"Приглашаю в ELF BAR: https://t.me/{main_bot.username}?start={referral_code}")],
        [InlineKeyboardButton(text="↩️ В главное меню", callback_data="back_to_general")]
    ])
    await callback.message.answer(dashboard_message, parse_mode="Markdown", reply_markup=dashboard_keyboard)

@main_dp.callback_query(lambda c: c.data == "back_to_general")
async def back_to_general(callback: types.CallbackQuery, state: FSMContext):
    """
    Clears any FSM state and shows the general main menu.
    """
    await state.clear()
    user_records = users_airtable.get_all(formula=f"{{User ID}} = {callback.from_user.id}")
    if user_records:
        referral_code = user_records[0]['fields'].get("Referral Code", "")
    else:
        referral_code = ""
    share_text = f"Приглашаю в ELF BAR: https://t.me/{main_bot.username}?start={referral_code}"
    main_menu_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 Купить продукцию", callback_data="start_shopping")],
        [InlineKeyboardButton(text="📊 Мой Кабинет", callback_data="dashboard")],
        [InlineKeyboardButton(text="🔗 Поделиться ссылкой", switch_inline_query=share_text)]
    ])
    try:
        await callback.message.edit_text("Главное меню:", reply_markup=main_menu_keyboard)
    except Exception as e:
        logging.error(f"Failed to display main menu: {e}")
        await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard)

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
        await callback.message.edit_text("Выберите способ получения:", reply_markup=reply_markup)
    except Exception as e:
        logging.error(f"Failed to edit message: {e}")
        await callback.message.answer("Выберите способ получения:", reply_markup=reply_markup)
    await state.set_state(OrderStates.choosing_delivery)

@main_dp.callback_query(lambda c: c.data == "pickup")
async def show_locations(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(delivery_type="pickup")
    keyboard = [
        [InlineKeyboardButton(text=loc_data["name"], callback_data=f"loc_{loc_key}")]
        for loc_key, loc_data in locations.items()
    ]
    keyboard.append(create_back_button())
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await callback.message.edit_text("🏪 *Выберите ближайший магазин для самовывоза:*", reply_markup=reply_markup, parse_mode="Markdown")
    await state.set_state(OrderStates.choosing_location)

@main_dp.callback_query(lambda c: c.data == "delivery")
async def request_address(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(delivery_type="delivery")
    await callback.message.edit_text("📍 *Пожалуйста, укажите адрес доставки:*\n(Укажите улицу, дом, квартиру и другие необходимые детали)", parse_mode="Markdown")
    await state.set_state(OrderStates.waiting_for_address)

@main_dp.message(OrderStates.waiting_for_address)
async def process_address(message: types.Message, state: FSMContext):
    await state.update_data(delivery_address=message.text)
    await show_product_type_selection(message, state)

async def show_product_type_selection(event, state: FSMContext):
    keyboard = [
        [
            InlineKeyboardButton(text="📦 Устройство", callback_data="product_vape"),
            InlineKeyboardButton(text="💧 Жидкость", callback_data="product_liquid")
        ]
    ]
    keyboard.append(create_back_button())
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    if isinstance(event, types.CallbackQuery):
        try:
            await event.message.delete()
        except Exception as e:
            logging.error(f"Failed to delete message: {e}")
        await event.message.answer("Выберите тип продукта:", reply_markup=reply_markup)
    else:
        await event.answer("Выберите тип продукта:", reply_markup=reply_markup)
    await state.set_state(OrderStates.choosing_product_type)

@main_dp.callback_query(lambda c: c.data in ["product_liquid", "product_vape"])
async def process_product_type(callback: types.CallbackQuery, state: FSMContext):
    product_type = "liquid" if callback.data == "product_liquid" else "vape"
    await state.update_data(product_type=product_type)
    await show_collection_types(callback, state)

async def show_collection_types(event, state: FSMContext):
    user_data = await state.get_data()
    inventory = build_inventory(config)
    keyboard = []
    location_key = user_data.get('location')
    product_type = user_data.get('product_type')
    if product_type == "liquid":
        collections = catalog.get("liquid_collections", [])
    else:
        collections = catalog.get("hqd_collections", [])
    for collection in collections:
        is_available = False
        for item in collection.get("items", []):
            item_id = str(item["id"])
            if user_data.get('delivery_type') == 'pickup':
                if location_key in inventory and item_id in inventory[location_key] and inventory[location_key][item_id] > 0:
                    is_available = True
                    break
            else:
                for loc in inventory.values():
                    if item_id in loc and loc[item_id] > 0:
                        is_available = True
                        break
        collection_name = f"🟢 {collection['name']}" if is_available else f"🔴 {collection['name']}"
        keyboard.append([InlineKeyboardButton(text=collection_name, callback_data=f"type_{collection['id']}")])
    keyboard.append(create_back_button())
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    if user_data.get('delivery_type') == 'delivery':
        message_text = f"📍 *Адрес доставки:* {user_data['delivery_address']}\n\nВыберите тип продукции:"
    else:
        message_text = f"📍 *Выбранный магазин:* {locations[user_data['location']]['name']}\n\nВыберите тип продукции:"
    if isinstance(event, types.CallbackQuery):
        try:
            await event.message.delete()
        except Exception as e:
            logging.error(f"Failed to delete message: {e}")
        await event.message.answer(text=message_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await event.answer(text=message_text, reply_markup=reply_markup, parse_mode="Markdown")
    await state.set_state(OrderStates.choosing_collection_type)

@main_dp.callback_query(lambda c: c.data.startswith('loc_'))
async def process_location(callback: types.CallbackQuery, state: FSMContext):
    location_key = callback.data.replace('loc_', '')
    await state.update_data(location=location_key)
    await show_product_type_selection(callback, state)

@main_dp.callback_query(lambda c: c.data.startswith('type_'))
async def process_collection_type(callback: types.CallbackQuery, state: FSMContext):
    collection_id = callback.data.replace('type_', '')
    await state.update_data(collection=collection_id)
    user_data = await state.get_data()
    product_type = user_data.get('product_type')
    if product_type == "liquid":
        collections = catalog.get("liquid_collections", [])
    else:
        collections = catalog.get("hqd_collections", [])
    collection = next((c for c in collections if c["id"] == collection_id), None)
    if not collection:
        await callback.answer("Коллекция не найдена.", show_alert=True)
        return
    await state.update_data(collection_type=collection_id)
    inventory = build_inventory(config)
    keyboard = []
    location_key = user_data.get('location')
    for item in collection.get("items", []):
        item_id = str(item['id'])
        is_available = False
        if user_data.get('delivery_type') == 'pickup':
            if location_key in inventory and item_id in inventory[location_key] and inventory[location_key][item_id] > 0:
                is_available = True
        else:
            for loc in inventory.values():
                if item_id in loc and loc[item_id] > 0:
                    is_available = True
                    break
        item_name = f"🟢 {item['name']}" if is_available else f"🔴 {item['name']}"
        keyboard.append([InlineKeyboardButton(text=item_name, callback_data=f"aroma_{item['id']}")])
    keyboard.append(create_back_button())
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    if user_data.get('delivery_type') == 'delivery':
        message_text = f"📍 *Адрес доставки:* {user_data['delivery_address']}\n\nВыберите вкус из коллекции *{collection['name']}*:"
    else:
        message_text = f"📍 *Выбранный магазин:* {locations[user_data['location']]['name']}\n\nВыберите вкус из коллекции *{collection['name']}*:"
    try:
        await callback.message.delete()
    except Exception as e:
        logging.error(f"Failed to delete message: {e}")
    image_path = f"images/{collection['id']}.jpeg"
    logging.info(f"Collection image path: {image_path}")
    if not os.path.isfile(image_path):
        logging.error(f"Image file not found: {image_path}")
        await callback.answer("Изображение коллекции не найдено.", show_alert=True)
        return
    photo = FSInputFile(image_path)
    await main_bot.send_photo(
        chat_id=callback.message.chat.id,
        photo=photo,
        caption=message_text,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    await state.set_state(OrderStates.choosing_aroma)

# ----------------------------
# DISCOUNT CONFIRMATION FLOW
# ----------------------------

@main_dp.callback_query(lambda c: c.data.startswith('aroma_'))
async def process_aroma(callback: types.CallbackQuery, state: FSMContext):
    """
    After the user selects an aroma, check if they have a discount (>0).
    If yes, ask whether to apply the discount.
    """
    user_data = await state.get_data()
    delivery_type = user_data.get('delivery_type', 'pickup')
    location_info = ""
    inventory = build_inventory(config)
    product_type = user_data.get('product_type')
    if delivery_type == "pickup":
        location_key = user_data['location']
        location_info = f"📍 Магазин: {locations[location_key]['name']}"
        manager_name = locations[location_key].get('manager', 'Менеджер')
    else:
        location_info = f"📍 Адрес доставки: {user_data.get('delivery_address', 'Не указан')}"
        manager_name = "Менеджер доставки"
    if product_type == "liquid":
        collections = catalog.get("liquid_collections", [])
    else:
        collections = catalog.get("hqd_collections", [])
    collection = next((c for c in collections if c["id"] == user_data.get('collection_type')), None)
    if not collection:
        await callback.answer("Коллекция не найдена.", show_alert=True)
        return
    aroma_id = callback.data.replace('aroma_', '')
    aroma = next((item for item in collection.get("items", []) if str(item["id"]) == aroma_id), None)
    if not aroma:
        await callback.answer("Аромат не найден.", show_alert=True)
        return
    item_id = str(aroma['id'])
    is_available = False
    if delivery_type == "pickup":
        location_key = user_data['location']
        if location_key in inventory and item_id in inventory[location_key] and inventory[location_key][item_id] > 0:
            is_available = True
    else:
        for loc in inventory.values():
            if item_id in loc and loc[item_id] > 0:
                is_available = True
                break
    if not is_available:
        await callback.answer("Извините, этот товар сейчас недоступен.", show_alert=True)
        return
    current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    username = callback.from_user.username or "Без username"
    user_fullname = callback.from_user.full_name or "Без имени"
    base_customer_message = (
        f"✅ *Отлично!*\n\n"
        f"*Ваш выбор:*\n"
        f"{location_info}\n"
        f"📦 *Коллекция:* {collection['name']}\n"
        f"🎨 *Вкус:* {aroma['name']}\n\n"
    )
    order_total = 1000  # Example base total
    discount = await get_user_discount(callback.from_user.id)
    if discount > 0:
        discount_prompt = f"У вас есть скидка {discount}%. Хотите применить её к вашему заказу?"
        discount_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Да, применить скидку", callback_data="apply_discount")],
            [InlineKeyboardButton(text="Нет, не применять", callback_data="skip_discount")]
        ])
        # Save all necessary information in state for later use.
        await state.update_data(
            current_time=current_time,
            username=username,
            user_fullname=user_fullname,
            location_info=location_info,
            order_total=order_total,
            collection=collection,
            aroma_name=aroma['name'],
            discount=discount,
            manager_name=manager_name,
            delivery_type=delivery_type,
            delivery_address=user_data.get('delivery_address', "")
        )
        await callback.message.answer(discount_prompt, parse_mode="Markdown", reply_markup=discount_keyboard)
        return
    else:
        total_val = order_total
    # If no discount is available, finalize the order immediately.
    order_id = str(abs(hash(current_time + username)))[-8:]
    manager_message = (
        f"🔔 *Заказ #{order_id}*\n"
        "━━━━━━━━━━━━━━━\n"
        f"📅 *Дата:* {current_time}\n"
        f"👤 *Клиент:*\n"
        f"   • TG: @{username}\n"
        f"   • Имя: {user_fullname}\n\n"
        f"🛍 *Заказ:*\n"
        f"   • Серия: {collection['name']}\n"
        f"   • Вкус: {aroma['name']}\n"
        f"   • Скидка: 0%\n"
        f"   • Итог: {total_val}\n"
        f"📍 *Получение:*\n"
        f"   • {location_info.split(': ', 1)[0]}: {location_info.split(': ', 1)[1]}\n"
        "━━━━━━━━━━━━━━━"
    )
    customer_message = (
        base_customer_message +
        "Скидка не применена.\n"
        f"Итоговая сумма заказа: {total_val}\n\n"
        "Для нового заказа используйте команду /start"
    )
    try:
        await callback.message.delete()
    except Exception as e:
        logging.error(f"Failed to delete message: {e}")
    sent_message = await callback.message.answer(customer_message, parse_mode="Markdown")
    asyncio.create_task(send_follow_up_message(sent_message))
    order_details = {
        "Order ID": int(order_id),
        "Date": current_time,
        "User": f"<https://t.me/{username}>",
        "Delivery Type": delivery_type,
        "Location": location_info.split(': ', 1)[1] if delivery_type != 'delivery' else "",
        "Delivery Address": user_data.get('delivery_address', "") if delivery_type == 'delivery' else "",
        "Collection Name": collection['name'],
        "Flavor Name": aroma['name'],
        "Manager": manager_name,
        "Discount Applied": 0,
        "Status": False,
        "User ID": callback.from_user.id,
        "Total": total_val
    }
    try:
        orders_airtable.insert(order_details)
        logging.info("Order details inserted into Airtable successfully.")
    except Exception as e:
        logging.error(f"Failed to insert order details into Airtable: {e}")
        await callback.answer("Ошибка при сохранении заказа.", show_alert=True)
        return
    try:
        await manager_bot.send_message(manager_id, manager_message, parse_mode="Markdown")
        logging.info('Notification sent to manager.')
    except Exception as e:
        logging.error(f"Failed to send notification to manager: {e}")
        await callback.answer("Не удалось уведомить менеджера.", show_alert=True)
        return
    await state.clear()

@main_dp.callback_query(lambda c: c.data == "apply_discount")
async def apply_discount_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    discount = data.get("discount", 0)
    order_total = data.get("order_total", 1000)
    total_val = apply_discount(order_total, discount)
    order_id = str(abs(hash(data.get("current_time") + data.get("username"))))[-8:]
    manager_message = (
        f"🔔 *Заказ #{order_id}*\n"
        "━━━━━━━━━━━━━━━\n"
        f"📅 *Дата:* {data.get('current_time')}\n"
        f"👤 *Клиент:*\n"
        f"   • TG: @{data.get('username')}\n"
        f"   • Имя: {data.get('user_fullname')}\n\n"
        f"🛍 *Заказ:*\n"
        f"   • Серия: {data.get('collection')['name']}\n"
        f"   • Вкус: {data.get('aroma_name')}\n"
        f"   • Скидка: {discount}%\n"
        f"   • Итог: {total_val}\n"
        f"📍 *Получение:*\n"
        f"   • {data.get('location_info').split(': ',1)[0]}: {data.get('location_info').split(': ',1)[1]}\n"
        "━━━━━━━━━━━━━━━"
    )
    customer_message = (
        f"✅ *Отлично!*\n\n"
        f"*Ваш выбор:*\n"
        f"{data.get('location_info')}\n"
        f"📦 *Коллекция:* {data.get('collection')['name']}\n"
        f"🎨 *Вкус:* {data.get('aroma_name')}\n\n"
        f"Скидка {discount}% применена.\n"
        f"Итоговая сумма заказа: {total_val}\n\n"
        "Для нового заказа используйте команду /start"
    )
    order_details = {
        "Order ID": int(order_id),
        "Date": data.get("current_time"),
        "User": f"<https://t.me/{data.get('username')}>",
        "Delivery Type": data.get("delivery_type", ""),
        "Location": data.get("location_info").split(': ',1)[1] if data.get("delivery_type") != 'delivery' else "",
        "Delivery Address": data.get("delivery_address", "") if data.get("delivery_type") == "delivery" else "",
        "Collection Name": data.get("collection")['name'],
        "Flavor Name": data.get("aroma_name"),
        "Manager": data.get("manager_name"),
        "Discount Applied": discount,
        "Status": False,
        "User ID": callback.from_user.id,
        "Total": total_val
    }
    try:
        orders_airtable.insert(order_details)
        logging.info("Order with discount inserted into Airtable successfully.")
    except Exception as e:
        logging.error(f"Failed to insert order details into Airtable: {e}")
        await callback.answer("Ошибка при сохранении заказа.", show_alert=True)
        return
    # Reset the user's discount to 0.
    user_records = users_airtable.get_all(formula=f"{{User ID}} = '{callback.from_user.id}'")
    if user_records and discount>0:
        record_id = user_records[0]['id']
        try:
            users_airtable.update(record_id, {"Discount": 0})
            logging.info("User discount updated to 0 after applying discount.")
        except Exception as e:
            logging.error(f"Failed to update user discount in Airtable: {e}")
    try:
        await callback.message.delete()
    except Exception as e:
        logging.error(f"Failed to delete discount confirmation message: {e}")
    await callback.message.answer(customer_message, parse_mode="Markdown")
    try:
        await manager_bot.send_message(manager_id, manager_message, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Failed to send notification to manager: {e}")
    await state.clear()

@main_dp.callback_query(lambda c: c.data == "skip_discount")
async def skip_discount_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    order_total = data.get("order_total", 1000)
    total_val = order_total
    
    # Ensure current_time and username are not None
    current_time = data.get("current_time") or "default_time"
    username = data.get("username") or "default_username"
    
    order_id = str(abs(hash(current_time + username)))[-8:]
    manager_message = (
        f"🔔 *Заказ #{order_id}*\n"
        "━━━━━━━━━━━━━━━\n"
        f"📅 *Дата:* {current_time}\n"
        f"👤 *Клиент:*\n"
        f"   • TG: @{username}\n"
        f"   • Имя: {data.get('user_fullname')}\n\n"
        f"🛍 *Заказ:*\n"
        f"   • Серия: {data.get('collection')['name']}\n"
        f"   • Вкус: {data.get('aroma_name')}\n"
        f"   • Скидка: 0%\n"
        f"   • Итог: {total_val}\n"
        f"📍 *Получение:*\n"
        f"   • {data.get('location_info').split(': ',1)[0]}: {data.get('location_info').split(': ',1)[1]}\n"
        "━━━━━━━━━━━━━━━"
    )
    customer_message = (
        f"✅ *Отлично!*\n\n"
        f"*Ваш выбор:*\n"
        f"{data.get('location_info')}\n"
        f"📦 *Коллекция:* {data.get('collection')['name']}\n"
        f"🎨 *Вкус:* {data.get('aroma_name')}\n\n"
        "Скидка не применена.\n"
        f"Итоговая сумма заказа: {total_val}\n\n"
        "Для нового заказа используйте команду /start"
    )
    order_details = {
        "Order ID": int(order_id),
        "Date": current_time,
        "User": f"<https://t.me/{username}>",
        "Delivery Type": data.get("delivery_type", ""),
        "Location": data.get("location_info").split(': ',1)[1] if data.get("delivery_type") != 'delivery' else "",
        "Delivery Address": data.get("delivery_address", "") if data.get("delivery_type") == "delivery" else "",
        "Collection Name": data.get("collection")['name'],
        "Flavor Name": data.get("aroma_name"),
        "Manager": data.get("manager_name"),
        "Discount Applied": 0,
        "Status": False,
        "User ID": callback.from_user.id,
        "Total": total_val
    }
    try:
        orders_airtable.insert(order_details)
        logging.info("Order without discount inserted into Airtable successfully.")
    except Exception as e:
        logging.error(f"Failed to insert order details into Airtable: {e}")
        await callback.answer("Ошибка при сохранении заказа.", show_alert=True)
        return
    await callback.message.answer(customer_message, parse_mode="Markdown")
    try:
        await manager_bot.send_message(manager_id, manager_message, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Failed to send notification to manager: {e}")
    
    await state.clear()


@main_dp.callback_query(lambda c: c.data == "back")
async def process_back(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    try:
        await callback.message.delete()
    except Exception as e:
        logging.error(f"Failed to delete message: {e}")
    if current_state in [OrderStates.choosing_collection_type.state, OrderStates.choosing_product_type.state]:
        await show_delivery_options(callback, state)
    elif current_state == OrderStates.choosing_aroma.state:
        await process_collection_type(callback, state)
    elif current_state in [OrderStates.waiting_for_address.state, OrderStates.choosing_location.state]:
        await show_delivery_options(callback, state)
    else:
        await cmd_start(callback.message, state)

async def main():
    # Retrieve the main bot’s username for referral link generation.
    me = await main_bot.get_me()
    main_bot.username = me.username
    logging.info(f"Main bot username set to: {main_bot.username}")
    await asyncio.gather(
        main_dp.start_polling(main_bot),
        # Uncomment the following line if you wish to start polling for the manager bot:
        manager_dp.start_polling(manager_bot)
    )

if __name__ == '__main__':
    asyncio.run(main())