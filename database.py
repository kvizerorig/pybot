import aiosqlite


class Database:

  def __init__(self, db_file="bot_database.db"):
    self.db_file = db_file

  async def create_pool(self):
    async with aiosqlite.connect(self.db_file) as db:
      # Таблица пользователей
      await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    balance INTEGER DEFAULT 0,
                    completed_tasks INTEGER DEFAULT 0,
                    invited_count INTEGER DEFAULT 0,
                    referrer_id INTEGER,
                    language TEXT
                )
            """)

      # Таблица заданий
      await db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    description TEXT,
                    reward INTEGER,
                    category TEXT,
                    max_limit INTEGER,
                    current_completions INTEGER DEFAULT 0
                )
            """)

      # Таблица выполненных заданий (сабмитов)
      await db.execute("""
                CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    task_id INTEGER,
                    photo_file_id TEXT,
                    submitted_at INTEGER
                )
            """)

      # Таблица предложенных заданий пользователями
      await db.execute("""
                CREATE TABLE IF NOT EXISTS suggested_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    title TEXT,
                    description TEXT,
                    category TEXT,
                    status TEXT DEFAULT 'pending'
                )
            """)

      # Таблица заявок на вывод средств
      await db.execute("""
                CREATE TABLE IF NOT EXISTS withdrawals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount INTEGER,
                    status TEXT DEFAULT 'pending'
                )
            """)

      # Таблица промокодов
      await db.execute("""
                CREATE TABLE IF NOT EXISTS promos (
                    code TEXT PRIMARY KEY,
                    reward INTEGER,
                    limit_uses INTEGER,
                    used_count INTEGER DEFAULT 0
                )
            """)

      # Таблица использованных промокодов пользователями
      await db.execute("""
                CREATE TABLE IF NOT EXISTS used_promos (
                    user_id INTEGER,
                    code TEXT,
                    PRIMARY KEY (user_id, code)
                )
            """)

      # Таблица модераторов
      await db.execute("""
                CREATE TABLE IF NOT EXISTS moderators (
                    user_id INTEGER PRIMARY KEY
                )
            """)

      # Таблица текстов кнопок меню (динамический редактор)
      await db.execute("""
                CREATE TABLE IF NOT EXISTS menu_buttons (
                    button_key TEXT PRIMARY KEY,
                    button_text TEXT
                )
            """)

      # Таблица донатов (помощи боту через Telegram Stars)
      await db.execute("""
                CREATE TABLE IF NOT EXISTS donations (
                    user_id INTEGER,
                    amount INTEGER,
                    timestamp INTEGER
                )
            """)

      # Таблица истории еженедельных заданий
      await db.execute("""
                CREATE TABLE IF NOT EXISTS weekly_task_history (
                    user_id INTEGER,
                    task_id INTEGER,
                    week_number INTEGER,
                    PRIMARY KEY (user_id, task_id, week_number)
                )
            """)

      await db.commit()

  # --- ПОЛЬЗОВАТЕЛИ ---
  async def add_user(
      self, user_id, username, first_name, referrer_id=None
  ) -> bool:
    async with aiosqlite.connect(self.db_file) as db:
      async with db.execute(
          "SELECT user_id FROM users WHERE user_id = ?", (user_id,)
      ) as cursor:
        user = await cursor.fetchone()
        if user:
          return False

      await db.execute(
          """
                INSERT INTO users (user_id, username, first_name, referrer_id)
                VALUES (?, ?, ?, ?)
            """,
          (user_id, username, first_name, referrer_id),
      )
      await db.commit()
      return True

  async def get_user(self, user_id):
    async with aiosqlite.connect(self.db_file) as db:
      db.row_factory = aiosqlite.Row
      async with db.execute(
          "SELECT * FROM users WHERE user_id = ?", (user_id,)
      ) as cursor:
        return await cursor.fetchone()

  async def set_user_language(self, user_id, lang):
    async with aiosqlite.connect(self.db_file) as db:
      await db.execute(
          "UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id)
      )
      await db.commit()

  async def update_balance(self, user_id, amount):
    async with aiosqlite.connect(self.db_file) as db:
      await db.execute(
          "UPDATE users SET balance = balance + ? WHERE user_id = ?",
          (amount, user_id),
      )
      await db.commit()

  async def increment_invited_count(self, user_id):
    async with aiosqlite.connect(self.db_file) as db:
      await db.execute(
          "UPDATE users SET invited_count = invited_count + 1 WHERE user_id = ?",
          (user_id,),
      )
      await db.commit()

  async def get_user_referral_count(self, user_id) -> int:
    async with aiosqlite.connect(self.db_file) as db:
      async with db.execute(
          "SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,)
      ) as cursor:
        res = await cursor.fetchone()
        return res[0] if res else 0

  async def get_all_users(self):
    async with aiosqlite.connect(self.db_file) as db:
      db.row_factory = aiosqlite.Row
      async with db.execute("SELECT user_id FROM users") as cursor:
        return await cursor.fetchall()

  async def get_total_stats(self):
    async with aiosqlite.connect(self.db_file) as db:
      async with db.execute("SELECT COUNT(*) FROM users") as cursor:
        total_users = (await cursor.fetchone())[0]
      async with db.execute("SELECT SUM(balance) FROM users") as cursor:
        total_given = (await cursor.fetchone())[0] or 0
      return total_users, total_given

  # --- ЗАДАНИЯ ---
  async def add_task(self, title, description, reward, category, max_limit):
    async with aiosqlite.connect(self.db_file) as db:
      await db.execute(
          """
                INSERT INTO tasks (title, description, reward, category, max_limit)
                VALUES (?, ?, ?, ?, ?)
            """,
          (title, description, reward, category, max_limit),
      )
      await db.commit()

  async def get_task_by_id(self, task_id):
    async with aiosqlite.connect(self.db_file) as db:
      db.row_factory = aiosqlite.Row
      async with db.execute(
          "SELECT * FROM tasks WHERE id = ?", (task_id,)
      ) as cursor:
        return await cursor.fetchone()

  async def get_weekly_available_tasks(self, user_id, limit=3):
    import time

    week_number = int(time.strftime("%Y%W"))
    async with aiosqlite.connect(self.db_file) as db:
      db.row_factory = aiosqlite.Row
      async with db.execute(
          """
                SELECT * FROM tasks 
                WHERE current_completions < max_limit
                AND id NOT IN (
                    SELECT task_id FROM weekly_task_history 
                    WHERE user_id = ? AND week_number = ?
                )
                LIMIT ?
            """,
          (user_id, week_number, limit),
      ) as cursor:
        return await cursor.fetchall()

  # --- ПРОВЕРКА ЗАДАНИЙ ---
  async def add_submission(self, user_id, task_id, photo_file_id):
    import time

    async with aiosqlite.connect(self.db_file) as db:
      await db.execute(
          """
                INSERT INTO submissions (user_id, task_id, photo_file_id, submitted_at)
                VALUES (?, ?, ?, ?)
            """,
          (user_id, task_id, photo_file_id, int(time.time())),
      )
      await db.commit()

  async def get_pending_submissions(self):
    async with aiosqlite.connect(self.db_file) as db:
      db.row_factory = aiosqlite.Row
      async with db.execute("""
                SELECT s.*, t.title, t.reward, u.username 
                FROM submissions s
                JOIN tasks t ON s.task_id = t.id
                JOIN users u ON s.user_id = u.user_id
            """) as cursor:
        return await cursor.fetchall()

  async def resolve_submission(
      self, sub_id, user_id, task_id, reward, title, approve
  ):
    import time

    async with aiosqlite.connect(self.db_file) as db:
      await db.execute("DELETE FROM submissions WHERE id = ?", (sub_id,))
      if approve:
        week_number = int(time.strftime("%Y%W"))
        await db.execute(
            """
                    INSERT OR IGNORE INTO weekly_task_history (user_id, task_id, week_number)
                    VALUES (?, ?, ?)
                """,
            (user_id, task_id, week_number),
        )
        await db.execute(
            """
                    UPDATE users 
                    SET balance = balance + ?, completed_tasks = completed_tasks + 1 
                    WHERE user_id = ?
                """,
            (reward, user_id),
        )
        await db.execute(
            """
                    UPDATE tasks 
                    SET current_completions = current_completions + 1 
                    WHERE id = ?
                """,
            (task_id,),
        )
      await db.commit()

  # --- ПРЕДЛОЖЕННЫЕ ЗАДАНИЯ ---
  async def add_suggested_task(
      self, user_id, username, title, description, category
  ):
    async with aiosqlite.connect(self.db_file) as db:
      await db.execute(
          """
                INSERT INTO suggested_tasks (user_id, username, title, description, category)
                VALUES (?, ?, ?, ?, ?)
            """,
          (user_id, username, title, description, category),
      )
      await db.commit()

  async def get_pending_suggested_tasks(self):
    async with aiosqlite.connect(self.db_file) as db:
      db.row_factory = aiosqlite.Row
      async with db.execute(
          "SELECT * FROM suggested_tasks WHERE status = 'pending'"
      ) as cursor:
        return await cursor.fetchall()

  async def get_suggested_task_by_id(self, sugg_id):
    async with aiosqlite.connect(self.db_file) as db:
      db.row_factory = aiosqlite.Row
      async with db.execute(
          "SELECT * FROM suggested_tasks WHERE id = ?", (sugg_id,)
      ) as cursor:
        return await cursor.fetchone()

  async def resolve_suggested_task(self, sugg_id, approve):
    status = "approved" if approve else "rejected"
    async with aiosqlite.connect(self.db_file) as db:
      await db.execute(
          "UPDATE suggested_tasks SET status = ? WHERE id = ?",
          (status, sugg_id),
      )
      await db.commit()

  # --- ВЫВОДЫ СРЕДСТВ ---
  async def add_withdrawal(self, user_id, amount):
    async with aiosqlite.connect(self.db_file) as db:
      await db.execute(
          "UPDATE users SET balance = balance - ? WHERE user_id = ?",
          (amount, user_id),
      )
      await db.execute(
          "INSERT INTO withdrawals (user_id, amount) VALUES (?, ?)",
          (user_id, amount),
      )
      await db.commit()

  async def get_pending_withdrawals(self):
    async with aiosqlite.connect(self.db_file) as db:
      db.row_factory = aiosqlite.Row
      async with db.execute("""
                SELECT w.*, u.username, u.first_name 
                FROM withdrawals w
                JOIN users u ON w.user_id = u.user_id
                WHERE w.status = 'pending'
            """) as cursor:
        return await cursor.fetchall()

  async def resolve_withdrawal(self, wd_id, approve):
    async with aiosqlite.connect(self.db_file) as db:
      db.row_factory = aiosqlite.Row
      async with db.execute(
          "SELECT * FROM withdrawals WHERE id = ?", (wd_id,)
      ) as cursor:
        wd = await cursor.fetchone()

      if not wd:
        return None

      if approve:
        await db.execute(
            "UPDATE withdrawals SET status = 'approved' WHERE id = ?",
            (wd_id,),
        )
      else:
        await db.execute(
            "UPDATE withdrawals SET status = 'rejected' WHERE id = ?",
            (wd_id,),
        )
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (wd["amount"], wd["user_id"]),
        )
      await db.commit()
      return wd

  # --- ПРОМОКОДЫ ---
  async def add_promo(self, code, reward, limit_uses):
    async with aiosqlite.connect(self.db_file) as db:
      await db.execute(
          """
                INSERT INTO promos (code, reward, limit_uses)
                VALUES (?, ?, ?)
            """,
          (code, reward, limit_uses),
      )
      await db.commit()

  async def apply_promo(self, code):
    async with aiosqlite.connect(self.db_file) as db:
      db.row_factory = aiosqlite.Row
      async with db.execute(
          "SELECT * FROM promos WHERE code = ?", (code,)
      ) as cursor:
        promo = await cursor.fetchone()

      if not promo or promo["used_count"] >= promo["limit_uses"]:
        return None

      await db.execute(
          "UPDATE promos SET used_count = used_count + 1 WHERE code = ?",
          (code,),
      )
      await db.commit()
      return promo["reward"]

  # --- МОДЕРАТОРЫ ---
  async def add_moderator(self, user_id):
    async with aiosqlite.connect(self.db_file) as db:
      await db.execute(
          "INSERT OR IGNORE INTO moderators (user_id) VALUES (?)", (user_id,)
      )
      await db.commit()

  async def is_moderator(self, user_id) -> bool:
    async with aiosqlite.connect(self.db_file) as db:
      async with db.execute(
          "SELECT user_id FROM moderators WHERE user_id = ?", (user_id,)
      ) as cursor:
        res = await cursor.fetchone()
        return res is not None

  async def get_all_moderators(self):
    async with aiosqlite.connect(self.db_file) as db:
      db.row_factory = aiosqlite.Row
      async with db.execute("SELECT user_id FROM moderators") as cursor:
        return await cursor.fetchall()

  # --- КНОПКИ МЕНЮ ---
  async def get_buttons_text(self):
    defaults = {
        "profile_text": "👤 Мой профиль",
        "tasks_text": "🔍 Поиск заданий",
        "leaderboard_text": "🏆 Таблица лидеров",
        "donate_text": "💎 Помощь Боту",
        "promo_text": "Ввести промокод",
        "admin_panel_text": "Админ панель",
    }
    async with aiosqlite.connect(self.db_file) as db:
      async with db.execute(
          "SELECT button_key, button_text FROM menu_buttons"
      ) as cursor:
        rows = await cursor.fetchall()
        for r in rows:
          if r[0] in defaults:
            defaults[r[0]] = r[1]
    return defaults

  async def update_button_text(self, button_name, new_text):
    key = (
        f"{button_name}_text"
        if not button_name.endswith("_text")
        else button_name
    )
    async with aiosqlite.connect(self.db_file) as db:
      await db.execute(
          """
                INSERT INTO menu_buttons (button_key, button_text) VALUES (?, ?)
                ON CONFLICT(button_key) DO UPDATE SET button_text = ?
            """,
          (key, new_text, new_text),
      )
      await db.commit()

  # --- ДОНАТЫ ---
  async def add_donation(self, user_id, amount):
    import time

    async with aiosqlite.connect(self.db_file) as db:
      await db.execute(
          "INSERT INTO donations (user_id, amount, timestamp) VALUES (?, ?, ?)",
          (user_id, amount, int(time.time())),
      )
      await db.commit()

  # --- ТАБЛИЦА ЛИДЕРОВ ---
  async def get_top_users(self, category):
    async with aiosqlite.connect(self.db_file) as db:
      db.row_factory = aiosqlite.Row
      if category == "referrals":
        async with db.execute("""
                    SELECT u.username, u.first_name, COUNT(r.user_id) as val
                    FROM users u
                    LEFT JOIN users r ON u.user_id = r.referrer_id
                    GROUP BY u.user_id
                    ORDER BY val DESC
                    LIMIT 10
                """) as cursor:
          return await cursor.fetchall()
      elif category == "withdrawals":
        async with db.execute("""
                    SELECT u.username, u.first_name, SUM(w.amount) as val
                    FROM users u
                    JOIN withdrawals w ON u.user_id = w.user_id
                    WHERE w.status = 'approved'
                    GROUP BY u.user_id
                    ORDER BY val DESC
                    LIMIT 10
                """) as cursor:
          return await cursor.fetchall()
      elif category == "donates":
        async with db.execute("""
                    SELECT u.username, u.first_name, SUM(d.amount) as val
                    FROM users u
                    JOIN donations d ON u.user_id = d.user_id
                    GROUP BY u.user_id
                    ORDER BY val DESC
                    LIMIT 10
                """) as cursor:
          return await cursor.fetchall()
      return []