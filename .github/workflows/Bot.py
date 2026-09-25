import os
import sqlite3
import json
import asyncio
from contextlib import closing
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

# --- CONFIGURATION (FILL THESE IN) ---
API_TOKEN = "8802905116:AAGCSn3033SwKWZBJa8JqxveXQbGBlspR3I"
ADMIN_ID = 8806907120  # Replace with your numerical Telegram User ID
CARD_NUMBER = "6219-8619-7743-3431"
CARD_OWNER = "MaTin Rahmanian"

MIN_GB = 10
MAX_GB = 500
PRICE_PER_GB = 8490

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- FSM STATES ---
class OrderForm(StatesGroup):
    volume = State()
    receipt = State()
    support = State()
    waiting_for_config = State()
    waiting_for_qr = State()

# --- DATABASE SETUP ---
def init_db():
    with closing(sqlite3.connect("bot_data.db")) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                volume INTEGER,
                price INTEGER,
                plan_name TEXT,
                receipt_id TEXT,
                config TEXT,
                subscription TEXT,
                status TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                text TEXT
            )
        """)
        db.commit()

def money(amount):
    return f"{amount:,}"

def get_price_for_custom_volume(volume):
    return volume * PRICE_PER_GB

def get_order(order_id):
    with closing(sqlite3.connect("bot_data.db")) as db:
        db.row_factory = sqlite3.Row
        return db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

def create_order(user_id, username, volume, price, plan_name):
    with closing(sqlite3.connect("bot_data.db")) as db:
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO orders (user_id, username, volume, price, plan_name, status) VALUES (?, ?, ?, ?, ?, 'pending_receipt')",
            (user_id, username, volume, price, plan_name)
        )
        db.commit()
        return cursor.lastrowid

def update_order(order_id, **kwargs):
    columns = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values()) + [order_id]
    with closing(sqlite3.connect("bot_data.db")) as db:
        db.execute(f"UPDATE orders SET {columns} WHERE id = ?", values)
        db.commit()

# --- CHAT DESIGNS / KEYBOARDS ---
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡️ خرید حجم دلخواه", callback_query_data="buy_custom")],
        [InlineKeyboardButton(text="💬 ارتباط با پشتیبانی", callback_query_data="support_chat")]
    ])

def admin_order_kb(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 تایید فیش", callback_query_data=f"approve:{order_id}"),
            InlineKeyboardButton(text="🔴 رد فیش", callback_query_data=f"reject:{order_id}")
        ]
    ])

# --- BOT COMMANDS & HANDLERS ---

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "⚡️ **به ربات کانفیگ با حجم دلخواه خوش آمدید**\n\n"
        "📦 سرویس‌های اختصاصی (۱۰ تا ۵۰۰ گیگ)\n"
        f"💰 قیمت هر گیگابایت: {money(PRICE_PER_GB)} تومان\n"
        "⏱ اعتبار زمانی: نامحدود\n\n"
        "گزینه مورد نظر خود را از منوی زیر انتخاب کنید:"
    )
    await message.answer(text, reply_markup=main_menu_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "buy_custom")
async def start_buy(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(OrderForm.volume)
    await callback.message.answer(f"📊 لطفاً حجم مورد نظر خود را به گیگابایت (فقط عدد صحیح بین {MIN_GB} تا {MAX_GB}) وارد کنید:")

@dp.message(OrderForm.volume)
async def receive_custom_volume(message: Message, state: FSMContext):
    try:
        volume = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ لطفاً فقط یک عدد صحیح وارد کنید.")
        return

    if not (MIN_GB <= volume <= MAX_GB):
        await message.answer(f"❌ حجم وارد شده باید بین {MIN_GB} تا {MAX_GB} گیگ باشد.")
        return

    price = get_price_for_custom_volume(volume)
    order_id = create_order(
        user_id=message.from_user.id,
        username=message.from_user.username,
        volume=volume,
        price=price,
        plan_name="حجم دلخواه",
    )

    await state.set_state(OrderForm.receipt)
    await state.update_data(order_id=order_id)

    owner = f"\nبه نام: {CARD_OWNER}" if CARD_OWNER else ""
    await message.answer(
        f"🧾 **سفارش #{order_id}**\n"
        f"📦 حجم: {volume} گیگ\n"
        f"💰 مبلغ: {money(price)} تومان\n"
        f"♾ اعتبار: نامحدود\n\n"
        f"💳 شماره کارت جهت واریز:\n`{CARD_NUMBER}`{owner}\n\n"
        "📸 لطفاً تصویر رسید خود را همین‌جا ارسال کنید."
    )

@dp.message(OrderForm.receipt, F.photo)
async def receive_receipt(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("order_id")
    if not order_id:
        await message.answer("❌ سفارش منقضی شده است. لطفا مجدد تلاش کنید.")
        return

    photo_id = message.photo[-1].file_id
    update_order(order_id, receipt_id=photo_id, status="pending_review")
    await state.clear()
    await message.answer("✅ رسید شما با موفقیت برای ادمین ارسال شد. سرویس پس از بررسی تحویل داده می‌شود.")

    order = get_order(order_id)
    if ADMIN_ID and order:
        await bot.send_photo(
            ADMIN_ID,
            photo_id,
            caption=(
                f"🚨 **رسید جدید پرداخت!**\n\n"
                f"📦 سفارش #{order_id}\n"
                f"👤 کاربر: {order['user_id']}\n"
                f"📊 حجم: {order['volume']} گیگ\n"
                f"💰 مبلغ: {money(order['price'])} تومان"
            ),
            reply_markup=admin_order_kb(order_id),
        )

@dp.message(OrderForm.receipt)
async def receipt_required(message: Message):
    await message.answer("⚠️ لطفاً فیش واریزی خود را فقط به صورت عکس ارسال کنید.")

# --- ADMIN VERIFICATION ACTIONS ---

@dp.callback_query(F.data.startswith("approve:"))
async def approve_order(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    order_id = int(callback.data.split(":")[1])
    order = get_order(order_id)

    if not order or order["status"] != "pending_review":
        await callback.answer("این سفارش قبلاً تعیین تکلیف شده است.", show_alert=True)
        return

    update_order(order_id, status="awaiting_delivery")
    await callback.answer("✅ تایید شد")
    await callback.message.edit_caption(caption=f"🟢 سفارش #{order_id} تایید شد. منتظر ارسال مشخصات...", reply_markup=None)
    await bot.send_message(order["user_id"], "✅ پرداخت شما تایید شد! کانفیگ اختصاصی شما به زودی ارسال می‌شود.")
    await bot.send_message(ADMIN_ID, f"📦 جهت تحویل سفارش #{order_id} دستور زیر را ارسال کنید:\n\n`/deliver {order_id}`")

@dp.callback_query(F.data.startswith("reject:"))
async def reject_order(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    order_id = int(callback.data.split(":")[1])
    order = get_order(order_id)

    if not order or order["status"] != "pending_review":
        await callback.answer("این سفارش قبلاً تعیین تکلیف شده است.", show_alert=True)
        return

    update_order(order_id, status="rejected")
    await callback.answer("❌ رد شد")
    await callback.message.edit_caption(caption=f"🔴 سفارش #{order_id} توسط شما رد شد.", reply_markup=None)
    await bot.send_message(order["user_id"], "❌ فیش واریزی شما رد شد. در صورت وجود اشتباه به پشتیبانی پیام دهید.")

# --- ORDER DELIVERY SYSTEM (COMPLETED) ---

@dp.message(Command("deliver"))
async def deliver(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("❌ فرمت اشتباه است. لطفاً به این صورت ارسال کنید:\n`/deliver ORDER_ID`")
        return

    try:
        order_id = int(parts[1])
    except ValueError:
        await message.answer("❌ شناسه سفارش باید عدد باشد.")
        return

    order = get_order(order_id)
    if not order:
        await message.answer("❌ سفارشی با این شناسه یافت نشد.")
        return

    await state.set_state(OrderForm.waiting_for_config)
    await state.update_data(delivery_order_id=order_id)
    await message.answer(f"🔗 لطفاً **متن کانفیگ (Vless/Vmess)** را برای سفارش #{order_id} ارسال کنید:")

@dp.message(OrderForm.waiting_for_config)
async def receive_delivery_config(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    order_id = data.get("delivery_order_id")
    config_text = message.text

    await state.update_data(config_text=config_text)
    await state.set_state(OrderForm.waiting_for_qr)
    await message.answer(f"📸 حالا لطفاً **عکس QR کد** مربوط به این کانفیگ را ارسال کنید (یا ارسال کلمه /skip برای صرف نظر از عکس):")

@dp.message(OrderForm.waiting_for_qr)
async def receive_delivery_qr(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    order_id = data.get("delivery_order_id")
    config_text = data.get("config_text")
    
    order = get_order(order_id)
    if not order:
        await message.answer("❌ خطا در یافتن سفارش.")
        await state.clear()
        return

    qr_photo_id = None
    if message.photo:
        qr_photo_id = message.photo[-1].file_id

    # Update database
