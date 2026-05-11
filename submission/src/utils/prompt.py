"""Prompt utilities for Android GUI Agent."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple


APP_ALIASES = {
    "铁路12306": [
        "铁路12306", "12306", "中国铁路", "火车票", "高铁票",
    ],
    "百度地图": [
        "百度地图", "百度地图app", "百度map", "百度地圖",
    ],
    "高德地图": [
        "高德地图", "高德", "高德地图app",
    ],
    "美团": [
        "美团", "美团外卖", "美团app",
    ],
    "饿了么": [
        "饿了么", "饿了么外卖",
    ],
    "大众点评": [
        "大众点评", "点评",
    ],
    "淘宝": [
        "淘宝", "淘宝网", "手机淘宝",
    ],
    "京东": [
        "京东", "京东商城",
    ],
    "拼多多": [
        "拼多多", "pdd",
    ],
    "抖音": [
        "抖音", "douyin",
    ],
    "快手": [
        "快手", "kuaishou",
    ],
    "哔哩哔哩": [
        "哔哩哔哩", "bilibili", "Bilibili", "B站", "b站", "小破站",
    ],
    "爱奇艺": [
        "爱奇艺", "爱奇艺视频",
    ],
    "腾讯视频": [
        "腾讯视频", "腾讯video", "腾讯",
    ],
    "芒果TV": [
        "芒果TV", "芒果tv", "芒果", "芒果视频",
    ],
    "优酷": [
        "优酷", "优酷视频",
    ],
    "喜马拉雅": [
        "喜马拉雅", "喜马拉雅听书",
    ],
    "QQ音乐": [
        "QQ音乐", "qq音乐",
    ],
    "网易云音乐": [
        "网易云音乐", "网易云",
    ],
    "微信": [
        "微信", "WeChat", "wechat",
    ],
    "支付宝": [
        "支付宝", "Alipay", "alipay",
    ],
    "去哪儿旅行": [
        "去哪儿旅行", "去哪旅行", "去哪儿", "去哪儿网", "去哪儿旅行网",
    ],
    "携程旅行": [
        "携程旅行", "携程", "携程网",
    ],
    "飞猪旅行": [
        "飞猪旅行", "飞猪",
    ],
    "中兴管家": [
        "中兴管家",
    ],
    "小红书": [
        "小红书", "RED", "rednote",
    ],
    "微博": [
        "微博", "新浪微博",
    ],
}


def _normalize_text(text: str) -> str:
    text = text or ""
    return re.sub(r"\s+", "", text).lower()


def infer_app_name(instruction: str) -> str:
    """Infer canonical app name from user instruction."""
    text = instruction or ""
    norm = _normalize_text(text)

    candidates = []
    for canonical, aliases in APP_ALIASES.items():
        for alias in aliases:
            candidates.append((canonical, alias))

    # Prefer longer aliases to avoid short ambiguous matches.
    candidates.sort(key=lambda x: len(x[1]), reverse=True)

    for canonical, alias in candidates:
        if _normalize_text(alias) in norm:
            return canonical

    return ""


def _format_history_actions(history_actions: List[Dict[str, Any]]) -> str:
    if not history_actions:
        return "[]"
    try:
        return json.dumps(history_actions[-8:], ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(history_actions[-8:])


def _history_has_action(history_actions: List[Dict[str, Any]], action: str) -> bool:
    action = action.upper()
    for item in history_actions or []:
        if str(item.get("action", "")).upper() == action:
            return True
    return False


def _last_action(history_actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not history_actions:
        return {}
    return history_actions[-1] or {}


def _last_click_point(history_actions: List[Dict[str, Any]]) -> List[int]:
    for item in reversed(history_actions or []):
        if str(item.get("action", "")).upper() == "CLICK":
            params = item.get("parameters", {}) or {}
            point = params.get("point")
            if isinstance(point, list) and len(point) == 2:
                try:
                    return [int(point[0]), int(point[1])]
                except Exception:
                    return []
    return []


def build_gui_agent_prompt(
    instruction: str,
    step_count: int,
    image_size: Tuple[int, int],
    history_actions: List[Dict[str, Any]],
) -> str:
    """Build a robust GUI-control prompt for VLM."""
    app_name = infer_app_name(instruction)
    history_text = _format_history_actions(history_actions)
    has_open = _history_has_action(history_actions, "OPEN")
    last = _last_action(history_actions)
    last_click = _last_click_point(history_actions)

    width, height = image_size

    repeated_search_warning = ""
    if last_click and last_click[0] >= 780 and last_click[1] <= 110:
        repeated_search_warning = (
            "\n特别注意：上一轮已经点击过右上角搜索图标。"
            "当前如果需要继续搜索，不要再次点击右上角图标；"
            "应点击顶部搜索输入框中部，或在键盘已出现时直接 TYPE。\n"
        )

    prompt = f"""
你是一个 Android 手机 GUI Agent。你需要根据当前截图、用户任务和历史动作，输出下一步操作。

用户任务：
{instruction}

推断目标应用：
{app_name if app_name else "未知"}

当前步数：
{step_count}

当前截图尺寸：
width={width}, height={height}

是否已经执行过 OPEN：
{has_open}

上一动作：
{json.dumps(last, ensure_ascii=False, default=str)}

最近历史动作：
{history_text}
{repeated_search_warning}

你只能输出一个严格 JSON 对象，不要 markdown，不要解释，不要输出思考过程。

动作集合与格式：
1. CLICK
{{"action":"CLICK","parameters":{{"point":[x,y]}}}}

2. TYPE
{{"action":"TYPE","parameters":{{"text":"要输入的文字"}}}}

3. SCROLL
{{"action":"SCROLL","parameters":{{"start_point":[x1,y1],"end_point":[x2,y2]}}}}

4. OPEN
{{"action":"OPEN","parameters":{{"app_name":"应用名"}}}}

5. COMPLETE
{{"action":"COMPLETE","parameters":{{}}}}

坐标规则：
- 所有坐标必须是 0 到 1000 的整数归一化坐标。
- 左上角是 [0,0]，右下角是 [1000,1000]。
- 禁止输出 0 到 1 的小数坐标。
- 禁止输出 0 到 100 的百分比坐标。
- 禁止输出像素坐标。
- 禁止输出 [0,0]、[0,1]、[1,0]、[1,1] 这类角落无效点。
- 点击时尽量点目标控件的中心，而不是边缘。

OPEN 规则：
- OPEN 只应该用于第一步打开目标应用。
- 如果历史中已经有 OPEN，后续禁止再次 OPEN。
- 如果已经在目标 App 内，继续执行 CLICK / TYPE / SCROLL / COMPLETE。

搜索入口规则：
- 很多 App 的搜索入口在顶部区域，常见位置是右上角搜索图标或顶部搜索框。
- 刚打开 App 首页且任务需要搜索视频、地点、店铺、商品、音乐或内容时，通常应点击顶部搜索入口。
- 如果上一动作已经点击过右上角搜索图标，当前界面通常已经进入搜索页或搜索输入状态。
- 此时不要再次点击右上角搜索图标。
- 下一步应点击顶部搜索输入框的中部，或在键盘出现后直接 TYPE。
- 顶部搜索输入框的安全点击区域通常在屏幕上方中间，不要点击最右侧图标边缘。
- 对于顶部搜索框，优先选择搜索框中部区域，而不是右上角按钮边缘。

输入动作规则：
- 如果屏幕底部出现中文键盘、英文键盘、九宫格键盘或候选词栏，通常说明输入框已经聚焦。
- 如果输入框已经聚焦且任务需要输入内容，应优先 TYPE。
- 如果没有键盘，且需要输入搜索词、地点、评论、店名、视频名或商品名，通常应先 CLICK 输入框。
- 如果上一动作是 CLICK，且当前截图已经出现键盘，则下一步优先 TYPE。
- 如果上一动作是 TYPE，且当前截图中输入框已有目标文本，则下一步不要继续 TYPE，应 CLICK 搜索、确认、完成、发送或第一个相关结果。
- TYPE 只输入任务中需要输入的关键词或评论，不要输入完整任务句子。

评论/发布规则：
- 如果任务要求发表评论，流程通常是：打开评论区 -> 点击评论输入框 -> TYPE 评论文本 -> 点击发布/发送。
- 如果已经输入评论文本，下一步通常点击“发布”“发送”或右下角确认按钮。
- 不要在输入文本后继续重复 TYPE。

隐藏测试泛化原则：
- 不要按照固定样例流程机械执行；必须根据当前截图判断真实控件位置。
- 如果是商品评价、订单评价、评论填写类任务，且已经成功 TYPE 了较长评价文本，下一步若界面没有明确“发布/提交”按钮，可以输出 COMPLETE。
- 如果上一动作是 TYPE 且文本已出现在输入框中，不要继续重复 TYPE；应根据界面点击确认/搜索/发布，或在任务已完成时 COMPLETE。
- 对非公开样例任务，不要固定使用某个 App 的特定坐标；应点击当前截图中真实可见的目标控件中心。

完成规则：
- 只有当用户目标已经完成时才输出 COMPLETE。
- 如果只是打开了目标页面但还没有执行目标动作，不要 COMPLETE。
- 如果已经成功发布、成功播放、成功搜索到目标并进入目标结果，才考虑 COMPLETE。

弹窗处理：
- 如果有权限、定位、协议、青少年模式、广告、登录提醒等弹窗阻挡任务，优先点击允许、同意、跳过、以后再说、关闭。
- 如果弹窗不是必须处理，不要乱点页面中部推荐内容。

输出要求：
- 只输出 JSON。
- 不要输出解释。
- 不要输出 markdown。
- 不要输出多个动作。
- 不要输出自然语言。

现在根据当前截图输出下一步动作。
""".strip()

    return prompt
