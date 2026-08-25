import asyncio
import html
import logging
import time
import os
from aiogram import Bot, Dispatcher, F, types
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
)
from database import Database

from fastapi import FastAPI
from uvicorn import Config, Server

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в переменных окружения")


ADMIN_ID = 7499731115
CHANNEL_ID = -1003927424016
CHANNEL_URL = "https://t.me/KV1ZER"

app = FastAPI()

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = Database()
logging.basicConfig(level=logging.INFO)



# --- УНИВЕРСАЛЬНАЯ КНОПКА ОТМЕНЫ ---
cancel_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_action")]
    ]
)


@dp.callback_query(F.data == "cancel_action")
async def cancel_action_handler(call: CallbackQuery, state: FSMContext):
  await state.clear()
  await call.message.edit_text("❌ Действие отменено.")
  await call.message.answer(
      "Главное меню:", reply_markup=await get_user_keyboard()
  )
  await call.answer()


# --- СОСТОЯНИЯ ---
class UserStates(StatesGroup):
  waiting_for_promo = State()
  waiting_for_custom_stars = State()
  waiting_for_task_photo = State()

  suggest_title = State()
  suggest_desc = State()
  suggest_category = State()
  suggest_link = State()


class AdminStates(StatesGroup):
  task_category = State()
  task_title = State()
  task_desc = State()
  task_reward = State()
  task_limit = State()

  promo_code = State()
  promo_reward = State()
  promo_limit = State()

  edit_button_state = State()

  broadcast_text = State()
  broadcast_photo = State()
  broadcast_markup = State()

  add_moderator = State()

  publish_reward = State()
  publish_limit = State()

  give_tokens_id = State()
  give_tokens_amount = State()


# --- ТЕКСТЫ И ПЕРЕВОДЫ ---
LANG_TEXTS = {
    "ru": {
        "start": (
            "👋 **Привет, это бот Квизера**, созданный специально для того,"
            " чтобы ты смог получить звёздочки на простых заданиях.\n\n🕹️"
            " **Перейдите по кнопке ниже в меню -**"
        ),
        "menu_greeting": (
            "🗄️ **Вы перешли в бот Квизера теперь вы можете:**\n\n- Выполнять"
            " задания и зарабатывать К-токен.\n\n- Обменивать К-токены на"
            " 🌟.\n\n> *Удачного пользования мы рады вас видеть* 💫"
        ),
        "menu_btn": "Меню",
        "choose_lang": (
            "🌍 **Выберите язык интерфейса / Choose your language:**"
        ),
    },
    "en": {
        "start": (
            "👋 **Hello, this is Quizer Bot**, created specifically for you"
            " to earn stars through simple tasks.\n\n🕹️ **Click the button below"
            " to open the menu -**"
        ),
        "menu_greeting": (
            "🗄️ **You are now in the Quizer menu, you can:**\n\n- Complete"
            " tasks and earn K-tokens.\n\n- Exchange K-tokens for 🌟.\n\n> *Have"
            " a great time, we are glad to see you* 💫"
        ),
        "menu_btn": "Menu",
        "choose_lang": (
            "🌍 **Choose your language / Выберите язык интерфейса:**"
        ),
    },
    "uk": {
        "start": (
            "👋 **Привіт, це бот Квізера**, створений спеціально для того,"
            " об ти зміг отримати зірочки на простих завданнях.\n\n🕹️"
            " **Перейдіть за кнопкою нижче в меню -**"
        ),
        "menu_greeting": (
            "🗄️ **Ви перейшли в меню Квізера, тепер ви можете:**\n\n-"
            " Виконувати завдання та заробляти К-токен.\n\n- Обмінювати К-токени"
            " на 🌟.\n\n> *Вдалих завдань, раді вас бачити* 💫"
        ),
        "menu_btn": "Меню",
        "choose_lang": "🌍 **Оберіть мову інтерфейсу:**",
    },
}


async def is_admin_or_moderator(user_id: int) -> bool:
  if user_id == ADMIN_ID:
    return True
  return await db.is_moderator(user_id)


async def check_subscription(user_id: int) -> bool:
  try:
    member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
    if member.status in ["creator", "administrator", "member"]:
      return True
  except Exception as e:
    logging.error(f"Ошибка при проверке подписки: {e}")
  return False


async def get_menu_keyboard(lang="ru"):
  text = LANG_TEXTS.get(lang, LANG_TEXTS["ru"])["menu_btn"]
  return ReplyKeyboardMarkup(
      keyboard=[[KeyboardButton(text=text)]], resize_keyboard=True
  )


async def get_user_keyboard():
  btns = await db.get_buttons_text()
  return ReplyKeyboardMarkup(
      keyboard=[
          [
              KeyboardButton(
                  text=btns.get("profile_text", "👤 Мой профиль")
              ),
              KeyboardButton(
                  text=btns.get("tasks_text", "🔍 Поиск заданий")
              ),
          ],
          [
              KeyboardButton(
                  text=btns.get("leaderboard_text", "🏆 Таблица лидеров")
              ),
              KeyboardButton(text=btns.get("donate_text", "💎 Помощь Боту")),
          ],
          [
              KeyboardButton(text="👥 Рефералы"),
              KeyboardButton(text="📢 Канал Kvizer"),
          ],
      ],
      resize_keyboard=True,
  )


@dp.message(CommandStart())
async def start(message: types.Message):
  user_id = message.from_user.id

  referrer_id = None
  if message.text and len(message.text.split()) > 1:
    try:
      referrer_id = int(message.text.split()[1])
    except:
      pass
    if referrer_id == user_id:
      referrer_id = None

  is_new = await db.add_user(
      user_id,
      message.from_user.username,
      message.from_user.first_name,
      referrer_id,
  )

  if is_new and referrer_id:
    ref_count = await db.get_user_referral_count(referrer_id)
    multiplier = 2 ** (ref_count // 100)
    reward_amount = 1 * multiplier

    await db.update_balance(referrer_id, reward_amount)
    await db.increment_invited_count(referrer_id)
    try:
      await bot.send_message(
          referrer_id,
          (
              "🎉 **У вас новый реферал!**\n\n💰 На ваш баланс начислено"
              f" `{reward_amount} К-токенов` (с учетом прогрессивного"
              " бонуса)."
          ),
          parse_mode="Markdown",
      )
    except:
      pass

  user = await db.get_user(user_id)
  user_dict = dict(user) if user else {}
  lang = user_dict.get("language")

  if not lang:
    lang_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🇷🇺 Русский", callback_data="setlang_ru"
                ),
                InlineKeyboardButton(
                    text="🇬🇧 English", callback_data="setlang_en"
                ),
                InlineKeyboardButton(
                    text="🇺🇦 Українська", callback_data="setlang_uk"
                ),
            ]
        ]
    )
    await message.answer(
        LANG_TEXTS["ru"]["choose_lang"],
        reply_markup=lang_kb,
        parse_mode="Markdown",
    )
  else:
    welcome_text = LANG_TEXTS.get(lang, LANG_TEXTS["ru"])["start"]
    await message.answer(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=await get_menu_keyboard(lang),
    )


@dp.callback_query(F.data == "check_sub_withdraw")
async def check_sub_withdraw_callback(call: CallbackQuery, state: FSMContext):
  user_id = call.from_user.id
  is_subscribed = await check_subscription(user_id)

  if not is_subscribed:
    await call.answer("❌ Вы все еще не подписаны на канал!", show_alert=True)
    return

  await call.message.delete()
  await call.answer("✅ Подписка подтверждена!")

  user = await db.get_user(user_id)
  
  withdraw_kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(text="15 К-токенов", callback_data="wd_amt_15"),
              InlineKeyboardButton(text="25 К-токенов", callback_data="wd_amt_25"),
              InlineKeyboardButton(text="50 К-токенов", callback_data="wd_amt_50"),
          ],
          [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_action")]
      ]
  )

  await call.message.answer(
      f"💸 **Вывод К-токенов**\n\nУ вас на балансе: `{user['balance']} К-токенов`.\nВыберите сумму для вывода:",
      parse_mode="Markdown",
      reply_markup=withdraw_kb
  )


@dp.callback_query(F.data.startswith("setlang_"))
async def set_language_callback(call: CallbackQuery):
  lang = call.data.replace("setlang_", "")
  user_id = call.from_user.id

  await db.set_user_language(user_id, lang)
  texts = LANG_TEXTS.get(lang, LANG_TEXTS["ru"])
  await call.message.edit_text(
      "✅ Язык успешно сохранен!"
      if lang == "ru"
      else (
          "✅ Language saved successfully!"
          if lang == "en"
          else "✅ Мову успішно збережено!"
      )
  )
  await call.message.answer(
      texts["start"],
      parse_mode="Markdown",
      reply_markup=await get_menu_keyboard(lang),
  )
  await call.answer()


@dp.message(F.text.in_({"Меню", "Menu"}))
async def open_menu(message: types.Message):
  user_id = message.from_user.id
  user = await db.get_user(user_id)
  user_dict = dict(user) if user else {}
  lang = user_dict.get("language", "ru")

  menu_text = LANG_TEXTS.get(lang, LANG_TEXTS["ru"])["menu_greeting"]
  await message.answer(
      menu_text, parse_mode="Markdown", reply_markup=await get_user_keyboard()
  )


# ==========================================
# СОЗДАНИЕ ЗАДАНИЙ АДМИНИСТРАТОРОМ
# ==========================================
@dp.callback_query(F.data.startswith("admin_cat_"))
async def process_task_category(call: CallbackQuery, state: FSMContext):
  if not await is_admin_or_moderator(call.from_user.id):
    return
  category = call.data.replace("admin_cat_", "")
  await state.update_data(task_category=category)
  await state.set_state(AdminStates.task_title)
  await call.message.edit_text(
      "✏️ **Создание задания (Шаг 2/5)**\n\nВведите название задания:",
      parse_mode="Markdown",
      reply_markup=cancel_kb,
  )
  await call.answer()


@dp.message(AdminStates.task_title)
async def process_task_title(message: types.Message, state: FSMContext):
  if not await is_admin_or_moderator(message.from_user.id):
    return
  await state.update_data(task_title=message.text.strip())
  await state.set_state(AdminStates.task_desc)
  await message.answer(
      "📝 **Создание задания (Шаг 3/5)**\n\nВведите **описание** задания:",
      parse_mode="Markdown",
      reply_markup=cancel_kb,
  )


@dp.message(AdminStates.task_desc)
async def process_task_desc(message: types.Message, state: FSMContext):
  if not await is_admin_or_moderator(message.from_user.id):
    return
  await state.update_data(task_desc=message.text.strip())
  await state.set_state(AdminStates.task_reward)
  await message.answer(
      (
          "💰 **Создание задания (Шаг 4/5)**\n\nВведите **награду** (число в"
          " К-токенах):"
      ),
      parse_mode="Markdown",
      reply_markup=cancel_kb,
  )


@dp.message(AdminStates.task_reward)
async def process_task_reward(message: types.Message, state: FSMContext):
  if not await is_admin_or_moderator(message.from_user.id):
    return
  try:
    reward = int(message.text.strip())
    if reward <= 0:
      raise ValueError
  except ValueError:
    await message.answer(
        "⚠️ Введите корректное целое число для награды:", reply_markup=cancel_kb
    )
    return

  await state.update_data(task_reward=reward)
  await state.set_state(AdminStates.task_limit)
  await message.answer(
      (
          "👥 **Создание задания (Шаг 5/5)**\n\nВведите **количество"
          " выполнений** (сколько пользователей могут выполнить задание):"
      ),
      parse_mode="Markdown",
      reply_markup=cancel_kb,
  )


@dp.message(AdminStates.task_limit)
async def process_task_limit(message: types.Message, state: FSMContext):
  if not await is_admin_or_moderator(message.from_user.id):
    return
  try:
    max_limit = int(message.text.strip())
    if max_limit <= 0:
      raise ValueError
  except ValueError:
    await message.answer(
        "⚠️ Введите положительное число для лимита:", reply_markup=cancel_kb
    )
    return

  data = await state.get_data()
  await db.add_task(
      title=data["task_title"],
      description=data["task_desc"],
      reward=data["task_reward"],
      category=data["task_category"],
      max_limit=max_limit,
  )
  await state.clear()
  await message.answer(
      "✅ Задание успешно создано и опубликовано!",
      reply_markup=await get_user_keyboard(),
  )


# ==========================================
# ПРЕДЛОЖЕНИЕ ЗАДАНИЙ ПОЛЬЗОВАТЕЛЯМИ
# ==========================================
@dp.callback_query(F.data == "suggest_task_start")
async def suggest_task_start(call: CallbackQuery, state: FSMContext):
  await state.set_state(UserStates.suggest_title)
  await call.message.answer(
      "💡 **Бесплатное предложение задания (Шаг 1/4)**\n\nВведите название"
      " задания (например: *Подписаться на мой канал*):",
      parse_mode="Markdown",
      reply_markup=cancel_kb,
  )
  await call.answer()


@dp.message(UserStates.suggest_title)
async def suggest_get_title(message: types.Message, state: FSMContext):
  await state.update_data(suggest_title=message.text.strip())
  await state.set_state(UserStates.suggest_desc)
  await message.answer(
      (
          "📝 **Предложение задания (Шаг 2/4)**\n\nВведите описание и ссылку"
          " на задание:"
      ),
      parse_mode="Markdown",
      reply_markup=cancel_kb,
  )


@dp.message(UserStates.suggest_desc)
async def suggest_get_desc(message: types.Message, state: FSMContext):
  await state.update_data(suggest_desc=message.text.strip())

  cat_kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="📢 Подписки", callback_data="suggcat_sub")],
          [InlineKeyboardButton(text="👀 Просмотры", callback_data="suggcat_views")],
          [
              InlineKeyboardButton(
                  text="💬 Активность", callback_data="suggcat_activity"
              )
          ],
          [InlineKeyboardButton(text="⭐ Другое", callback_data="suggcat_other")],
          [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_action")],
      ]
  )
  await state.set_state(UserStates.suggest_category)
  await message.answer(
      "🎯 **Предложение задания (Шаг 3/4)**\n\nВыберите категорию:",
      reply_markup=cat_kb,
      parse_mode="Markdown",
  )


@dp.callback_query(F.data.startswith("suggcat_"), UserStates.suggest_category)
async def suggest_get_category(call: CallbackQuery, state: FSMContext):
  category = call.data.replace("suggcat_", "")
  await state.update_data(suggest_category=category)

  data = await state.get_data()
  raw_username = call.from_user.username or call.from_user.first_name
  safe_username = html.escape(str(raw_username))

  await db.add_suggested_task(
      user_id=call.from_user.id,
      username=safe_username,
      title=data["suggest_title"],
      description=data["suggest_desc"],
      category=category,
  )
  await state.clear()
  await call.message.edit_text(
      "✅ **Задание успешно отправлено на модерацию!**\n\nЕсли модераторы одобрят"
      " и опубликуют его, вы получите **5 К-токенов** на баланс!",
      parse_mode="Markdown",
  )
  await call.answer()


@dp.callback_query(F.data == "admin_suggested_tasks")
async def view_suggested_tasks(call: CallbackQuery):
  if not await is_admin_or_moderator(call.from_user.id):
    return

  tasks = await db.get_pending_suggested_tasks()
  if not tasks:
    await call.message.answer("🙅‍♂️ Нет предложенных заданий.")
    await call.answer()
    return

  for t in tasks:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Опубликовать", callback_data=f"pubsugg_{t['id']}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отклонить", callback_data=f"rejsugg_{t['id']}"
                )
            ],
        ]
    )
    safe_username = html.escape(str(t["username"] if "username" in t.keys() and t["username"] else ""))
    safe_title = html.escape(str(t["title"] if "title" in t.keys() and t["title"] else ""))
    safe_category = html.escape(str(t["category"] if "category" in t.keys() and t["category"] else ""))
    safe_description = html.escape(str(t["description"] if "description" in t.keys() and t["description"] else ""))

    text = (
        f"💡 **Предложенное задание ID: {t['id']}**\n"
        f"👤 От: @{safe_username} (ID: `{t['user_id']}`)\n"
        f"📌 Название: {safe_title}\n"
        f"🏷 Категория: {safe_category}\n"
        f"📝 Описание: {safe_description}"
    )
    await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
  await call.answer()


@dp.callback_query(F.data.startswith("rejsugg_"))
async def reject_suggested_task(call: CallbackQuery):
  if not await is_admin_or_moderator(call.from_user.id):
    return
  sugg_id = int(call.data.split("_")[1])
  await db.resolve_suggested_task(sugg_id, approve=False)
  await call.message.edit_text(
      call.message.text + "\n\n❌ **Отклонено**", parse_mode="Markdown"
  )
  await call.answer("Задание отклонено.")


@dp.callback_query(F.data.startswith("pubsugg_"))
async def publish_suggested_task_start(call: CallbackQuery, state: FSMContext):
  if not await is_admin_or_moderator(call.from_user.id):
    return
  sugg_id = int(call.data.split("_")[1])

  await state.set_state(AdminStates.publish_reward)
  await state.update_data(sugg_id=sugg_id)
  await call.message.answer(
      "💰 Введите **награду** для этого задания (в К-токенах):",
      parse_mode="Markdown",
      reply_markup=cancel_kb,
  )
  await call.answer()


@dp.message(AdminStates.publish_reward)
async def publish_get_reward(message: types.Message, state: FSMContext):
  if not await is_admin_or_moderator(message.from_user.id):
    return
  try:
    reward = int(message.text.strip())
    if reward <= 0:
      raise ValueError
  except ValueError:
    await message.answer("⚠️ Введите число больше 0:", reply_markup=cancel_kb)
    return

  await state.update_data(publish_reward=reward)
  await state.set_state(AdminStates.publish_limit)
  await message.answer(
      "👥 Введите **лимит выполнений** для этого задания:",
      parse_mode="Markdown",
      reply_markup=cancel_kb,
  )


@dp.message(AdminStates.publish_limit)
async def publish_get_limit(message: types.Message, state: FSMContext):
  if not await is_admin_or_moderator(message.from_user.id):
    return
  try:
    limit = int(message.text.strip())
    if limit <= 0:
      raise ValueError
  except ValueError:
    await message.answer("⚠️ Введите число больше 0:", reply_markup=cancel_kb)
    return

  data = await state.get_data()
  sugg_id = data["sugg_id"]
  reward = data["publish_reward"]

  sugg_task = await db.get_suggested_task_by_id(sugg_id)
  if sugg_task:
    await db.add_task(
        title=sugg_task["title"],
        description=sugg_task["description"],
        reward=reward,
        category=sugg_task["category"],
        max_limit=limit,
    )
    await db.resolve_suggested_task(sugg_id, approve=True)
    await db.update_balance(sugg_task["user_id"], 5)

    try:
      await bot.send_message(
          sugg_task["user_id"],
          (
              "🎉 **Ваше предложенное задание было опубликовано!**\n\n💰 Вам"
              " начислено вознаграждение: `5 К-токенов`."
          ),
          parse_mode="Markdown",
      )
    except:
      pass

  await state.clear()
  await message.answer(
      "✅ Задание успешно опубликовано, автору начислено 5 токенов!",
      reply_markup=await get_user_keyboard(),
  )


# ==========================================
# МОДЕРАТОРЫ И ВЫДАЧА ТОКЕНОВ
# ==========================================
@dp.callback_query(F.data == "admin_moderators")
async def admin_moderators_menu(call: CallbackQuery):
  if call.from_user.id != ADMIN_ID:
    return
  mods = await db.get_all_moderators()

  msg = "🛡️ **Управление модераторами**\n\nТекущие модераторы (ID):\n"
  if not mods:
    msg += "Список пуст."
  else:
    for m in mods:
      msg += f"• `{m['user_id']}`\n"

  kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="➕ Добавить модератора", callback_data="mod_add"
              )
          ],
          [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_action")],
      ]
  )
  await call.message.edit_text(msg, reply_markup=kb, parse_mode="Markdown")
  await call.answer()


@dp.callback_query(F.data == "mod_add")
async def mod_add_start(call: CallbackQuery, state: FSMContext):
  if call.from_user.id != ADMIN_ID:
    return
  await state.set_state(AdminStates.add_moderator)
  await call.message.answer(
      "🆔 Отправьте **Telegram ID** пользователя, которого хотите сделать"
      " модератором:",
      parse_mode="Markdown",
      reply_markup=cancel_kb,
  )
  await call.answer()


@dp.message(AdminStates.add_moderator, F.from_user.id == ADMIN_ID)
async def mod_save_moderator(message: types.Message, state: FSMContext):
  try:
    mod_id = int(message.text.strip())
  except ValueError:
    await message.answer(
        "⚠️ Введите корректный числовой ID:", reply_markup=cancel_kb
    )
    return

  await db.add_moderator(mod_id)
  await state.clear()
  await message.answer(
      f"✅ Пользователь `{mod_id}` назначен модератором!",
      parse_mode="Markdown",
      reply_markup=await get_user_keyboard(),
  )


@dp.callback_query(F.data == "admin_give_tokens")
async def admin_give_tokens_start(call: CallbackQuery, state: FSMContext):
  if not await is_admin_or_moderator(call.from_user.id):
    return
  await state.set_state(AdminStates.give_tokens_id)
  await call.message.answer(
      "🆔 Введите **Telegram ID** пользователя, которому хотите выдать"
      " К-токены:",
      parse_mode="Markdown",
      reply_markup=cancel_kb,
  )
  await call.answer()


@dp.message(AdminStates.give_tokens_id)
async def process_give_tokens_id(message: types.Message, state: FSMContext):
  if not await is_admin_or_moderator(message.from_user.id):
    return
  try:
    target_id = int(message.text.strip())
  except ValueError:
    await message.answer(
        "⚠️ Введите корректный числовой ID:", reply_markup=cancel_kb
    )
    return

  await state.update_data(target_id=target_id)
  await state.set_state(AdminStates.give_tokens_amount)
  await message.answer(
      "💰 Введите **количество К-токенов** для начисления:",
      parse_mode="Markdown",
      reply_markup=cancel_kb,
  )


@dp.message(AdminStates.give_tokens_amount)
async def process_give_tokens_amount(message: types.Message, state: FSMContext):
  if not await is_admin_or_moderator(message.from_user.id):
    return
  try:
    amount = int(message.text.strip())
    if amount == 0:
      raise ValueError
  except ValueError:
    await message.answer("⚠️ Введите целое число:", reply_markup=cancel_kb)
    return

  data = await state.get_data()
  target_id = data["target_id"]

  await db.update_balance(target_id, amount)
  await state.clear()

  await message.answer(
      f"✅ Успешно начислено `{amount} К-токенов` пользователю `{target_id}`!",
      parse_mode="Markdown",
      reply_markup=await get_user_keyboard(),
  )

  try:
    await bot.send_message(
        target_id,
        f"🎁 Администратор начислил вам `{amount} К-токенов` на баланс!",
        parse_mode="Markdown",
    )
  except:
    pass


# ==========================================
# УПРАВЛЕНИЕ ЗАЯВКАМИ НА ВЫВОД В АДМИНКЕ
# ==========================================
@dp.callback_query(F.data == "admin_withdrawals")
async def admin_withdrawals_menu(call: CallbackQuery):
  if not await is_admin_or_moderator(call.from_user.id):
    return

  withdrawals = await db.get_pending_withdrawals()
  if not withdrawals:
    await call.message.edit_text(
        "📭 **Нет активных заявок на вывод.**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="« Назад в админку", callback_data="admin_panel_back"
                    )
                ]
            ]
        ),
    )
    await call.answer()
    return

  await call.message.edit_text(
      "💸 **Список заявок на вывод средств:**", parse_mode="Markdown"
  )

  for w in withdrawals:
    w_username = w["username"] if "username" in w.keys() and w["username"] else ""
    w_firstname = w["first_name"] if "first_name" in w.keys() and w["first_name"] else ""
    safe_username = html.escape(str(w_username))
    safe_first_name = html.escape(str(w_firstname))
    username_info = (
        f"@{safe_username}" if w_username else safe_first_name
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Одобрить", callback_data=f"admin_wd_ok_{w['id']}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить", callback_data=f"admin_wd_no_{w['id']}"
                ),
            ]
        ]
    )
    await call.message.answer(
        f"👤 Пользователь: {username_info} (ID: <code>{w['user_id']}</code>)\n💰 Сумма вывода: <b>{w['amount']} К-токенов</b>",
        reply_markup=kb,
        parse_mode="HTML",
    )
  await call.answer()


@dp.callback_query(F.data.startswith("admin_wd_ok_"))
async def admin_approve_withdrawal(call: CallbackQuery):
  if not await is_admin_or_moderator(call.from_user.id):
    return
  wd_id = int(call.data.replace("admin_wd_ok_", ""))

  wd = await db.resolve_withdrawal(wd_id, approve=True)
  if wd:
    await call.message.edit_text(
        call.message.text + "\n\n✅ **Статус: Одобрено**", parse_mode="Markdown"
    )
    try:
      await bot.send_message(
          wd["user_id"],
          (
              "✅ **Ваша заявка на вывод"
              f" `{wd['amount']} К-токенов` успешно одобрена!**"
          ),
          parse_mode="Markdown",
      )
    except:
      pass
  await call.answer("Заявка одобрена.")


@dp.callback_query(F.data.startswith("admin_wd_no_"))
async def admin_reject_withdrawal(call: CallbackQuery):
  if not await is_admin_or_moderator(call.from_user.id):
    return
  wd_id = int(call.data.replace("admin_wd_no_", ""))

  wd = await db.resolve_withdrawal(wd_id, approve=False)
  if wd:
    await call.message.edit_text(
        call.message.text
        + "\n\n❌ **Статус: Отклонено (средства возвращены)**",
        parse_mode="Markdown",
    )
    try:
      await bot.send_message(
          wd["user_id"],
          (
              "❌ **Ваша заявка на вывод"
              f" `{wd['amount']} К-токенов` отклонена.** Средства возвращены"
              " на баланс."
          ),
          parse_mode="Markdown",
      )
    except:
      pass
  await call.answer("Заявка отклонена, средства возвращены.")


@dp.callback_query(F.data == "admin_panel_back")
async def admin_panel_back(call: CallbackQuery):
  if not await is_admin_or_moderator(call.from_user.id):
    return
  await admin_panel(call)


# ==========================================
# ПРОМОКОДЫ И КНОПКИ
# ==========================================
@dp.message(AdminStates.promo_code, F.from_user.id == ADMIN_ID)
async def process_promo_code(message: types.Message, state: FSMContext):
  await state.update_data(promo_code=message.text.strip())
  await state.set_state(AdminStates.promo_reward)
  await message.answer(
      "🎁 **Создание промокода (Шаг 2/3)**\n\nВведите сумму награды в К-токенах:",
      parse_mode="Markdown",
      reply_markup=cancel_kb,
  )


@dp.message(AdminStates.promo_reward, F.from_user.id == ADMIN_ID)
async def process_promo_reward(message: types.Message, state: FSMContext):
  try:
    reward = int(message.text.strip())
  except ValueError:
    await message.answer("⚠️ Введите число:", reply_markup=cancel_kb)
    return
  await state.update_data(promo_reward=reward)
  await state.set_state(AdminStates.promo_limit)
  await message.answer(
      "🎁 **Создание промокода (Шаг 3/3)**\n\nВведите лимит активаций:",
      parse_mode="Markdown",
      reply_markup=cancel_kb,
  )


@dp.message(AdminStates.promo_limit, F.from_user.id == ADMIN_ID)
async def process_promo_limit(message: types.Message, state: FSMContext):
  try:
    limit = int(message.text.strip())
  except ValueError:
    await message.answer("⚠️ Введите число:", reply_markup=cancel_kb)
    return

  data = await state.get_data()
  try:
    await db.add_promo(data["promo_code"], data["promo_reward"], limit)
    await state.clear()
    await message.answer(
        f"✅ Промокод `{data['promo_code']}` успешно создан!",
        parse_mode="Markdown",
        reply_markup=await get_user_keyboard(),
    )
  except:
    await message.answer("❌ Ошибка: возможно, такой промокод уже существует.")
    await state.clear()


@dp.message(AdminStates.edit_button_state, F.from_user.id == ADMIN_ID)
async def save_edited_button(message: types.Message, state: FSMContext):
  data = await state.get_data()
  button_name = data.get("button_name")

  new_text = ""
  if message.sticker:
    emoji = message.sticker.emoji or "⭐"
    new_text = f"{emoji} Кнопка"
  elif message.text:
    new_text = message.text.strip()
  else:
    new_text = "Новая кнопка"

  if button_name:
    await db.update_button_text(button_name, new_text)
    await message.answer(
        f"✅ **Название кнопки успешно изменено на:** `{new_text}`",
        parse_mode="Markdown",
        reply_markup=await get_user_keyboard(),
    )

  await state.clear()


# ==========================================
# РАССЫЛКА
# ==========================================
@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(call: CallbackQuery, state: FSMContext):
  if not await is_admin_or_moderator(call.from_user.id):
    return
  await state.set_state(AdminStates.broadcast_text)
  await call.message.answer(
      (
          "📢 **Массовая рассылка (Шаг 1/3)**\n\nОтправьте текст рассылки"
          " (поддерживается Markdown):"
      ),
      parse_mode="Markdown",
      reply_markup=cancel_kb,
  )
  await call.answer()


@dp.message(AdminStates.broadcast_text)
async def broadcast_get_text(message: types.Message, state: FSMContext):
  if not await is_admin_or_moderator(message.from_user.id):
    return
  await state.update_data(b_text=message.text or message.caption)
  await state.set_state(AdminStates.broadcast_photo)
  await message.answer(
      (
          "📸 **Массовая рассылка (Шаг 2/3)**\n\nОтправьте картинку для"
          " рассылки или напишите `нет`:"
      ),
      parse_mode="Markdown",
      reply_markup=cancel_kb,
  )


@dp.message(AdminStates.broadcast_photo)
async def broadcast_get_photo(message: types.Message, state: FSMContext):
  if not await is_admin_or_moderator(message.from_user.id):
    return
  photo_id = None
  if message.photo:
    photo_id = message.photo[-1].file_id
  elif message.text and message.text.lower() == "нет":
    photo_id = None

  await state.update_data(b_photo=photo_id)
  await state.set_state(AdminStates.broadcast_markup)
  await message.answer(
      "🔗 **Массовая рассылка (Шаг 3/3)**\n\nОтправьте инлайн-кнопки в"
      " формате:\n`Текст кнопки - https://t.link`\nИли напишите `нет`:",
      parse_mode="Markdown",
      reply_markup=cancel_kb,
  )


@dp.message(AdminStates.broadcast_markup)
async def broadcast_get_markup(message: types.Message, state: FSMContext):
  if not await is_admin_or_moderator(message.from_user.id):
    return
  data = await state.get_data()
  b_text = data.get("b_text")
  b_photo = data.get("b_photo")

  reply_markup = None
  if message.text and message.text.lower() != "нет":
    rows = []
    for line in message.text.split("\n"):
      if "-" in line:
        parts = line.split("-", 1)
        btn_txt = parts[0].strip()
        btn_url = parts[1].strip()
        rows.append([InlineKeyboardButton(text=btn_txt, url=btn_url)])
    if rows:
      reply_markup = InlineKeyboardMarkup(inline_keyboard=rows)

  users = await db.get_all_users()
  await state.clear()

  await message.answer(
      f"🚀 **Рассылка запущена!** Пользователей: `{len(users)}`",
      parse_mode="Markdown",
      reply_markup=await get_user_keyboard(),
  )

  success = 0
  fail = 0
  for u in users:
    uid = u["user_id"]
    try:
      if b_photo:
        await bot.send_photo(
            chat_id=uid,
            photo=b_photo,
            caption=b_text,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
      else:
        await bot.send_message(
            chat_id=uid,
            text=b_text,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
      success += 1
      await asyncio.sleep(0.05)
    except:
      fail += 1

  await message.answer(
      f"✅ **Рассылка завершена!**\n\n📩 Доставлено: `{success}`\n❌ Ошибок:"
      f" `{fail}`",
      parse_mode="Markdown",
  )


# ==========================================
# ПОЛЬЗОВАТЕЛЬСКИЕ СОСТОЯНИЯ
# ==========================================
@dp.message(UserStates.waiting_for_custom_stars)
async def process_custom_stars_input(message: types.Message, state: FSMContext):
  try:
    amount = int(message.text.strip())
    if amount <= 0:
      raise ValueError
  except ValueError:
    await message.answer(
        "⚠️ Пожалуйста, введите корректное положительное число звезд:",
        reply_markup=cancel_kb,
    )
    return

  await state.clear()
  await message.answer(
      f"📦 Счет на оплату `{amount} ⭐` сгенерирован:", parse_mode="Markdown"
  )
  prices = [LabeledPrice(label="Помощь боту", amount=amount)]
  await bot.send_invoice(
      chat_id=message.from_user.id,
      title="Помощь проекту",
      description=f"Пожертвование на развитие бота в размере {amount} ⭐",
      payload=f"donate_{amount}_{message.from_user.id}",
      currency="XTR",
      prices=prices,
  )


@dp.message(UserStates.waiting_for_promo)
async def process_user_promo(message: types.Message, state: FSMContext):
  code = message.text.strip()
  reward = await db.apply_promo(code)

  if reward:
    await db.update_balance(message.from_user.id, reward)
    await message.answer(
        (
            "✅ **Промокод успешно активирован!**\n\n💰 Баланс пополнен на"
            f" `{reward} К-токенов`."
        ),
        parse_mode="Markdown",
        reply_markup=await get_user_keyboard(),
    )
  else:
    await message.answer(
        "❌ **Ошибка:** Неверный или просроченный промокод.",
        parse_mode="Markdown",
        reply_markup=await get_user_keyboard(),
    )
  await state.clear()


@dp.message(UserStates.waiting_for_task_photo, F.photo)
async def handle_photo_submit(message: types.Message, state: FSMContext):
  data = await state.get_data()
  task_id = data.get("task_id")

  if task_id:
    task = await db.get_task_by_id(task_id)
    if task:
      await db.add_submission(
          message.from_user.id, task_id, message.photo[-1].file_id
      )
      await message.answer(
          "✅ **Скриншот успешно отправлен!**\n\nОжидайте проверки.",
          parse_mode="Markdown",
          reply_markup=await get_user_keyboard(),
      )
    else:
      await message.answer(
          "❌ Ошибка: задание не найдено.",
          reply_markup=await get_user_keyboard(),
      )

  await state.clear()


# ==========================================
# ОСНОВНОЙ ОБРАБОТЧИК КНОПОК ГЛАВНОГО МЕНЮ
# ==========================================
@dp.message(F.text)
async def handle_main(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  btns = await db.get_buttons_text()
  text = message.text

  if text == "📢 Канал Kvizer":
    channel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Перейти в канал 🚀", url=CHANNEL_URL)]
        ]
    )
    await message.answer(
        "Чтобы перейти в канал нажмите на кнопку ниже 👇",
        reply_markup=channel_kb,
    )
    return

  if text == "👥 Рефералы":
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    ref_count = await db.get_user_referral_count(user_id)
    current_mult = 2 ** (ref_count // 100)

    ref_text = (
        "👥 **Реферальная система**\n\nПриглашайте друзей и получайте"
        f" награды!\n• Базовая награда: **1 К-токен** за реферала\n• Прогрессивный"
        f" бонус: за каждые **100 рефералов** награда **удваивается** (сейчас"
        f" ваш множитель: `x{current_mult}`)\n\n🔗 Ваша реферальная"
        f" ссылка:\n`{ref_link}`\n\n📊 Приглашено друзей: `{ref_count}`"
    )
    await message.answer(ref_text, parse_mode="Markdown")
    return

  if text == btns.get("profile_text", "👤 Мой профиль"):
    user = await db.get_user(user_id)
    if not user:
      await db.add_user(
          user_id,
          message.from_user.username,
          message.from_user.first_name,
      )
      user = await db.get_user(user_id)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=btns.get("promo_text", "Ввести промокод"),
                    callback_data="user_promo",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💸 Вывести", callback_data="user_withdraw"
                )
            ],
        ]
    )

    if await is_admin_or_moderator(user_id):
      keyboard.inline_keyboard.append([
          InlineKeyboardButton(
              text=btns.get("admin_panel_text", "Админ панель"),
              callback_data="admin_panel",
          )
      ])

    profile = (
        "👤 **Личный кабинет**\n\n🆔 **ID:**"
        f" `{user['user_id']}`\n💰 **Баланс:** `{user['balance']}"
        f" К-токенов`\n📋 **Выполнено заданий:**"
        f" `{user['completed_tasks']}`\n👥 **Приглашено друзей:**"
        f" `{user['invited_count']}`\n"
    )

    if user_id == ADMIN_ID:
      total_users, total_given = await db.get_total_stats()
      profile += (
          "\n📈 **Статистика бота:**\n👤 Всего юзеров:"
          f" `{total_users}`\n💎 Выдано К-токенов: `{total_given}`"
      )

    await message.answer(profile, reply_markup=keyboard, parse_mode="Markdown")

  elif text == btns.get("tasks_text", "🔍 Поиск заданий"):
    tasks = await db.get_weekly_available_tasks(user_id, limit=3)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Предложить задание",
                    callback_data="suggest_task_start",
                )
            ]
        ]
    )

    if not tasks:
      await message.answer(
          "😴 На этой неделе вы уже выполнили доступные задания (лимит: 3"
          " задания в неделю) либо заданий пока нет.",
          reply_markup=keyboard,
      )
      return

    msg = "🎯 **Доступные задания для вас (до 3 в неделю):**\n\n"
    for t in tasks:
      safe_t_title = html.escape(str(t["title"] if "title" in t.keys() and t["title"] else ""))
      safe_t_desc = html.escape(str(t["description"] if "description" in t.keys() and t["description"] else ""))
      
      msg += (
          f"📌 <b>{safe_t_title}</b>\n📝 {safe_t_desc}\n💰 Награда:"
          f" <b>{t['reward']} К-токенов</b>\n➖➖➖➖➖➖➖\n"
      )
      keyboard.inline_keyboard.insert(
          0,
          [
              InlineKeyboardButton(
                  text=f"Выполнить: {t['title']}",
                  callback_data=f"take_{t['id']}",
              )
          ],
      )

    await message.answer(msg, reply_markup=keyboard, parse_mode="HTML")

  elif text == btns.get("leaderboard_text", "🏆 Таблица лидеров"):
    lb_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👨‍💻 Реферальная", callback_data="top_referrals"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💸 Выводы токенов", callback_data="top_withdrawals"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🤖 Помощь боту", callback_data="top_donates"
                )
            ],
        ]
    )
    await message.answer(
        "🏆 **Выберете таблицу 👇**", reply_markup=lb_kb, parse_mode="Markdown"
    )

  elif text == btns.get("donate_text", "💎 Помощь Боту"):
    donate_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="5 ⭐", callback_data="donate_5"),
                InlineKeyboardButton(text="10 ⭐", callback_data="donate_10"),
                InlineKeyboardButton(text="15 ⭐", callback_data="donate_15"),
            ],
            [
                InlineKeyboardButton(
                    text="👨‍💻 Свое количество", callback_data="donate_custom"
                )
            ],
        ]
    )
    await message.answer(
        "🤖 **Выберете сумму пожертвования на развитие бота**",
        reply_markup=donate_kb,
        parse_mode="Markdown",
    )


# --- ТАБЛИЦА ЛИДЕРОВ ---
@dp.callback_query(F.data.startswith("top_"))
async def show_leaderboard(call: CallbackQuery):
  cat = call.data.replace("top_", "")
  users = await db.get_top_users(cat)

  titles = {
      "referrals": "👨‍💻 **Топ-10 по приглашенным рефералам:**",
      "withdrawals": "💸 **Топ-10 по выводу токенов:**",
      "donates": "🤖 **Топ-10 по помощи боту (донаты):**",
  }

  msg = titles.get(cat, "🏆 **Таблица лидеров:**") + "\n\n"
  if not users:
    msg += "Пока нет участников в этой таблице."
  else:
    for i, u in enumerate(users, start=1):
      u_username = u["username"] if "username" in u.keys() and u["username"] else ""
      u_firstname = u["first_name"] if "first_name" in u.keys() and u["first_name"] else ""
      raw_name = u_username or u_firstname
      name = html.escape(str(raw_name))
      val = u["val"] or 0
      if cat == "referrals":
        suffix = " реф."
      elif cat == "withdrawals":
        suffix = " токенов"
      else:
        suffix = " ⭐"
      name_display = f"@{name}" if u_username else name
      msg += f"{i}. {name_display} — <code>{val}{suffix}</code>\n"

  await call.message.edit_text(
      msg,
      parse_mode="HTML",
      reply_markup=InlineKeyboardMarkup(
          inline_keyboard=[
              [
                  InlineKeyboardButton(
                      text="« Назад к выбору таблиц", callback_data="back_to_lb"
                  )
              ]
          ]
      ),
  )
  await call.answer()


@dp.callback_query(F.data == "back_to_lb")
async def back_to_leaderboard(call: CallbackQuery):
  lb_kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="👨‍💻 Реферальная", callback_data="top_referrals"
              )
          ],
          [
              InlineKeyboardButton(
                  text="💸 Выводы токенов", callback_data="top_withdrawals"
              )
          ],
          [
              InlineKeyboardButton(
                  text="🤖 Помощь боту", callback_data="top_donates"
              )
          ],
      ]
  )
  await call.message.edit_text(
      "🏆 **Выберете таблицу 👇**", reply_markup=lb_kb, parse_mode="Markdown"
  )
  await call.answer()


@dp.callback_query(F.data.startswith("donate_"))
async def process_donate_callback(call: CallbackQuery, state: FSMContext):
  data_parts = call.data.split("_")
  action = data_parts[1]

  if action == "custom":
    await state.set_state(UserStates.waiting_for_custom_stars)
    await call.message.answer(
        "👨‍💻 Введите желаемое количество звезд для пожертвования:",
        parse_mode="Markdown",
        reply_markup=cancel_kb,
    )
    await call.answer()
    return

  amount = int(action)
  await call.answer()
  prices = [LabeledPrice(label="Помощь боту", amount=amount)]
  await bot.send_invoice(
      chat_id=call.from_user.id,
      title="Помощь проекту",
      description=f"Пожертвование на развитие бота в размере {amount} ⭐",
      payload=f"donate_{amount}_{call.from_user.id}",
      currency="XTR",
      prices=prices,
  )


@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
  await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@dp.message(F.successful_payment)
async def successful_payment_handler(message: types.Message):
  payment = message.successful_payment
  if payment.currency == "XTR":
    amount = payment.total_amount
    await db.add_donation(message.from_user.id, amount)
    await message.answer(
        (
            "❤️ **Огромное спасибо за поддержку!**\n\nУспешно получено"
            f" пожертвование в размере `{amount} ⭐`."
        ),
        parse_mode="Markdown",
        reply_markup=await get_user_keyboard(),
    )


@dp.callback_query(F.data == "user_promo")
async def user_promo(call: CallbackQuery, state: FSMContext):
  await state.set_state(UserStates.waiting_for_promo)
  await call.message.answer(
      "🎟️ **Введите промокод:**\n\nОтправьте код одним сообщением в чат.",
      reply_markup=cancel_kb,
  )
  await call.answer()


@dp.callback_query(F.data == "user_withdraw")
async def user_withdraw_start(call: CallbackQuery, state: FSMContext):
  user_id = call.from_user.id
  user = await db.get_user(user_id)
  
  if not user or user["balance"] < 15:
    await call.answer(
        "❌ Минимальная сумма для вывода составляет 15 К-токенов!",
        show_alert=True,
    )
    return

  is_subscribed = await check_subscription(user_id)
  if not is_subscribed:
    sub_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Подписаться на канал", url=CHANNEL_URL
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Я подписался", callback_data="check_sub_withdraw"
                )
            ],
        ]
    )
    await call.message.answer(
        "⚠️ **Для вывода средств необходимо подписаться на наш канал!**\n\nПожалуйста,"
        " подпишитесь, а затем нажмите кнопку ниже.",
        reply_markup=sub_kb,
        parse_mode="Markdown",
    )
    await call.answer()
    return

  withdraw_kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(text="15 К-токенов", callback_data="wd_amt_15"),
              InlineKeyboardButton(text="25 К-токенов", callback_data="wd_amt_25"),
              InlineKeyboardButton(text="50 К-токенов", callback_data="wd_amt_50"),
          ],
          [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_action")]
      ]
  )

  await call.message.answer(
      f"💸 **Вывод К-токенов**\n\nУ вас на балансе: `{user['balance']} К-токенов`.\nВыберите сумму для вывода:",
      parse_mode="Markdown",
      reply_markup=withdraw_kb
  )
  await call.answer()


@dp.callback_query(F.data.startswith("wd_amt_"))
async def process_fixed_withdrawal(call: CallbackQuery):
  user_id = call.from_user.id
  amount = int(call.data.replace("wd_amt_", ""))
  
  user = await db.get_user(user_id)
  
  if not user or user["balance"] < amount:
    await call.answer(f"❌ У вас недостаточно средств для вывода {amount} К-токенов!", show_alert=True)
    return

  await db.add_withdrawal(user_id, amount)

  await call.message.edit_text(
      f"✅ **Заявка на вывод отправлена!**\n\nСумма: `{amount} К-токенов`.",
      parse_mode="Markdown"
  )
  await call.message.answer(
      "Главное меню:", 
      reply_markup=await get_user_keyboard()
  )

  admin_kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="Перейти в заявки админки", callback_data="admin_withdrawals")]
      ]
  )
  raw_username = call.from_user.username
  safe_username = html.escape(str(raw_username)) if raw_username else "Без юзернейма"
  username_info = f"@{safe_username}" if raw_username else "Без юзернейма"
  
  await bot.send_message(
      ADMIN_ID,
      f"💸 <b>Новая заявка на вывод!</b>\n\n👤 Юзер: {username_info}\n🆔 Айди: <code>{user_id}</code>\n💰 Сумма: <b>{amount} К-токенов</b>",
      reply_markup=admin_kb,
      parse_mode="HTML"
  )
  await call.answer()


# --- АДМИН ПАНЕЛЬ ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(call: CallbackQuery):
  if not await is_admin_or_moderator(call.from_user.id):
    await call.answer("⛔ Доступ запрещен!", show_alert=True)
    return

  keyboard_rows = [
      [
          InlineKeyboardButton(
              text="Добавить задание", callback_data="admin_add_task"
          )
      ],
      [
          InlineKeyboardButton(
              text="💎 Выдать К-токены", callback_data="admin_give_tokens"
          )
      ],
      [
          InlineKeyboardButton(
              text="💸 Заявки на вывод", callback_data="admin_withdrawals"
          )
      ],
      [
          InlineKeyboardButton(
              text="Проверить задания", callback_data="admin_check"
          )
      ],
      [
          InlineKeyboardButton(
              text="💡 Предложенные задания",
              callback_data="admin_suggested_tasks",
          )
      ],
      [
          InlineKeyboardButton(
              text="Создать промокод", callback_data="admin_promo"
          )
      ],
      [
          InlineKeyboardButton(
              text="Редактор кнопок", callback_data="admin_edit_buttons"
          )
      ],
      [
          InlineKeyboardButton(
              text="📢 Сделать рассылку", callback_data="admin_broadcast"
          )
      ],
  ]

  if call.from_user.id == ADMIN_ID:
    keyboard_rows.insert(
        3,
        [
            InlineKeyboardButton(
                text="🛡️ Модераторы", callback_data="admin_moderators"
            )
        ],
    )

  keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
  await call.message.answer(
      "⚙️ **Панель администратора / модератора**",
      reply_markup=keyboard,
      parse_mode="Markdown",
  )
  await call.answer()


@dp.callback_query(F.data == "admin_add_task")
async def admin_add_task(call: CallbackQuery):
  if not await is_admin_or_moderator(call.from_user.id):
    return
  cat_kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="📢 Подписки", callback_data="admin_cat_sub")],
          [InlineKeyboardButton(text="👀 Просмотры", callback_data="admin_cat_views")],
          [
              InlineKeyboardButton(
                  text="💬 Активность", callback_data="admin_cat_activity"
              )
          ],
          [InlineKeyboardButton(text="⭐ Другое", callback_data="admin_cat_other")],
          [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_action")],
      ]
  )
  await call.message.answer(
      "✏️ **Создание задания (Шаг 1/5)**\n\nВыберите категорию:",
      reply_markup=cat_kb,
      parse_mode="Markdown",
  )
  await call.answer()


@dp.callback_query(F.data == "admin_promo")
async def admin_promo_start(call: CallbackQuery, state: FSMContext):
  if not await is_admin_or_moderator(call.from_user.id):
    return
  await state.set_state(AdminStates.promo_code)
  await call.message.answer(
      "🎁 **Создание промокода (Шаг 1/3)**\n\nВведите код:",
      parse_mode="Markdown",
      reply_markup=cancel_kb,
  )
  await call.answer()


@dp.callback_query(F.data == "admin_check")
async def admin_check(call: CallbackQuery):
  if not await is_admin_or_moderator(call.from_user.id):
    return
  subs = await db.get_pending_submissions()

  if not subs:
    await call.message.answer("🙅‍♂️ Нет заданий на проверку.")
    await call.answer()
    return

  for sub in subs:
    if int(time.time()) - sub["submitted_at"] > 7200:
      await db.resolve_submission(
          sub["id"],
          sub["user_id"],
          sub["task_id"],
          sub["reward"],
          sub["title"],
          approve=False,
      )
    else:
      kb = InlineKeyboardMarkup(
          inline_keyboard=[
              [
                  InlineKeyboardButton(
                      text="Принять",
                      callback_data=(
                          f"aprv_{sub['id']}_{sub['user_id']}_{sub['task_id']}_{sub['reward']}"
                      ),
                  ),
                  InlineKeyboardButton(
                      text="Отклонить", callback_data=f"rej_{sub['id']}"
                  ),
              ]
          ]
      )
      
      sub_title = sub["title"] if "title" in sub.keys() and sub["title"] else ""
      sub_username = sub["username"] if "username" in sub.keys() and sub["username"] else ""
      safe_title = html.escape(str(sub_title))
      safe_username = html.escape(str(sub_username))
      
      await call.message.answer_photo(
          photo=sub["photo_file_id"],
          caption=(
              f"📌 Задание: {safe_title} (+{sub['reward']} К-токенов)\n👤 От:"
              f" @{safe_username}"
          ),
          reply_markup=kb,
          parse_mode="HTML",
      )
  await call.answer()


@dp.callback_query(F.data.startswith("aprv_"))
async def approve_task(call: CallbackQuery):
  if not await is_admin_or_moderator(call.from_user.id):
    return
  _, sub_id, user_id, task_id, reward = call.data.split("_")
  await db.resolve_submission(
      int(sub_id),
      int(user_id),
      int(task_id),
      int(reward),
      "Задание",
      approve=True,
  )
  await call.message.edit_caption(
      caption=call.message.caption + "\n\n✅ **Принято!**", parse_mode="Markdown"
  )
  await call.answer("Успешно!")


@dp.callback_query(F.data.startswith("rej_"))
async def reject_task(call: CallbackQuery):
  if not await is_admin_or_moderator(call.from_user.id):
    return
  sub_id = int(call.data.split("_")[1])
  await db.resolve_submission(sub_id, 0, 0, 0, "", approve=False)
  await call.message.edit_caption(
      caption=call.message.caption + "\n\n❌ **Отклонено.**", parse_mode="Markdown"
  )
  await call.answer("Отклонено.")


@dp.callback_query(F.data == "admin_edit_buttons")
async def edit_buttons(call: CallbackQuery):
  if call.from_user.id != ADMIN_ID:
    return
  current = await db.get_buttons_text()
  menu = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text=f"Профиль: {current['profile_text']}",
                  callback_data="edit_profile_text",
              )
          ],
          [
              InlineKeyboardButton(
                  text=f"Задания: {current['tasks_text']}",
                  callback_data="edit_tasks_text",
              )
          ],
          [
              InlineKeyboardButton(
                  text=f"Таблица лидеров: {current['leaderboard_text']}",
                  callback_data="edit_leaderboard_text",
              )
          ],
          [
              InlineKeyboardButton(
                  text=f"Помощь: {current['donate_text']}",
                  callback_data="edit_donate_text",
              )
          ],
          [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_action")],
      ]
  )
  await call.message.answer(
      "⚙️ **Редактор кнопок меню**\n\nНажмите на нужную кнопку и отправьте ей"
      " новый текст или стикер:",
      reply_markup=menu,
      parse_mode="Markdown",
  )
  await call.answer()


@dp.callback_query(F.data.startswith("edit_"))
async def edit_button_start(call: CallbackQuery, state: FSMContext):
  if call.from_user.id != ADMIN_ID:
    return
  button_name = call.data.replace("edit_", "").replace("_text", "")
  await state.set_state(AdminStates.edit_button_state)
  await state.update_data(button_name=button_name)
  await call.message.answer(
      "✏️ **Введите новый текст для этой кнопки или отправьте"
      " Telegram-стикер:**",
      parse_mode="Markdown",
      reply_markup=cancel_kb,
  )
  await call.answer()


@dp.callback_query(F.data.startswith("take_"))
async def take_task(call: CallbackQuery, state: FSMContext):
  task_id = int(call.data.split("_")[1])
  await state.set_state(UserStates.waiting_for_task_photo)
  await state.update_data(task_id=task_id)
  await call.message.answer(
      "📸 **Отправьте скриншот выполнения задания.**\n\nОн автоматически уйдет"
      " на проверку.",
      parse_mode="Markdown",
      reply_markup=cancel_kb,
  )
  await call.answer()



@app.get("/")
async def root():
    return {"status": "ok", "service": "kvizer-bot"}

@app.get("/health")
async def health():
    return {"ok": True}

async def run_http_server():
    config = Config(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
    server = Server(config)
    await server.serve()


# --- ЗАПУСК ---
async def main():



  try:
    http_task = asyncio.create_task(run_http_server())
#    await db.create_pool()
    print("Бот успешно запущен!")
    await dp.start_polling(bot)
    http_task.cancel
  except TelegramUnauthorizedError:
    print("\n❌ ОШИБКА: Токен бота неверный или устарел!\n")


if __name__ == "__main__":
  try:
    asyncio.run(main())
  except KeyboardInterrupt:
    print("\nБот остановлен.")