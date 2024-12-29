import streamlit as st
import pandas as pd
from processing import parallel_city_statistics, get_response, is_anomaly
import plotly.express as px

@st.cache_data
def load_data(file):
    df = pd.read_csv(file)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df

st.title("Аналитика температуры воздуха в городах")
st.header("1. Загрузка данных")

uploaded_file = st.file_uploader("Выберите CSV-файл", type=["csv"])

# Загрузка файла
if uploaded_file is not None:
    data = load_data(uploaded_file)
    st.write("Превью данных:")
    st.dataframe(data[:100]) # ограничиваем для слишком больших входных данных
    cities = data["city"].unique()
    data_updated, city_profiles, season_profiles = parallel_city_statistics(data)
    if data_updated.empty:
        st.error("Данные по аномалиям не рассчитались, проверьте загружаемый файл.")
    if city_profiles.empty:
        st.error("Статистика по городам не рассчиталась, проверьте загружаемый файл.")
    if season_profiles.empty:
        st.error("Профиль сезона не рассчитался, проверьте загружаемый файл.")
else:
    st.write("Пожалуйста, загрузите CSV-файл.")

# Выбор города
if uploaded_file is not None:
    if cities is not None:
        city = st.sidebar.selectbox("Выберите город", cities)
        if not data_updated.empty and not city_profiles.empty and not season_profiles.empty:
            data_city = data_updated[data_updated["city"] == city].copy().reset_index(drop=True)
            city_profile = city_profiles[city_profiles["city"] == city].copy().reset_index(drop=True)
            season_profile = season_profiles[season_profiles["city"] == city].copy().reset_index(drop=True)
        else:
            st.error("Файлы статистик пустые, проверьте загружаемый файл.")
    else:
        st.write("В загруженном файле отсутствует колонка city.")

# Загрузка API-ключа, проверка текущей температуры на аномальность
if uploaded_file is not None:
    st.sidebar.header("API OpenWeatherMap")
    api_key = st.sidebar.text_input("Введите API-ключ для OpenWeatherMap")
    st.header("2. Текущая температура")

    if not api_key:
        st.warning("Введите API-ключ, чтобы получить данные текущей температуры.")
    else:
        if city is not None:
            response = get_response(city, api_key)
        else:
            st.write("Выберите город")

        if "error" in response:
            st.error(response["error"])
        else:
            current_temp = response["temperature"]
            current_season = response["season"]
            weather_icon = response["weather_icon"]

        if "temperature" in response:
            st.write(f"Сейчас в {city}: {current_temp}°C {weather_icon}, сезон: {current_season}.")
            anomaly_status = is_anomaly(city, current_season, current_temp, season_profile)
            status = "нормальная" if not anomaly_status else "аномальная"
            st.write(f"Температура {status} для сезона.")

# Профиль сезона
if uploaded_file is not None and city is not None and not season_profile.empty:
    st.header("3. Температурный профиль сезона")

    if st.checkbox("Показать сезонный профиль"):
        st.write(f"**Сезонный профиль для {city}**")
        st.write(season_profile.set_index("city").round(2))

# Описательные статистики
if uploaded_file is not None and city is not None and not data_city.empty:
    st.header("4. Основные статистики")

    if st.checkbox("Показать описательную статистику"):
        data_filtred = data_city[["city", "season", "temperature"]]
        st.write(f"**Описательные статистики для {city}**")
        st.write(data_filtred.groupby(["city", "season"]).describe().round(2))

        # Боксплот
        fig = px.box(data_filtred, x="season", y="temperature",
                     title=f"Распределение температуры по сезонам в {city}",
                     labels={"season": "Сезон", "temperature": "Температура, °C"},
                     color="season", color_discrete_sequence=px.colors.qualitative.Pastel
                     )

        st.plotly_chart(fig)

# Динамика
if uploaded_file is not None and city is not None and not city_profile.empty:
    st.header("5. Динамика температуры")

    if st.checkbox("Показать динамику"):
        st.write(f"**Профиль города {city}**")
        st.write(city_profile.set_index("city").round(2))

        # Фильтр по годам
        data_city_dynamic = data_city.copy()
        data_city_dynamic["is_anomaly"] = data_city_dynamic["is_anomaly"] \
                .fillna("undefined") \
                .apply(lambda x: "anomaly" if x == 1.0 else "normal" if x == 0.0 else x)

        data_city_dynamic["year"] = data_city_dynamic["timestamp"].dt.year

        available_years = sorted(data_city_dynamic["year"].unique())
        all_years_option = "Выбрать все"
        select_options = [all_years_option] + available_years

        # Мультиселект по годам
        selected_years = st.sidebar.multiselect(
            "Выберите год (мультиселект)",
            select_options,
            default=all_years_option
        )

        if all_years_option in selected_years:
            selected_years = available_years

        data_city_dynamic_filtred = data_city_dynamic[data_city_dynamic["year"].isin(selected_years)]

        if data_city_dynamic_filtred.empty:
            st.warning("Нет данных для выбранных периодов.")
        else:
            # График динамики
            # Динамика по всем наблюдениям
            fig = px.scatter(
                data_city_dynamic_filtred,
                x="timestamp",
                y="temperature",
                color="is_anomaly",
                color_discrete_map={
                    "normal": "blue",
                    "anomaly": "red",
                    "undefined": "gray"
                },
                opacity=0.6,
                title=f"Динамика температуры воздуха в {city}",
                labels={"is_anomaly": "Характер температуры:", "timestamp": "Дата", "temperature": "Температура, °C"}
            )

            # Скользящее среднее
            fig.add_scatter(
                x=data_city_dynamic_filtred["timestamp"],
                y=data_city_dynamic_filtred["rolling_mean"],
                mode="lines",
                name="Скользящее среднее",
                line=dict(color="orange")
            )

            # Тренд
            fig.add_scatter(
                x=data_city_dynamic_filtred["timestamp"],
                y=data_city_dynamic_filtred["trend"],
                mode="lines",
                name="Линия тренда",
                line=dict(color="green")
            )

            fig.update_layout(
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    x=0.5,
                    y=-0.2,
                    xanchor="center"
                ),
                xaxis=dict(title="Дата"),
                yaxis=dict(title="Температура, °C"),
                height=600,
                annotations=[
                    dict(
                        text="*undefined — не хватает периода расчёта окна в 30 дней",
                        showarrow=False,
                        xref="paper",
                        yref="paper",
                        x=0,
                        y=-0.2,
                        font=dict(
                            family="Arial, sans-serif",
                            size=12,
                            color="gray"
                        ),
                        align="center"
                    )
                ]
            )

            st.plotly_chart(fig)

            # Круговая диаграмма частотности температуры
            # Подготовка данных
            data_city_polar = data_city_dynamic_filtred.copy()
            data_city_polar["month"] = data_city_polar["timestamp"].dt.month_name()
            data_city_polar["day"] = data_city_polar["timestamp"].dt.day
            data_city_polar['temperature'] = data_city_polar.temperature.round()

            data_city_polar_agg = data_city_polar.groupby(['city', 'month', 'temperature']) \
                .agg(days_count=('day', 'count')).reset_index()

            month_order = [
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"]

            data_city_polar_agg["month"] = pd.Categorical(data_city_polar_agg["month"],
                                                          categories=month_order, ordered=True)

            data_city_polar_agg = data_city_polar_agg.sort_values(["month", "temperature"])

            # Polar bar
            fig = px.bar_polar(
                data_city_polar_agg,
                r="days_count",
                theta="month",
                color="temperature",
                title=f"Температурная частотность за выбранный период в {city}",
                labels={"temperature": "Температура, °C"},
                color_continuous_scale="turbo",
            )

            fig.update_layout(
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=-0.3,
                    xanchor="center",
                    x=0.5
                )
            )

            st.plotly_chart(fig)