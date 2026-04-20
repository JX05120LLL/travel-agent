"""
和风天气工具
============

设计目标：
- 对 Agent 暴露统一天气能力，而不是让 Agent 自己理解 3d / 7d / 15d / 30d 这些底层接口细节
- 如果目标日期在未来 30 天内，自动选择合适的天气预报接口
- 如果目标日期超过未来 30 天，返回季节气候参考，并提醒用户临近出发再查询精确天气
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta

import httpx
from dotenv import load_dotenv
from langchain_core.tools import tool
from tools.holiday_calendar import resolve_holiday_window

os.environ.pop("SSL_CERT_FILE", None)
os.environ.pop("REQUESTS_CA_BUNDLE", None)

load_dotenv()


MONTH_CLIMATE_HINTS = {
    1: {
        "season": "冬季",
        "trend": "整体偏冷，早晚温差较明显，部分城市可能有寒潮或雨雪天气。",
        "packing": "建议准备厚外套、保暖层，北方或高海拔地区注意防寒防滑。",
    },
    2: {
        "season": "冬末初春",
        "trend": "气温开始缓慢回升，但天气仍不稳定，冷暖切换较频繁。",
        "packing": "建议洋葱式穿搭，带上防风外套和基础保暖衣物。",
    },
    3: {
        "season": "春季",
        "trend": "整体转暖，部分地区降雨开始增多，适合踏青但要注意天气波动。",
        "packing": "建议准备轻薄外套、长袖和便携雨具。",
    },
    4: {
        "season": "春末",
        "trend": "大多数城市气温舒适，但南方部分地区湿度上升、降雨增加。",
        "packing": "建议准备薄外套、舒适步行鞋和雨伞。",
    },
    5: {
        "season": "春夏过渡期",
        "trend": "多数城市白天气温较舒适到偏暖，部分地区开始进入多雨阶段。",
        "packing": "建议以轻便衣物为主，并准备防晒和雨具。",
    },
    6: {
        "season": "初夏",
        "trend": "气温明显升高，南方闷热感增强，部分地区进入梅雨期。",
        "packing": "建议准备透气衣物、防晒用品，并注意防潮防雨。",
    },
    7: {
        "season": "盛夏",
        "trend": "多数城市炎热，高温和强对流天气概率较高。",
        "packing": "建议轻薄透气穿着，关注防晒、补水和午后雷阵雨。",
    },
    8: {
        "season": "盛夏",
        "trend": "整体仍然偏热，部分地区易出现连续高温或台风、暴雨过程。",
        "packing": "建议轻便衣物、防晒用品，并提前关注极端天气预警。",
    },
    9: {
        "season": "夏秋过渡期",
        "trend": "多数地区开始转凉，体感比 7-8 月更舒适，但降雨仍可能出现。",
        "packing": "建议准备夏装为主，同时带一件轻薄外套。",
    },
    10: {
        "season": "秋季",
        "trend": "大多数城市气温相对舒适，早晚偏凉，部分地区可能有秋雨。",
        "packing": "建议带薄外套、长袖和舒适步行鞋，早晚注意保暖。",
    },
    11: {
        "season": "深秋",
        "trend": "气温继续下降，北方寒意明显增强，南方也会逐步转凉。",
        "packing": "建议准备厚一点的外套和长裤，注意早晚温差。",
    },
    12: {
        "season": "初冬",
        "trend": "多数城市进入寒冷阶段，部分地区可能出现低温、雨雪或大风天气。",
        "packing": "建议准备保暖外套、防风衣物和防寒用品。",
    },
}


CITY_CLIMATE_NOTES = {
    "北京": "秋冬季通常偏干燥，春季风感较明显，出行注意补水和防风。",
    "上海": "湿度通常较高，梅雨和台风季对出行影响更明显。",
    "广州": "体感常偏暖偏湿，夏秋季要特别留意强降雨和闷热感。",
    "深圳": "整体偏暖湿，夏秋季需重点关注降雨和台风影响。",
    "成都": "空气湿度通常偏高，秋冬常见阴天或小雨，体感会比温度更凉一些。",
    "重庆": "夏季闷热感强，春秋转换较快，湿度高时体感偏重。",
    "杭州": "春季和梅雨期降水较活跃，秋季通常较舒适。",
    "南京": "四季分明，春秋适合旅行，但换季时早晚温差较明显。",
    "西安": "整体偏干燥，春季风沙和昼夜温差需要关注。",
    "苏州": "湿度较高，春夏之交和秋雨阶段要留意降水。",
    "昆明": "整体温差较温和，但早晚偏凉，紫外线较强。",
    "青岛": "受海洋影响，体感相对湿润，海风会增强早晚凉意。",
    "厦门": "整体温暖湿润，夏秋季需关注降雨和台风影响。",
    "三亚": "常年偏暖，日照强，雨季和台风期要提前看天气变化。",
    "哈尔滨": "冬季寒冷明显，保暖需求高，春秋季节短促。",
}


def _parse_date(value: str | None) -> date | None:
    """Parse YYYY-MM-DD date strings."""
    if not value:
        return None

    value = value.strip()
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _holiday_anchor_date(text: str, today: date) -> tuple[date, str] | None:
    """Resolve common holiday expressions to anchor dates."""
    current_year = today.year
    next_year = current_year + 1

    holiday_map = {
        "五一": (5, 1, "劳动节"),
        "劳动节": (5, 1, "劳动节"),
        "国庆": (10, 1, "国庆"),
        "国庆节": (10, 1, "国庆"),
        "元旦": (1, 1, "元旦"),
    }

    for keyword, (month, day, display_name) in holiday_map.items():
        if keyword not in text:
            continue

        anchor = date(current_year, month, day)
        if anchor < today:
            anchor = date(next_year, month, day)

        return anchor, display_name

    return None


def _extract_duration_days(text: str) -> int | None:
    """Extract duration like '7天' or '玩5日'."""
    match = re.search(r"(\d+)\s*(天|日)", text)
    if not match:
        return None

    duration = int(match.group(1))
    return duration if duration > 0 else None


def _default_duration_for_text(text: str) -> int | None:
    """Provide pragmatic defaults for common holiday windows."""
    if "国庆" in text:
        return 7
    if "五一" in text or "劳动节" in text:
        return 5
    if "元旦" in text:
        return 3
    if "周末" in text:
        return 2
    return None


def _resolve_weekend_range(text: str, today: date) -> tuple[date, date, str] | None:
    """Resolve phrases like 本周末 / 下周末."""
    weekday = today.weekday()  # Monday=0, Sunday=6
    this_saturday = today + timedelta(days=(5 - weekday) % 7)
    this_sunday = this_saturday + timedelta(days=1)

    if "下周末" in text:
        start = this_saturday + timedelta(days=7)
        end = start + timedelta(days=1)
        return start, end, "下周末"

    if "本周末" in text or "这周末" in text:
        return this_saturday, this_sunday, "本周末"

    return None


def _resolve_dates(
    start_date: str,
    end_date: str,
    date_text: str,
) -> tuple[date | None, date | None, str | None]:
    """
    Resolve precise dates or natural-language date expressions.

    Return:
    - start date
    - end date
    - explanation for how dates were resolved
    """
    today = date.today()
    requested_start = _parse_date(start_date)
    requested_end = _parse_date(end_date) or requested_start

    if requested_start:
        return requested_start, requested_end, "已按精确日期查询"

    text = (date_text or "").strip()
    if not text:
        return None, None, None

    holiday_window = resolve_holiday_window(text)
    if holiday_window:
        start = datetime.strptime(holiday_window["start_date"], "%Y-%m-%d").date()
        official_end = datetime.strptime(holiday_window["end_date"], "%Y-%m-%d").date()
        duration = _extract_duration_days(text)
        if duration:
            end = start + timedelta(days=duration - 1)
            duration_note = f"并按你提到的 {duration} 天行程处理"
        else:
            end = official_end
            duration_note = "默认按官方放假窗口处理"
        return (
            start,
            end,
            (
                f"已通过节假日工具将“{holiday_window['holiday_name']}”解析为 "
                f"{start.isoformat()} 至 {official_end.isoformat()}，{duration_note}"
            ),
        )

    weekend_range = _resolve_weekend_range(text, today)
    if weekend_range:
        start, end, label = weekend_range
        return start, end, f"已将“{label}”解析为 {start.isoformat()} 至 {end.isoformat()}"

    holiday_anchor = _holiday_anchor_date(text, today)
    if holiday_anchor:
        anchor_date, holiday_name = holiday_anchor
        duration = _extract_duration_days(text) or _default_duration_for_text(text) or 1
        resolved_end = anchor_date + timedelta(days=duration - 1)
        return (
            anchor_date,
            resolved_end,
            f"已将“{holiday_name}”解析为 {anchor_date.isoformat()} 开始，按 {duration} 天行程处理",
        )

    return None, None, None


def _pick_forecast_endpoint(target_end: date) -> str:
    """Pick the smallest forecast window that can cover target_end."""
    today = date.today()
    days_ahead = (target_end - today).days + 1

    if days_ahead <= 3:
        return "3d"
    if days_ahead <= 7:
        return "7d"
    if days_ahead <= 10:
        return "10d"
    if days_ahead <= 15:
        return "15d"
    return "30d"


def _build_climate_reference(city_name: str, start: date, end: date) -> str:
    """Return a generic seasonal climate reference for long-range dates."""
    months = []
    current = date(start.year, start.month, 1)
    end_marker = date(end.year, end.month, 1)

    while current <= end_marker:
        months.append(current.month)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    result = [
        f"【{city_name}{start.isoformat()} 至 {end.isoformat()} 季节气候参考】",
        (
            f"当前日期是 {date.today().isoformat()}，距离这段行程时间较远，"
            "目前不适合提供精确天气预报。建议在出发前 15 天到 30 天内再查询具体天气。"
        ),
        "",
        "以下内容为季节气候参考，不代表当天精确天气：",
    ]

    for month in months:
        hint = MONTH_CLIMATE_HINTS[month]
        result.append(
            f"- {month} 月通常属于{hint['season']}：{hint['trend']} {hint['packing']}"
        )

    city_note = CITY_CLIMATE_NOTES.get(city_name)
    if city_note:
        result.extend(["", f"{city_name}出行补充提示：{city_note}"])

    result.extend(
        [
            "",
            "建议：",
            "1. 现在先按季节特征准备路线、酒店和衣物思路。",
            "2. 临近出发时，再刷新精确天气，用于细化每日行程和行李准备。",
        ]
    )
    return "\n".join(result)


def _shift_same_season_to_next_year(start: date, end: date) -> tuple[date, date]:
    """Shift a historical holiday window to next year for seasonal reference only."""
    try:
        shifted_start = start.replace(year=start.year + 1)
    except ValueError:
        shifted_start = start + timedelta(days=365)

    duration = (end - start).days
    shifted_end = shifted_start + timedelta(days=duration)
    return shifted_start, shifted_end


def _fetch_json(url: str, *, headers: dict, params: dict) -> dict:
    """Simple HTTP helper for QWeather APIs."""
    response = httpx.get(url, headers=headers, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


@tool
def get_weather(
    city: str,
    start_date: str = "",
    end_date: str = "",
    date_text: str = "",
) -> str:
    """
    查询指定城市的天气信息。

    使用方式：
    - 只传 city：返回实时天气 + 未来短期预报
    - 传 start_date / end_date（格式 YYYY-MM-DD）：自动根据日期选择合适的预报接口
    - 传 date_text：支持像“国庆7天”“五一假期”“下周末”这类自然语言时间表达
    - 如果目标日期超过未来 30 天：返回季节气候参考，并提醒用户临近出发再查精确天气

    适用场景：
    - 问某城市最近几天天气怎么样
    - 问某次旅行日期范围内的天气适不适合出行
    - 问五一、国庆等旅行日期对应的天气或气候参考
    """
    api_key = os.getenv("QWEATHER_API_KEY")
    api_host = os.getenv("QWEATHER_HOST")
    if not api_key:
        return "错误：未配置和风天气 API Key（QWEATHER_API_KEY），请在 .env 文件中添加。"
    if not api_host:
        return "错误：未配置和风天气 API Host（QWEATHER_HOST），请在 .env 文件中添加。"

    headers = {"X-QW-Api-Key": api_key}
    exact_start = _parse_date(start_date)
    exact_end = _parse_date(end_date)
    requested_start, requested_end, resolution_note = _resolve_dates(
        start_date=start_date,
        end_date=end_date,
        date_text=date_text,
    )

    if start_date and not exact_start:
        return f"错误：start_date 格式无效，请使用 YYYY-MM-DD，例如 2026-10-01。当前传入：{start_date}"
    if end_date and not exact_end:
        return f"错误：end_date 格式无效，请使用 YYYY-MM-DD，例如 2026-10-07。当前传入：{end_date}"
    if date_text and not requested_start and not exact_start:
        return (
            f"错误：暂时无法识别 date_text={date_text}。"
            " 目前支持像“国庆7天”“五一假期”“本周末”“下周末”这样的表达，"
            "或者直接传 start_date / end_date。"
        )
    if requested_start and requested_end and requested_start > requested_end:
        return "错误：start_date 不能晚于 end_date。"

    geo_url = f"https://{api_host}/geo/v2/city/lookup"
    try:
        geo_data = _fetch_json(
            geo_url,
            headers=headers,
            params={"location": city, "lang": "zh"},
        )
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        return f"查询城市信息失败：HTTP {exc.response.status_code}，{detail}"
    except Exception as exc:
        return f"查询城市信息失败：{exc}"

    if geo_data.get("code") != "200" or not geo_data.get("location"):
        error_detail = geo_data.get("error", {}).get("detail")
        if error_detail:
            return f"找不到城市：{city}。接口提示：{error_detail}"
        return f"找不到城市：{city}（API 返回：{geo_data.get('code')}）"

    location = geo_data["location"][0]
    location_id = location["id"]
    city_name = location["name"]

    # 默认模式：实时天气 + 3天预报
    if not requested_start:
        now_url = f"https://{api_host}/v7/weather/now"
        forecast_url = f"https://{api_host}/v7/weather/3d"
        try:
            now_data = _fetch_json(now_url, headers=headers, params={"location": location_id})
            forecast_data = _fetch_json(forecast_url, headers=headers, params={"location": location_id})
        except httpx.HTTPStatusError as exc:
            return f"查询天气失败：HTTP {exc.response.status_code}，{exc.response.text}"
        except Exception as exc:
            return f"查询天气失败：{exc}"

        if now_data.get("code") == "200":
            now = now_data["now"]
            result = f"【{city_name}实时天气】\n"
            result += f"天气：{now['text']}，温度：{now['temp']}°C，体感温度：{now['feelsLike']}°C\n"
            result += f"风向：{now['windDir']}，风力：{now['windScale']}级，湿度：{now['humidity']}%\n\n"
        else:
            result = f"实时天气查询失败（code: {now_data.get('code')}）\n\n"

        if forecast_data.get("code") == "200":
            result += f"【{city_name}未来3天预报】\n"
            for day in forecast_data["daily"]:
                result += (
                    f"{day['fxDate']}：{day['textDay']}，"
                    f"{day['tempMin']}°C ~ {day['tempMax']}°C，"
                    f"降水概率：{day.get('pop', '未知')}%\n"
                )
        else:
            result += f"天气预报查询失败（code: {forecast_data.get('code')}）\n"
        return result

    today = date.today()
    if requested_start < today:
        if date_text:
            shifted_start, shifted_end = _shift_same_season_to_next_year(requested_start, requested_end)
            seasonal_hint = _build_climate_reference(city_name, shifted_start, shifted_end)
            return (
                f"{resolution_note}\n\n"
                "当前解析出的官方节假日窗口已经早于今天，说明这一年的节假日已经过去，"
                "或者下一年度官方安排还没有同步发布。\n"
                "下面先给你同季节的出行气候参考，等临近出发时再查询精确天气：\n\n"
                f"{seasonal_hint}"
            )
        return (
            f"错误：start_date={requested_start.isoformat()} 早于今天 {today.isoformat()}。"
            " 这个工具只查询今天及未来天气。"
        )

    if (requested_end - today).days >= 30:
        climate_text = _build_climate_reference(city_name, requested_start, requested_end)
        if resolution_note:
            return f"{resolution_note}\n\n{climate_text}"
        return climate_text

    forecast_window = _pick_forecast_endpoint(requested_end)
    forecast_url = f"https://{api_host}/v7/weather/{forecast_window}"

    try:
        forecast_data = _fetch_json(
            forecast_url,
            headers=headers,
            params={"location": location_id},
        )
    except httpx.HTTPStatusError as exc:
        return f"查询天气预报失败：HTTP {exc.response.status_code}，{exc.response.text}"
    except Exception as exc:
        return f"查询天气预报失败：{exc}"

    if forecast_data.get("code") != "200":
        return f"天气预报查询失败（code: {forecast_data.get('code')}）"

    filtered_days = [
        day
        for day in forecast_data["daily"]
        if requested_start <= _parse_date(day["fxDate"]) <= requested_end
    ]

    if not filtered_days:
        return (
            f"没有查到 {city_name} 在 {requested_start.isoformat()} 至 {requested_end.isoformat()} 的天气数据。"
            " 你可以稍后再试，或确认日期是否在未来 30 天内。"
        )

    heading = (
        f"【{city_name}{requested_start.isoformat()} 至 {requested_end.isoformat()}天气预报】"
        if requested_start != requested_end
        else f"【{city_name}{requested_start.isoformat()}天气预报】"
    )
    result_lines = [heading]
    if resolution_note:
        result_lines.append(resolution_note)
    result_lines.append(f"已自动调用未来 {forecast_window[:-1]} 天预报接口。")

    for day in filtered_days:
        result_lines.append(
            f"{day['fxDate']}：白天{day['textDay']}，夜间{day['textNight']}，"
            f"{day['tempMin']}°C ~ {day['tempMax']}°C，降水概率：{day.get('pop', '未知')}%，"
            f"风向：{day.get('windDirDay', '未知')}，风力：{day.get('windScaleDay', '未知')}级"
        )

    if requested_end == requested_start and len(filtered_days) == 1:
        result_lines.append("这是一天天气视角，适合判断是否需要带伞、增减衣物或调整当天行程。")
    else:
        result_lines.append("这是行程日期范围内的天气视角，适合判断整体节奏、穿衣准备和降雨风险。")

    return "\n".join(result_lines)
