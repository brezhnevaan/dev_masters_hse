import requests
from typing import Optional
from config import API_WEATHER_TOKEN, API_NUTRITIONIX_APP, API_NUTRITIONIX_TOKEN


def get_city_temperature(city: str) -> Optional[float]:
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_WEATHER_TOKEN}&units=metric"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data.get("main", {}).get("temp")
    else:
        print(f"Ошибка: {response.status_code} - {response.text}")
        return None


def get_product_nutrition(product: str) -> Optional[float]:
    url = "https://trackapi.nutritionix.com/v2/natural/nutrients"
    headers = {
        "x-app-id": API_NUTRITIONIX_APP,
        "x-app-key": API_NUTRITIONIX_TOKEN,
        "Content-Type": "application/json"
    }
    data = {
        "query": product,
        "locale": "en_US"
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Ошибка: {response.status_code} - {response.text}")
        return None


def get_exercise_data(exercise: str) -> Optional[float]:
    url = "https://trackapi.nutritionix.com/v2/natural/exercise"
    headers = {
        "x-app-id": API_NUTRITIONIX_APP,
        "x-app-key": API_NUTRITIONIX_TOKEN,
        "Content-Type": "application/json"
    }
    data = {
        "query": exercise
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Ошибка: {response.status_code} - {response.text}")
        return None
