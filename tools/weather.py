"""
和风天气工具
============
概念说明：
- @tool 装饰器：告诉 LangChain "这个函数可以作为工具给 LLM 使用"
  LLM 会读取函数名、参数、docstring 来理解这个工具能做什么
  ≈ Spring AI 里的 @Tool 注解

- 函数的 docstring（三引号注释）非常重要！
  LLM 靠它来决定"用户问什么问题时该调这个工具"
  写得越清晰，LLM 调用越准确
"""

import os
os.environ.pop("SSL_CERT_FILE", None)
os.environ.pop("REQUESTS_CA_BUNDLE", None)

import httpx
from langchain_core.tools import tool
from dotenv import load_dotenv

load_dotenv()


@tool
def get_weather(city: str) -> str:
    """
    查询指定城市当前天气和未来3天天气预报。
    当用户询问某个城市的天气、气温、是否需要带伞、旅行天气是否合适时，调用此工具。
    参数 city：城市名称，如"北京"、"成都"、"西安"
    """
    api_key = os.getenv("QWEATHER_API_KEY")
    api_host = os.getenv("QWEATHER_HOST")
    if not api_key:
        return "错误：未配置和风天气 API Key（QWEATHER_API_KEY），请在 .env 文件中添加"
    if not api_host:
        return "错误：未配置和风天气 API Host（QWEATHER_HOST），请在 .env 文件中添加"

    headers = {"X-QW-Api-Key": api_key}

    # 第一步：城市名 → 城市 ID（和风天气需要先查 location ID）
    geo_url = f"https://{api_host}/geo/v2/city/lookup"
    try:
        resp = httpx.get(
            geo_url,
            params={"location": city, "lang": "zh"},
            headers=headers,
            timeout=10,
        )
        geo_data = resp.json()
    except Exception as e:
        return f"查询城市信息失败：{e}"

    if geo_data.get("code") != "200" or not geo_data.get("location"):
        return f"找不到城市：{city}（API 返回：{geo_data.get('code')}）"

    location = geo_data["location"][0]
    location_id = location["id"]
    city_name = location["name"]

    # 第二步：查实时天气
    now_url = f"https://{api_host}/v7/weather/now"
    try:
        now_resp = httpx.get(now_url, params={"location": location_id}, headers=headers, timeout=10)
        now_data = now_resp.json()
    except Exception as e:
        return f"查询实时天气失败：{e}"

    # 第三步：查3天预报
    forecast_url = f"https://{api_host}/v7/weather/3d"
    try:
        forecast_resp = httpx.get(forecast_url, params={"location": location_id}, headers=headers, timeout=10)
        forecast_data = forecast_resp.json()
    except Exception as e:
        return f"查询天气预报失败：{e}"

    # 整理实时天气
    if now_data.get("code") == "200":
        now = now_data["now"]
        result = f"【{city_name}实时天气】\n"
        result += f"天气：{now['text']}，温度：{now['temp']}°C，体感温度：{now['feelsLike']}°C\n"
        result += f"风向：{now['windDir']}，风力：{now['windScale']}级，湿度：{now['humidity']}%\n\n"
    else:
        result = f"实时天气查询失败（code: {now_data.get('code')}）\n\n"

    # 整理3天预报
    if forecast_data.get("code") == "200":
        result += f"【{city_name}未来3天预报】\n"
        for day in forecast_data["daily"]:
            result += f"{day['fxDate']}：{day['textDay']}，"
            result += f"{day['tempMin']}°C ~ {day['tempMax']}°C，"
            result += f"降水概率：{day.get('pop', '未知')}%\n"
    else:
        result += f"天气预报查询失败（code: {forecast_data.get('code')}）\n"

    return result
