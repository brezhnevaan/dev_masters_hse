import re
import asyncio
import json
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from config import BOT_TOKEN
from api_requests import get_city_temperature, get_product_nutrition, get_exercise_data
from utils import get_water_norm, get_calories_norm, translate_to_english, get_progress_visualisation
from pathlib import Path


USER_DATA_FILE = str(Path("/app") / "user_data.json")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

class User:
    def __init__(self, user_id: int):
        self.user_id: int = user_id
        self.data: UserData = UserData()
        self.daily: DailyData = DailyData()

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "data": self.data.to_dict(),
            "daily": self.daily.to_dict()
        }

    @staticmethod
    def from_dict(data):
        user = User(user_id=data["user_id"])
        user.data = UserData.from_dict(data["data"])
        user.daily = DailyData.from_dict(data["daily"])
        return user


class UserData:
    def __init__(self, weight=None, height=None, age=None, activity=None, city=None):
        self.weight = weight
        self.height = height
        self.age = age
        self.activity = activity
        self.city = city

    def to_dict(self):
        return self.__dict__

    @staticmethod
    def from_dict(data):
        return UserData(**data)


class DailyData:
    def __init__(self, water_goal=None, calorie_goal=None, logged_water=0, logged_calories=0, burned_calories=0, workout_minutes=0, date=None):
        self.water_goal = water_goal
        self.calorie_goal = calorie_goal
        self.logged_water = logged_water
        self.logged_calories = logged_calories
        self.burned_calories = burned_calories
        self.workout_minutes = workout_minutes
        self.date = date

    def to_dict(self):
        return self.__dict__

    @staticmethod
    def from_dict(data):
        return DailyData(**data)


class UserProfile(StatesGroup):
    confirm_update = State()
    weight = State()
    height = State()
    age = State()
    activity = State()
    city = State()


class UserFood(StatesGroup):
    product_name = State()
    calories_100g = State()
    logged_amount_g = State()
    logged_calories = State()


if not Path(USER_DATA_FILE).exists():
    with open(USER_DATA_FILE, "w") as f:
        json.dump({}, f)


with open(USER_DATA_FILE, "r") as f:
    users = {int(k): User.from_dict(v) for k, v in json.load(f).items()}


def save_users():
    with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({k: v.to_dict() for k, v in users.items()}, f, indent=4, ensure_ascii=False)

class LoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data: dict):
        print(f"Получено сообщение: {event.text}")
        return await handler(event, data)

dp.message.middleware(LoggingMiddleware())

@router.message(Command("help"))
async def cmd_help(message: Message):
    print("Help command received")
    await message.reply(
        "🛸 Доступные команды:"
        "\n/start — начать работу с ботом"
        "\n/set_profile — настроить профиль"
        "\n/log_water [количество] — записать выпитую воду"
        "\n/log_food [продукт] — записать съеденные калории"
        "\n/log_workout [тренировка] [длительность в часах/минутах]— зарегистрировать тренировку"
        "\n/check_progress — проверить дневной прогресс"
        "\n/help — получить список команд"
    )


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.reply("Привет! Это бот отслеживания активности и рациона питания 👋"
                        "\nЧтобы начать работу, нужно заполнить профиль. Используйте команду /set_profile.")


@router.message(Command("set_profile"))
async def set_profile(message: Message, state: FSMContext):
    user_id = message.from_user.id
    current_date = message.date.date()
    if user_id in users:
        user = users[user_id]

        # Если пользователь пришел в тот же день — подгружаем и обновляем данные того же дня
        # Если в новый день — перезаписываем
        if user.daily.date == current_date.isoformat():
            water_goal = user.daily.water_goal
            calorie_goal = user.daily.calorie_goal
        else:
            temperature = get_city_temperature(translate_to_english(user.data.city))
            if temperature is None:
                temperature = 10.0
            user.daily.water_goal = get_water_norm(user.data.weight, user.data.activity, temperature)
            user.daily.calorie_goal = get_calories_norm(user.data.weight, user.data.height, user.data.age, user.data.activity)
            user.daily.logged_water = 0
            user.daily.logged_calories = 0
            user.daily.burned_calories = 0
            user.daily.workout_minutes = 0
            user.daily.date = current_date.isoformat()

            save_users()

            water_goal = user.daily.water_goal
            calorie_goal = user.daily.calorie_goal

        await message.reply(
            f"Ваш профиль уже существует 🙌\n"
            f"\nВес: {user.data.weight} кг"
            f"\nРост: {user.data.height} см"
            f"\nВозраст: {user.data.age} лет"
            f"\nАктивность: {user.data.activity} минут"
            f"\nГород: {user.data.city}\n"
            f"\nВаша дневная норма воды: {int(water_goal)} мл"
            f"\nВаша дневная норма калорий: {int(calorie_goal)} ккал"
        )

        kb = [
            [KeyboardButton(text="Да"),
             KeyboardButton(text="Нет")]
        ]
        keyboard = ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True
        )
        await message.answer("Хотите обновить данные?", reply_markup=keyboard)
        await state.set_state(UserProfile.confirm_update)
    else:
        users[user_id] = User(user_id)
        await message.reply("Введите ваш вес в кг:")
        await state.set_state(UserProfile.weight)


@router.message(UserProfile.confirm_update)
async def confirm_update(message: Message, state: FSMContext):
    if message.text.lower() == "да":
        await message.reply("Введите ваш вес в кг:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(UserProfile.weight)
    elif message.text.lower() == "нет":
        await message.reply("Профиль не изменён 👌", reply_markup=ReplyKeyboardRemove())
        await state.clear()
    else:
        await message.reply("Пожалуйста, выберите 'Да' или 'Нет'.")


@router.message(UserProfile.weight)
async def update_weight(message: Message, state: FSMContext):
    try:
        weight = int(message.text)
        if weight <= 0:
            await message.reply("Вес должен быть больше 0.")
            return
        await state.update_data(weight=weight)
        await message.reply("Введите ваш рост в см:")
        await state.set_state(UserProfile.height)
    except ValueError:
        await message.reply("Пожалуйста, используйте цифры для ввода веса (целое число).")
        return


@router.message(UserProfile.height)
async def update_height(message: Message, state: FSMContext):
    try:
        height = int(message.text)
        if height <= 0:
            await message.reply("Рост должен быть больше 0.")
            return
        await state.update_data(height=height)
        await message.reply("Введите ваш возраст:")
        await state.set_state(UserProfile.age)
    except ValueError:
        await message.reply("Пожалуйста, используйте цифры для ввода роста (целое число).")
        return


@router.message(UserProfile.age)
async def update_age(message: Message, state: FSMContext):
    try:
        age = int(message.text)
        if age <= 0:
            await message.reply("Возраст должен быть больше 0.")
            return
        await state.update_data(age=age)
        await message.reply("Сколько минут активности у вас в день?")
        await state.set_state(UserProfile.activity)
    except ValueError:
        await message.reply("Пожалуйста, используйте цифры для ввода возраста (целое число).")
        return


@router.message(UserProfile.activity)
async def update_activity(message: Message, state: FSMContext):
    try:
        activity = int(message.text)
        if activity < 0:
            await message.reply("Активность не должна быть отрицательной.")
            return
        await state.update_data(activity=activity)
        await message.reply("В каком городе вы находитесь?")
        await state.set_state(UserProfile.city)
    except ValueError:
        await message.reply("Пожалуйста, используйте цифры для ввода активности (целое число).")
        return


@router.message(UserProfile.city)
async def update_city(message: Message, state: FSMContext):
    city = message.text.strip()
    if not city or city.isspace() or not re.match(r"^[a-zA-Zа-яА-Я0-9\s-]+$", city):
        await message.reply(
            "Название города не должно содержать специальных символов или быть пустым."
            "\nПопробуйте еще раз."
        )
        return

    await state.update_data(city=city)

    user_id = message.from_user.id
    user = users[user_id]

    user_data = await state.get_data()
    user.data.weight = user_data["weight"]
    user.data.height = user_data["height"]
    user.data.age = user_data["age"]
    user.data.activity = user_data["activity"]
    user.data.city = user_data["city"]
    save_users()

    temperature = get_city_temperature(translate_to_english(user.data.city))
    if temperature is None:
        await message.reply(
            "Данные о текущей температуре в городе отсутствуют."
            "\nУстановлена температура по умолчанию: 10°C."
        )
        temperature = 10.0

    user.daily.water_goal = get_water_norm(user.data.weight, user.data.activity, temperature)
    user.daily.calorie_goal = get_calories_norm(user.data.weight, user.data.height, user.data.age, user.data.activity)
    save_users()

    await state.clear()
    await message.reply(
        f"Профиль успешно заполнен 🙌\n"
        f"\nВес: {user.data.weight} кг"
        f"\nРост: {user.data.height} см"
        f"\nВозраст: {user.data.age} лет"
        f"\nАктивность: {user.data.activity} минут"
        f"\nГород: {user.data.city}\n"
        f"\nВаша дневная норма воды: {int(user.daily.water_goal)} мл"
        f"\nВаша дневная норма калорий: {int(user.daily.calorie_goal)} ккал"
    )


@router.message(Command("log_water"))
async def log_water(message: Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.reply("Ваш профиль не найден 🧐"
                            "\nИспользуйте команду /set_profile, чтобы создать профиль.")
        return
    try:
        command_structure = message.text.split()
        if len(command_structure) != 2:
            await message.reply("Неверный ввод. Напишите количество воды после команды."
                                "\nНапример: /log_water 300")
            return
        try:
            logged_water = int(command_structure[1])
            if logged_water <= 0:
                await message.reply("Объем выпитой воды должен быть больше 0.")
                return
            user = users[user_id]
            user.daily.logged_water += logged_water
            save_users()

            left_to_drink = max(user.daily.water_goal - user.daily.logged_water, 0)

            if left_to_drink == 0:
                water_status = "\nУра! Норма воды выполнена 🎉"
            else:
                water_status = f"\n💧 До выполнения нормы: {int(left_to_drink)} мл."
            await message.reply(
                f"✅ Добавлено: {int(logged_water)} мл воды."
                f"\n🥤 Всего выпито: {int(user.daily.logged_water)} мл."
                f"{water_status}"
            )

        except ValueError:
            await message.reply("Пожалуйста, используйте цифры для ввода выпитой воды (целое число).")
            return
    except ValueError as e:
        await message.reply(f"Что-то пошло не так 😔 Попробуйте еще раз.")


@router.message(Command("log_food"))
async def log_food(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in users:
        await message.reply("Ваш профиль не найден 🧐"
                            "\nИспользуйте команду /set_profile, чтобы создать профиль.")
        return

    try:
        command_structure = message.text.split()

        if len(command_structure) < 2:
            await message.reply("Пожалуйста, укажите название продукта после команды."
                                "\nНапример: /log_food банан")
            return
        if len(command_structure) > 2:
            await message.reply("Пожалуйста, указывайте продукты по одному."
                                "\nНапример: /log_food суп")
            return

        product = command_structure[1]
        if not re.match(r"^[a-zA-Zа-яА-ЯёЁ]+$", product):
            await message.reply("Название продукта должно содержать только буквы. Попробуйте снова.")
            return

        product_data = get_product_nutrition(translate_to_english(product))
        if not product_data:
            await message.reply(f"Информация о продукте '{product}' (en: {translate_to_english(product)}) не найдена."
                                "\nПопробуйте другой варинт названия.")
            return
        try:
            calories_100g = round(product_data['foods'][0]['nf_calories'] \
                                  / product_data['foods'][0]['serving_weight_grams'] * 100, 2)
            await message.reply(
                f"{product.capitalize()} — {calories_100g} ккал на 100 г."
                f"\nСколько грамм вы съели?"
            )
            await state.set_state(UserFood.logged_amount_g)
            await state.update_data(product_name=product, calories_100g=calories_100g)
        except (KeyError, IndexError, ValueError):
            await message.reply(f"Что-то пошло не так 😔 Попробуйте еще раз.")
            return
    except ValueError as e:
        await message.reply(f"Что-то пошло не так 😔 Попробуйте еще раз.")


@router.message(UserFood.logged_amount_g)
async def log_food_amount(message: Message, state: FSMContext):
    user_id = message.from_user.id

    try:
        food_amount_g = int(message.text)
        if food_amount_g <= 0:
            await message.reply("Вес продукта должен быть больше 0 (целое число).")
            return

        user = users[user_id]
        data = await state.get_data()
        calories_100g = data["calories_100g"]
        product_name = data["product_name"]
        logged_calories = round((calories_100g / 100) * food_amount_g, 2)
        user.daily.logged_calories += logged_calories
        save_users()

        calories_left = round(user.daily.calorie_goal - user.daily.logged_calories)
        activity_minutes = user.data.activity
        burned_calories = user.daily.burned_calories
        activity_calories = (activity_minutes // 30) * 200
        extra_burned = burned_calories - activity_calories

        # Норму калорий не обновляем при доп. физ. активности, в отличие от воды (не всегда нужно есть больше)
        # Но если сожженные ккал на экстра-тренировках перекрывают превышение по съеденным ккал — не выводим алерт
        if calories_left >= -10 and calories_left <= 10:
            calories_status = "\nУра! Норма по калориям выполнена 🎉"
        elif calories_left > 10:
            calories_status = f"\n🍎 До выполнения нормы: {int(calories_left)} ккал."
        elif calories_left < -10 and extra_burned > abs(calories_left):
            calories_status = "\nУра! Норма по калориям выполнена 🎉"
        else:
            calories_status = f"\n❗ Норма по калориям превышена на {int(calories_left * -1)} ккал."
        await message.reply(
            f"✅ Добавлено: {int(logged_calories)} ккал для продукта '{product_name}' ({int(food_amount_g)} гр)."
            f"\n🍽️ Прогресс по калориям: {int(user.daily.logged_calories)} ккал."
            f"{calories_status}"
        )
        await state.clear()

    except ValueError:
        await message.reply("Пожалуйста, используйте цифры для ввода веса продукта (целое число).")


@router.message(Command("log_workout"))
async def log_workout(message: Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.reply("Ваш профиль не найден 🧐"
                            "\nИспользуйте команду /set_profile, чтобы создать профиль.")
        return

    try:
        command_structure = message.text.split()
        if len(command_structure) < 3 :
            await message.reply("Пожалуйста, укажите тип и продолжительность тренировки после команды (в минутах или часах)."
                                "\nНапример: /log_workout йога 30 минут")
            return

        if len(command_structure) > 4 :
            await message.reply("Пожалуйста, указывайте тренировки по одной."
                                "\nНапример: /log_workout бег 1 час")
            return

        try:
            duration = float(command_structure[2])
            if duration <= 0:
                await message.reply("Продолжительность тренировки должна быть больше 0.")
                return
        except ValueError:
            await message.reply("Пожалуйста, используйте цифры для ввода продолжительности тренировок.")
            return

        try:
            duration_unit = command_structure[3].lower()
            if not re.match(r"^(мин|час)[а-яА-Я]*$", duration_unit):
                await message.reply(
                    "Пожалуйста, укажите продолжительность тренировки в часах или минутах."
                    "\nНапример: 30 минут или 1.5 часа."
                )
                return
        except IndexError:
            await message.reply("Возникла ошибка, укажите информацию о тренировке еще раз.")
            return

        split_for_exercise = message.text.split(maxsplit=1)
        exercise = split_for_exercise[1]

        exercise_data = get_exercise_data(translate_to_english(exercise))
        if not exercise_data:
            await message.reply(f"Информация о тренировке '{exercise}' не найдена."
                                "\nПопробуйте другой варинт названия.")
            return

        try:
            burned_calories = round(exercise_data['exercises'][0]['nf_calories'], 2)
            exercise_duration_min = exercise_data['exercises'][0]['duration_min']

            user = users[user_id]
            user.daily.burned_calories += burned_calories
            user.daily.workout_minutes += exercise_duration_min

            # Если объем тренировок входит в первоначально указанный юзером — не меняем норму воды
            if user.daily.workout_minutes <= user.data.activity:
                exercise_water = (exercise_duration_min // 30) * 200
                water_status = f"\n💧 Не забудьте выпить {int(exercise_water)} мл воды."
            else:
                exercise_water = (exercise_duration_min // 30) * 200
                add_water = ((user.daily.workout_minutes - user.data.activity) // 30) * 200
                user.daily.water_goal += add_water
                water_status = f"\n❗ Норма воды изменилась! Новая цель: {int(user.daily.water_goal)} мл.\
                \n💧 Не забудьте выпить {int(exercise_water)} мл воды."

            save_users()

            await message.reply(
                f"💪 {exercise.capitalize()} — {int(burned_calories)} ккал."
                f"{water_status}"
                f"\n🔥 Всего сожжено {int(user.daily.burned_calories)} ккал."
            )

        except (KeyError, IndexError, ValueError):
            await message.reply(f"Что-то пошло не так 😔 Попробуйте еще раз.")
            return
    except Exception as e:
        await message.reply(f"Что-то пошло не так 😔 Попробуйте еще раз.")


@router.message(Command("check_progress"))
async def check_progress(message: Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.reply("Ваш профиль не найден 🧐"
                            "\nИспользуйте команду /set_profile, чтобы создать профиль.")
        return

    user = users[user_id]
    water_goal = user.daily.water_goal
    logged_water = user.daily.logged_water
    calorie_goal = user.daily.calorie_goal
    logged_calories = user.daily.logged_calories
    activity_minutes = user.data.activity
    burned_calories = user.daily.burned_calories

    water_left = max(water_goal - logged_water, 0)
    calories_left = round(calorie_goal - logged_calories)
    activity_calories = (activity_minutes // 30) * 200
    extra_burned = burned_calories - activity_calories

    if water_left == 0:
        water_status = "\n💧 Норма по воде выполнена!\n"
    else:
        water_status = f"\n💧 До выполнения нормы: {int(water_left)} мл.\n"

    # Норму калорий не обновляем при доп. физ. активности, в отличие от воды (не всегда нужно есть больше)
    # Но если сожженные ккал на экстра-тренировках перекрывают превышение по съеденным ккал — не выводим алерт
    if calories_left >= -10 and calories_left <= 10:
        calories_status = "\n🍎 Норма по калориям выполнена!"
    elif calories_left > 10:
        calories_status = f"\n🍎 До выполнения нормы: {int(calories_left)} ккал."
    elif calories_left < -10 and extra_burned > abs(calories_left):
        calories_status = "\n🍎 Норма по калориям выполнена!"
    else:
        calories_status = f"\n🍎 Норма по калориям превышена на {abs(int(calories_left))} ккал, может быть стоит начать тренировку?"

    graph_image = get_progress_visualisation(user.daily.logged_water,
                                             user.daily.water_goal,
                                             user.daily.logged_calories,
                                             user.daily.calorie_goal)

    graph_image.seek(0)

    buffered_file = BufferedInputFile(
        graph_image.read(),
        filename="buffer_img.png"
    )

    await message.reply(
        "📊 Прогресс:\n"
        f"\nВода:"
        f"\n🥤 Выпито: {int(logged_water)} мл из {int(water_goal)} мл."
        f"{water_status}"
        f"\nКалории:"
        f"\n🍽️ Потреблено: {int(logged_calories)} ккал из {int(calorie_goal)} ккал."
        f"{calories_status}"
        f"\n🔥 Всего сожжено {int(burned_calories)} ккал."
        f"\n⚖️ Баланс: {int(logged_calories - burned_calories)} ккал."
    )

    await message.answer_photo(buffered_file)

dp.include_router(router)

async def main():
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())