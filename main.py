import json
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from datetime import datetime
import os
import random
import pandas as pd

# Load configuration
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

# Initialize both bots
main_bot = Bot(token=config['api_key'])
manager_bot = Bot(token=config['manager_bot_token'])

# Configure logging
logging.basicConfig(level=logging.INFO)

# Create dispatchers for each bot
main_dp = Dispatcher()
manager_dp = Dispatcher()

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

def build_inventory(config):
    # Initialize inventory
    inventory = {key: {} for key in config["locations"].keys()}

    # Aggregate deliveries from postavka
    for postavka in config.get("postavka", []):
        for loc, delivery in postavka["deliveries"].items():
            item_quantities = delivery["items"]
            for item_id, qty in item_quantities.items():
                inventory[loc][item_id] = inventory[loc].get(item_id, 0) + qty

    return inventory

# Main bot handlers
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

@main_dp.message(Command("stats"))
async def cmd_stats(message: types.Message, state: FSMContext):
    # Load existing config
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        logging.error(f"Failed to load config: {e}")
        await message.answer("Ошибка при загрузке конфигурации.")
        return

    # Check if the user is authorized
    authorized_users = [config['manager_id']]
    if message.from_user.id not in authorized_users:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    # Build inventory
    inventory = build_inventory(config)

    # Subtract items from finished orders
    for order in config.get("orders", []):
        if order.get("status") == 1:  # Finished orders
            location_info = order["customer"].get("location_info", "")
            loc_key = None
            if "Магазин" in location_info:
                loc_key = location_info.split(": ")[1].strip()
                # Convert loc_key to key used in config["locations"]
                loc_key = next((k for k, v in config["locations"].items() if v["name"] == loc_key), None)
            
            # Check if product has an ID
            product = order.get("product", {})
            item_id = None
            for collection in config["catalog"]["hqd_collections"] + config["catalog"]["liquid_collections"]:
                if collection["name"] == product.get("collection"):
                    for item in collection["items"]:
                        if item["name"] == product.get("flavor"):
                            item_id = str(item["id"])
                            break

            if loc_key and item_id and loc_key in inventory:
                inventory[loc_key][item_id] = inventory[loc_key].get(item_id, 0) - 1
                if inventory[loc_key][item_id] < 0:
                    inventory[loc_key][item_id] = 0  # Prevent negative inventory

    # Prepare the DataFrame for the report
    data = []
    for loc_key, items in inventory.items():
        loc_name = config["locations"][loc_key]["name"]
        for item_id, qty in items.items():
            if qty > 0:
                # Get item name
                item_name = "Unknown Item"
                for collection in config["catalog"]["hqd_collections"] + config["catalog"]["liquid_collections"]:
                    for item in collection["items"]:
                        if str(item["id"]) == item_id:
                            item_name = item["name"]
                            break
                data.append({"Location": loc_name, "Item ID": item_id, "Item Name": item_name, "Quantity": qty})

    df = pd.DataFrame(data)

    # Save the DataFrame to an Excel file
    file_path = 'inventory_report.xlsx'
    df.to_excel(file_path, index=False)

    # Create an InputFile instance using the file path
    input_file = InputFile(file_path)

    # Send the Excel file to the user
    await message.answer_document(input_file, caption="📊 Инвентарь в формате Excel:")

    # Optionally, you can delete the file after sending
    os.remove(file_path)

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
    await show_collection_types(message, state)

async def show_collection_types(event, state: FSMContext):
    user_data = await state.get_data()
    # Load existing config
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        logging.error(f"Failed to load config: {e}")
        await event.answer("Ошибка при загрузке конфигурации.")
        return

    # Build inventory
    inventory = build_inventory(config)

    keyboard = []
    location_key = user_data.get('location')
    # Collections based on type
    collections = config["catalog"]["hqd_collections"] + config["catalog"]["liquid_collections"]
    for collection in collections:
        # Check if any items in the collection are available
        is_available = False
        for item in collection["items"]:
            item_id = str(item["id"])
            # For pickup, check location-specific availability
            if user_data.get('delivery_type') == 'pickup':
                if location_key in inventory and item_id in inventory[location_key] and inventory[location_key][item_id] > 0:
                    is_available = True
                    break
            else:
                # For delivery, assume available if any stock exists
                for loc in inventory.values():
                    if item_id in loc and loc[item_id] > 0:
                        is_available = True
                        break
        # Add emoji based on availability
        if is_available:
            collection_name = f"🟢 {collection['name']}"
        else:
            collection_name = f"🔴 {collection['name']}"
        keyboard.append([InlineKeyboardButton(
            text=collection_name,
            callback_data=f"type_{collection['id']}"
        )])

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
    
    if isinstance(event, types.CallbackQuery):
        try:
            await event.message.delete()
        except Exception as e:
            logging.error(f"Failed to delete message: {e}")
        await event.message.answer(
            text=message_text,
            reply_markup=reply_markup
        )
    else:
        await event.answer(
            text=message_text,
            reply_markup=reply_markup
        )
    await state.set_state(OrderStates.choosing_collection_type)

@main_dp.callback_query(lambda c: c.data.startswith('loc_'))
async def process_location(callback: types.CallbackQuery, state: FSMContext):
    location_key = callback.data.replace('loc_', '')
    await state.update_data(location=location_key)
    await show_collection_types(callback, state)

@main_dp.callback_query(lambda c: c.data.startswith('type_'))
async def process_collection_type(callback: types.CallbackQuery, state: FSMContext):
    collection_id = callback.data.replace('type_', '')
    await state.update_data(collection=collection_id)

    # Load existing config
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        logging.error(f"Failed to load config: {e}")
        await callback.answer("Ошибка при загрузке конфигурации.")
        return

    # Build inventory
    inventory = build_inventory(config)

    # Get the appropriate collection
    user_data = await state.get_data()
    collections = config["catalog"]["hqd_collections"] + config["catalog"]["liquid_collections"]
    collection = next((c for c in collections if c["id"] == collection_id), None)
    if not collection:
        await callback.answer("Коллекция не найдена.", show_alert=True)
        return

    await state.update_data(collection_type=collection_id)

    keyboard = []
    location_key = user_data.get('location')

    for item in collection["items"]:
        item_id = str(item["id"])
        # Check availability
        is_available = False
        if user_data.get('delivery_type') == 'pickup':
            if location_key in inventory and item_id in inventory[location_key] and inventory[location_key][item_id] > 0:
                is_available = True
        else:
            for loc in inventory.values():
                if item_id in loc and loc[item_id] > 0:
                    is_available = True
                    break

        # Add emoji based on availability
        if is_available:
            item_name = f"🟢 {item['name']}"
        else:
            item_name = f"🔴 {item['name']}"

        keyboard.append([InlineKeyboardButton(
            text=item_name,
            callback_data=f"aroma_{item['id']}"
        )])

    keyboard.append(create_back_button())
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    # Check delivery type and construct appropriate message
    if user_data.get('delivery_type') == 'delivery':
        message_text = (
            f"📍 Адрес доставки: {user_data['delivery_address']}\n\n"
            f"Выберите вкус из коллекции {collection['name']}:"
        )
    else:
        message_text = (
            f"📍 Выбранный магазин: {config['locations'][user_data['location']]['name']}\n\n"
            f"Выберите вкус из коллекции {collection['name']}:"
        )

    try:
        await callback.message.delete()
    except Exception as e:
        logging.error(f"Failed to delete message: {e}")
    await callback.message.answer(
        text=message_text,
        reply_markup=reply_markup
    )

    await state.set_state(OrderStates.choosing_aroma)

async def send_follow_up_message(message: types.Message):
    await asyncio.sleep(random.randint(1, 30))  # Random delay between 1-30 seconds
    await message.answer("🕐 Ваш заказ обрабатывается... Мы свяжемся с вами в течение 5 минут!")

@main_dp.callback_query(lambda c: c.data.startswith('aroma_'))
async def process_aroma(callback: types.CallbackQuery, state: FSMContext):
    # Load existing orders from config.json
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)

    # Build inventory
    inventory = build_inventory(config)

    user_data = await state.get_data()

    delivery_type = user_data.get('delivery_type', 'pickup')
    location_info = ""
    if delivery_type == "pickup":
        location_key = user_data['location']
        location_info = f"📍 Магазин: {config['locations'][location_key]['name']}"
    else:
        location_info = f"📍 Адрес доставки: {user_data['delivery_address']}"

    # Get collections based on type
    collections = config["catalog"]["hqd_collections"] + config["catalog"]["liquid_collections"]
    collection = next((c for c in collections if c["id"] == user_data['collection_type']), None)
    if not collection:
        await callback.answer("Коллекция не найдена.", show_alert=True)
        return

    aroma_id = callback.data.replace('aroma_', '')
    aroma = next((item for item in collection["items"] if str(item["id"]) == aroma_id), None)
    if not aroma:
        await callback.answer("Аромат не найден.", show_alert=True)
        return

    # Check availability
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

    try:
        await callback.message.delete()
    except Exception as e:
        logging.error(f"Failed to delete message: {e}")
    sent_message = await callback.message.answer(customer_message)

    # Start sending follow-up message
    asyncio.create_task(send_follow_up_message(sent_message))

    # Save order details to config.json with initial status
    order_details = {
        "order_id": order_id,
        "date": current_time,
        "customer": {
            "username": username,
            "fullname": user_fullname,
            "location_info": location_info,
        },
        "product": {
            "collection": collection['name'],
            "flavor": aroma['name'],
            "delivery_type": delivery_type,
        },
        "status": -1  # Initial status: -1 (Pending)
    }

    # Load existing orders from config.json
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)

    # Append new order to the orders list
    if "orders" not in config:
        config["orders"] = []  # Initialize orders list if it doesn't exist
    config["orders"].append(order_details)

    # Save updated config back to the file
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

    # Create buttons for success and cancel
    success_button = InlineKeyboardButton(text="✅ Success", callback_data=f"order_status_{order_id}_1")
    cancel_button = InlineKeyboardButton(text="❌ Cancel", callback_data=f"order_status_{order_id}_0")
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[[success_button, cancel_button]])

    # Send notification to the manager through manager bot
    try:
        sent_message = await manager_bot.send_message(config['manager_id'], manager_message, reply_markup=reply_markup)
        logging.info('Message to manager sent!')
    except Exception as e:
        logging.error(f"Failed to send notification to manager: {e}")

    # Update manager_message_id in order details
    order_details["manager_message_id"] = sent_message.message_id

    # Save updated config back to the file with manager_message_id
    # First, find the order in the config and update it
    for idx, order in enumerate(config["orders"]):
        if order["order_id"] == order_id:
            config["orders"][idx]["manager_message_id"] = sent_message.message_id
            break

    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

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
        # Go back to choosing delivery method
        await show_delivery_options(callback, state)
    
    elif current_state == OrderStates.choosing_collection.state:
        await show_collection_types(callback, state)
    
    elif current_state == OrderStates.choosing_aroma.state:
        # Get collections based on type
        await process_collection_type(callback, state)
    
    elif current_state == OrderStates.waiting_for_address.state:
        # Go back to delivery or pickup selection
        await show_delivery_options(callback, state)
    
    elif current_state == OrderStates.choosing_location.state:
        await show_delivery_options(callback, state)
    
    else:
        # If state is not recognized, start from the beginning
        await cmd_start(callback.message, state)

# Manager bot handlers
@manager_dp.callback_query(lambda c: c.data.startswith('order_status_'))
async def update_order_status(callback: types.CallbackQuery, state: FSMContext):
    _, _, order_id, status = callback.data.split('_')
    status = int(status)

    logging.info(f"Updating order status: {order_id} to {status}")  # Log the status update

    # Load existing orders from config.json
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)

    # Update the status of the specific order
    for idx, order in enumerate(config.get("orders", [])):
        if order["order_id"] == order_id:
            order["status"] = status  # Update the status

            # Delete the manager's message if it exists
            if "manager_message_id" in order:
                try:
                    await manager_bot.delete_message(config['manager_id'], order["manager_message_id"])
                    logging.info('Manager message deleted.')
                except Exception as e:
                    logging.error(f"Failed to delete manager message: {e}")
            config["orders"][idx] = order
            break
    else:
        logging.warning(f"Order ID {order_id} not found in orders.")

    # Save updated config back to the file 
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

    await callback.answer("Order status updated successfully.")

# Main function to run the bots
async def main():
    # Start polling both dispatchers concurrently
    await asyncio.gather(
        main_dp.start_polling(main_bot),
        manager_dp.start_polling(manager_bot)
    )

if __name__ == '__main__':
    asyncio.run(main())