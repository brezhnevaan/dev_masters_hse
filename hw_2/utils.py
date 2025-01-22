import io
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from googletrans import Translator


def get_water_norm(weight: int, activity: int, temperature: float) -> int:
    weight_water = weight * 30
    activity_water = (activity // 30) * 500
    weather_water = 500 if temperature > 25 else 0
    total_water = weight_water + activity_water + weather_water
    return total_water


def get_calories_norm(weight: int, height: int, age: int, activity: int) -> float:
    weight_calories = weight * 10
    height_calories = height * 6.25
    age_calories = age * 5
    activity_calories = (activity // 30) * 200
    total_calories = weight_calories + height_calories - age_calories + activity_calories
    return total_calories


translator = Translator()


def translate_to_english(text: str) -> str:
    result = translator.translate(text, dest='en')
    return result.text


def get_progress_visualisation(logged_water: float, water_goal: float,
                               logged_calories: float, calories_goal: float):
    # Расчетные данные
    progress_water = int((logged_water / water_goal) * 100)
    water_left = max(int(water_goal - logged_water), 0)
    water_extra = max(int(logged_water - water_goal), 0)
    logged_water_update = min(int(water_goal), int(logged_water))

    progress_calories = int((logged_calories / calories_goal) * 100)
    calories_left = max(int(calories_goal - logged_calories), 0)
    calories_extra = max(int(logged_calories - calories_goal), 0)
    logged_calories_update = min(int(calories_goal), int(logged_calories))

    # Цвета и настройки
    water_achieved_color = "blue"
    water_remaining_color = "skyblue"
    water_excess_color = "purple"

    food_achieved_color = "crimson"
    food_remaining_color = "lightpink"
    food_excess_color = "purple"

    background_color = "white"

    text_size = 18

    fig = make_subplots(
        rows=2, cols=2,
        specs=[[{"type": "domain"}, {"type": "domain"}], [{"type": "xy"}, {"type": "xy"}]],
        subplot_titles=(
            "Круговая диаграмма прогресса воды",
            "Круговая диаграмма прогресса калорий",
            "Абсолютный прогресс воды",
            "Абсолютный прогресс калорий"
        ),
        vertical_spacing=0.0005,
        horizontal_spacing=0.15
    )

    # Визуализации
    # Круговая диаграмма воды
    if progress_water <= 100:
        pie_water = go.Pie(
            values=[progress_water, 100 - progress_water],
            labels=["Прогресс", "Осталось"],
            hole=0.5,
            marker=dict(colors=[water_achieved_color, water_remaining_color]),
            textinfo="percent",
            textposition="inside",
            insidetextfont=dict(size=text_size, color=["white", "black"]),
            outsidetextfont=dict(size=text_size, color="black")
        )
    else:
        pie_water = go.Pie(
            values=[100, 0],
            labels=["Прогресс"],
            hole=0.5,
            marker=dict(colors=[water_achieved_color]),
            textinfo="none",
            texttemplate=f"{progress_water}%",
            textposition="inside",
            insidetextfont=dict(size=text_size, color="white")
        )
    fig.add_trace(pie_water, row=1, col=1)

    # Круговая диаграмма калорий
    if progress_calories <= 100:
        pie_food = go.Pie(
            values=[progress_calories, 100 - progress_calories],
            labels=["Прогресс", "Осталось"],
            hole=0.5,
            marker=dict(colors=[food_achieved_color, food_remaining_color]),
            textinfo="percent",
            textposition="inside",
            insidetextfont=dict(size=text_size, color=["white", "black"]),
            outsidetextfont=dict(size=text_size, color="black")
        )
    else:
        pie_food = go.Pie(
            values=[100, 0],
            labels=["Прогресс"],
            hole=0.5,
            marker=dict(colors=[food_achieved_color]),
            textinfo="none",
            texttemplate=f"{progress_calories}%",
            textposition="inside",
            insidetextfont=dict(size=text_size, color="white")
        )
    fig.add_trace(pie_food, row=1, col=2)

    # Барчарт воды
    bar_water = go.Bar(
        y=[""],
        x=[logged_water_update],
        name="Logged",
        text=[logged_water_update],
        textposition="inside",
        orientation="h",
        marker=dict(color=water_achieved_color),
        width=0.3,
        textfont=dict(size=text_size, color="white")
    )
    goal_bar_water = go.Bar(
        y=[""],
        x=[water_left],
        name="Осталось",
        text=[water_left],
        textposition="inside",
        orientation="h",
        marker=dict(color=water_remaining_color),
        width=0.3,
        textfont=dict(size=text_size, color="black")
    )
    excess_bar_water = go.Bar(
        y=[""],
        x=[water_extra],
        name="Превышение",
        text=[water_extra],
        textposition="inside",
        orientation="h",
        marker=dict(color=water_excess_color),
        width=0.3,
        textfont=dict(size=text_size, color="white")
    )
    fig.add_trace(bar_water, row=2, col=1)
    fig.add_trace(goal_bar_water, row=2, col=1)
    fig.add_trace(excess_bar_water, row=2, col=1)

    # Барчарт еды
    bar_food = go.Bar(
        y=[""],
        x=[logged_calories_update],
        name="Logged",
        text=[logged_calories_update],
        textposition="inside",
        orientation="h",
        marker=dict(color=food_achieved_color),
        width=0.3,
        textfont=dict(size=text_size, color="white")
    )
    goal_bar_food = go.Bar(
        y=[""],
        x=[calories_left],
        name="Осталось",
        text=[calories_left],
        textposition="inside",
        orientation="h",
        marker=dict(color=food_remaining_color),
        width=0.3,
        textfont=dict(size=text_size, color="black")
    )
    excess_bar_food = go.Bar(
        y=[""],
        x=[calories_extra],
        name="Превышение",
        text=[calories_extra],
        textposition="inside",
        orientation="h",
        marker=dict(color=food_excess_color),
        width=0.3,
        textfont=dict(size=text_size, color="white")
    )
    fig.add_trace(bar_food, row=2, col=2)
    fig.add_trace(goal_bar_food, row=2, col=2)
    fig.add_trace(excess_bar_food, row=2, col=2)

    fig.update_xaxes(visible=False, row=2, col=2)

    # Настройка подписей
    fig.update_layout(
        annotations=[
            dict(
                text=f"Достижение цели по воде:",
                x=0.2, y=1.02, xref="paper", yref="paper",
                font=dict(size=text_size, color="black"),
                showarrow=False
            ),
            dict(
                text=f"Норма воды: {int(water_goal)} мл",
                x=0.2, y=0.35, xref="paper", yref="paper",
                font=dict(size=text_size, color="black"),
                showarrow=False
            ),
            dict(
                text=f"Достижение цели по калориям:",
                x=0.75, y=1.02, xref="paper", yref="paper",
                font=dict(size=text_size, color="black"),
                showarrow=False
            ),
            dict(
                text=f"Норма калорий: {int(calories_goal)} ккал",
                x=0.75, y=0.35, xref="paper", yref="paper",
                font=dict(size=text_size, color="black"),
                showarrow=False
            ),
        ],
        height=700,
        width=900,
        title="Ваш прогресс в графиках!",
        title_x=0.5,
        margin=dict(t=150),
        title_font=dict(size=20, color="black"),
        paper_bgcolor=background_color,
        plot_bgcolor=background_color,
        barmode="stack",
        showlegend=False,
        xaxis=dict(visible=False),
        yaxis=dict(showgrid=False, zeroline=False),
    )

    img_buffer = io.BytesIO()
    fig.write_image(img_buffer, format="png")
    img_buffer.seek(0)
    return img_buffer
