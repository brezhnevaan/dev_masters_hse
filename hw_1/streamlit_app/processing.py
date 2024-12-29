import numpy as np
import requests
from datetime import datetime, timezone, timedelta
from sklearn.linear_model import LinearRegression
from multiprocess.pool import Pool
import pandas as pd

# Для определения сезона даты, для которой делаем запрос по API
month_to_season = {12: "winter", 1: "winter", 2: "winter",
                   3: "spring", 4: "spring", 5: "spring",
                   6: "summer", 7: "summer", 8: "summer",
                   9: "autumn", 10: "autumn", 11: "autumn"}

# Словарь с иконками для основных погодных условий
weather_icons = {
    "Clear": "☀️",
    "Rain": "🌧️",
    "Snow": "❄️",
    "Clouds": "☁️"}

# Главная "тяжелая" функция запроса всей статистики по городу
def city_statistics(df, window_days=30):
    # Определение аномалий по скользящим статистикам
    df["rolling_mean"] = df.temperature.rolling(window=window_days).mean()
    df["rolling_std"] = df.temperature.rolling(window=window_days).std()

    df["is_anomaly"] = np.where(
        df["rolling_mean"].notna() & df["rolling_std"].notna(),
        (df["temperature"] < df["rolling_mean"] - 2 * df["rolling_std"]) |
        (df["temperature"] > df["rolling_mean"] + 2 * df["rolling_std"]),
        np.nan
    )

    # Общий профиль города
    city_profile = df.groupby("city", as_index=False) \
        .agg(temp_mean=("temperature", "mean"),
             temp_min=("temperature", "min"),
             temp_max=("temperature", "max"),
             anomalies_count=("is_anomaly", "sum"),
             obs_count=("timestamp", "size")
             )

    city_profile["anomalies_share"] = city_profile.anomalies_count / city_profile.obs_count

    # + Тренд
    df_temp = df.copy()
    df_temp["timestamp_unix"] = df_temp["timestamp"].astype("int64") // 10 ** 9

    X = df_temp["timestamp_unix"].values.reshape(-1, 1)
    y = df_temp["temperature"].values

    model = LinearRegression()
    model.fit(X, y)

    df["trend"] = model.predict(X)
    slope = model.coef_[0]

    if abs(slope) < 1e-9:
        trend = "doesn`t exist"
    elif slope < 0:
        trend = "negative"
    else:
        trend = "positive"

    city_profile["trend"] = trend

    # Профиль сезона
    # Оставляем город в groupby, чтобы можно было объединить выводы функции в один df
    season_profile = df.groupby(["season", "city"], as_index=False).agg(
        temp_mean=("temperature", "mean"),
        temp_std=("temperature", "std")
    )

    return df, city_profile, season_profile

# Распараллеливание главной функции обработки городов
def parallel_city_statistics(df, num_processes=8):
    groups_by_city = [df[df["city"] == city].copy().reset_index(drop=True) for city in df["city"].unique()]

    with Pool(processes=num_processes) as pool:
        results = pool.map(city_statistics, groups_by_city)

    df_result = pd.concat([result[0] for result in results], ignore_index=True)
    city_profile_result = pd.concat([result[1] for result in results], ignore_index=True)
    season_profile_result = pd.concat([result[2] for result in results], ignore_index=True)

    return df_result, city_profile_result, season_profile_result

# Сезон для даты запроса температуры по API
def get_season(unix_timestamp, timezone_offset):
    local_timezone = timezone(timedelta(seconds=timezone_offset))
    local_time = datetime.fromtimestamp(unix_timestamp, tz=local_timezone)
    month = local_time.month
    season = month_to_season[month]

    return season

# Функция запроса в API
# Запрос делаем для одного города, не используем асинхронность
def get_response(city, key):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={key}&units=metric"
    try:
        response = requests.get(url)
        response.raise_for_status()

        try:
            data = response.json()
        except ValueError:
            return {"error": "Некорректный формат ответа от API"}

        if (
                "main" not in data or
                "temp" not in data["main"] or
                "dt" not in data or
                "timezone" not in data or
                "weather" not in data or
                "main" not in data["weather"][0]
        ):
            return {"error": "Некорректный формат данных от API"}

        temperature = data["main"]["temp"]
        unix_timestamp = data["dt"]
        timezone = data["timezone"]
        season = get_season(unix_timestamp, timezone)
        weather = data["weather"][0]["main"]
        weather_icon = weather_icons.get(weather, "")

        return {"temperature": temperature, "season": season, "weather_icon": weather_icon}

    except requests.exceptions.HTTPError as e:
        if response.status_code == 401:
            return {"error": "Некорректный API-ключ"}
        elif response.status_code == 404:
            return {"error": "Город не найден"}
        else:
            return {"error": f"HTTP ошибка: {e}"}

    except Exception as e:
        return {"error": f"Ошибка: {e}"}

# Является ли значение аномальным для сезона
def is_anomaly(city, season, current_temp, season_profile):
    city_season_profile = season_profile[
        (season_profile["city"] == city) & (season_profile["season"] == season)] \
        .copy().reset_index(drop=True)

    if city_season_profile.empty:
        raise ValueError(f"Данные {city}-{season} отсутствуют")

    mean = city_season_profile["temp_mean"].values[0]
    std = city_season_profile["temp_std"].values[0]

    return bool(current_temp < mean - 2 * std or current_temp > mean + 2 * std)