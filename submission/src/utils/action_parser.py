"""Parsing and validating model outputs for the GUI Agent protocol."""

from __future__ import annotations

import ast
import json
import re
from typing import Any, Dict, Optional, Tuple


VALID_ACTIONS = {"CLICK", "TYPE", "SCROLL", "OPEN", "COMPLETE"}

ACTION_ALIASES = {
    "CLICK": "CLICK",
    "TAP": "CLICK",
    "PRESS": "CLICK",
    "点击": "CLICK",
    "单击": "CLICK",

    "TYPE": "TYPE",
    "INPUT": "TYPE",
    "TEXT": "TYPE",
    "ENTER": "TYPE",
    "输入": "TYPE",
    "填写": "TYPE",

    "SCROLL": "SCROLL",
    "SWIPE": "SCROLL",
    "滑动": "SCROLL",
    "滚动": "SCROLL",

    "OPEN": "OPEN",
    "LAUNCH": "OPEN",
    "打开": "OPEN",

    "COMPLETE": "COMPLETE",
    "DONE": "COMPLETE",
    "FINISH": "COMPLETE",
    "完成": "COMPLETE",
    "结束": "COMPLETE",
}


APP_NAME_CANONICAL = {
    "12306": "铁路12306",
    "铁路": "铁路12306",

    "百度": "百度地图",
    "百度Map": "百度地图",

    "高德": "高德地图",

    "美团外卖": "美团",
    "美团App": "美团",

    "饿了么外卖": "饿了么",

    "B站": "哔哩哔哩",
    "b站": "哔哩哔哩",
    "bilibili": "哔哩哔哩",
    "Bilibili": "哔哩哔哩",

    "芒果": "芒果TV",
    "芒果tv": "芒果TV",
    "芒果视频": "芒果TV",

    "腾讯": "腾讯视频",
    "腾讯Video": "腾讯视频",

    "爱奇艺视频": "爱奇艺",

    "去哪旅行": "去哪儿旅行",
    "去哪儿": "去哪儿旅行",
    "去哪儿网": "去哪儿旅行",
    "去哪儿旅行网": "去哪儿旅行",

    "携程": "携程旅行",
    "携程网": "携程旅行",

    "飞猪": "飞猪旅行",

    "小破站": "哔哩哔哩",
}


def parse_model_action(
    raw_output: str,
    image_size: Tuple[int, int] | None = None,
    instruction: str = "",
) -> Tuple[Optional[str], Dict[str, Any]]:
    """Parse one action from arbitrary model text.

    Supported model output styles:
    - JSON: {"action":"CLICK","parameters":{"point":[500,800]}}
    - Legacy: CLICK:[[500, 800]] / TYPE:['abc']
    - Function style: click(point=[500,800])
    - Loose natural text containing action + parameters.
    """
    text = _strip_code_fence(str(raw_output or "").strip())
    if not text:
        return None, {}

    # 1) JSON object extraction.
    obj = _try_parse_json_object(text)
    if isinstance(obj, dict):
        action, params = _parse_from_dict(obj, image_size=image_size)
        if action:
            return action, _fill_missing_text(action, params, instruction)

    # 2) JSON/Python list after ACTION: prefix.
    action, params = _parse_legacy_action(text, image_size=image_size)
    if action:
        return action, _fill_missing_text(action, params, instruction)

    # 3) Function-call-like action syntax.
    action, params = _parse_function_call(text, image_size=image_size)
    if action:
        return action, _fill_missing_text(action, params, instruction)

    # 4) Very loose fallback.
    action, params = _parse_loose(text, image_size=image_size)
    if action:
        return action, _fill_missing_text(action, params, instruction)

    return None, {}


def sanitize_action(
    action: Optional[str],
    params: Dict[str, Any],
    image_size: Tuple[int, int] | None = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """Convert parsed action into the exact AgentOutput parameter schema."""
    action = _normalize_action(action)
    if action is None:
        return None, {}

    params = params or {}

    if action == "CLICK":
        point = _coerce_point(
            params.get("point")
            or params.get("coord")
            or params.get("coordinate")
            or params.get("position")
            or params.get("target"),
            image_size=image_size,
        )
        if point is None:
            return None, {}
        return action, {"point": point}

    if action == "SCROLL":
        start = _coerce_point(
            params.get("start_point")
            or params.get("start")
            or params.get("from")
            or params.get("point1"),
            image_size=image_size,
        )
        end = _coerce_point(
            params.get("end_point")
            or params.get("end")
            or params.get("to")
            or params.get("point2"),
            image_size=image_size,
        )
        if start is None or end is None:
            return None, {}
        return action, {"start_point": start, "end_point": end}

    if action == "TYPE":
        text = params.get("text")
        if text is None:
            text = params.get("content", "")
        return action, {"text": str(text).strip()}

    if action == "OPEN":
        app_name = params.get("app_name")
        if app_name is None:
            app_name = params.get("app") or params.get("name") or params.get("application") or ""
        app_name = _canonicalize_app_name(str(app_name))
        if not app_name:
            return None, {}
        return action, {"app_name": app_name}

    if action == "COMPLETE":
        return action, {}

    return None, {}


def _canonicalize_app_name(name: str) -> str:
    name = str(name or "").strip().strip("'\"`，。,:： ")
    if not name:
        return ""

    if name in APP_NAME_CANONICAL:
        return APP_NAME_CANONICAL[name]

    # 去掉模型常见赘词。
    name = re.sub(r"(应用|APP|App|app|软件)$", "", name).strip()
    return APP_NAME_CANONICAL.get(name, name)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```(?:json|python|text)?\s*(.*?)\s*```$", text, flags=re.S | re.I)
    if fence:
        return fence.group(1).strip()
    return text


def _normalize_action(action: Any) -> Optional[str]:
    if action is None:
        return None

    s = str(action).strip().strip("'\"`：: ")
    upper = s.upper()

    if upper in ACTION_ALIASES:
        return ACTION_ALIASES[upper]
    if s in ACTION_ALIASES:
        return ACTION_ALIASES[s]

    return upper if upper in VALID_ACTIONS else None


def _try_parse_json_object(text: str) -> Any:
    candidates = []

    if text.startswith("{") and text.endswith("}"):
        candidates.append(text)

    extracted = _extract_balanced_object(text)
    if extracted and extracted not in candidates:
        candidates.append(extracted)

    for cand in candidates:
        for loader in (json.loads, ast.literal_eval):
            try:
                return loader(cand)
            except Exception:
                pass

        repaired = re.sub(r",\s*([}\]])", r"\1", cand)
        try:
            return json.loads(repaired.replace("'", '"'))
        except Exception:
            continue

    return None


def _extract_balanced_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        return ""

    depth = 0
    in_str = False
    quote = ""
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_str = False
            continue

        if ch in ('"', "'"):
            in_str = True
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start: i + 1]

    return ""


def _parse_from_dict(
    obj: Dict[str, Any],
    image_size: Tuple[int, int] | None = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    action = _normalize_action(obj.get("action") or obj.get("Action") or obj.get("type"))
    if not action:
        return None, {}

    params = (
        obj.get("parameters")
        or obj.get("params")
        or obj.get("argument")
        or obj.get("arguments")
    )

    if params is None:
        params = {
            k: v
            for k, v in obj.items()
            if k.lower() not in {"action", "type", "thought", "target", "reason"}
        }

    if not isinstance(params, dict):
        params = _params_from_sequence(action, params)

    return sanitize_action(action, params, image_size=image_size)


def _parse_legacy_action(
    text: str,
    image_size: Tuple[int, int] | None = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    m = re.search(
        r"(?:^|\n)\s*(?:Action\s*[:：]\s*)?"
        r"([A-Za-z_]+|点击|输入|填写|滑动|滚动|打开|完成|结束)\s*[:：]\s*"
        r"(\[[\s\S]*\]|\{[\s\S]*\}|'.*?'|\".*?\")",
        text,
        flags=re.I,
    )
    if not m:
        return None, {}

    action = _normalize_action(m.group(1))
    if not action:
        return None, {}

    payload = m.group(2).strip()
    value = _safe_parse_literal(payload)
    params = _params_from_sequence(action, value)

    return sanitize_action(action, params, image_size=image_size)


def _parse_function_call(
    text: str,
    image_size: Tuple[int, int] | None = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    m = re.search(
        r"([A-Za-z_]+|点击|输入|填写|滑动|滚动|打开|完成|结束)\s*\((.*?)\)",
        text,
        flags=re.I | re.S,
    )
    if not m:
        return None, {}

    action = _normalize_action(m.group(1))
    if not action:
        return None, {}

    body = m.group(2).strip()
    params: Dict[str, Any] = {}

    for key, val in re.findall(
        r"(\w+)\s*=\s*(\[[^\]]*\]|'[^']*'|\"[^\"]*\"|[^,]+)",
        body,
    ):
        params[key] = _safe_parse_literal(val.strip())

    if not params and body:
        params = _params_from_sequence(action, _safe_parse_literal(body))

    return sanitize_action(action, params, image_size=image_size)


def _parse_loose(
    text: str,
    image_size: Tuple[int, int] | None = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    action = None

    for token in sorted(ACTION_ALIASES, key=len, reverse=True):
        if re.search(re.escape(token), text, flags=re.I):
            action = _normalize_action(token)
            break

    if not action:
        return None, {}

    if action in {"CLICK", "SCROLL"}:
        nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", text)]

        if action == "CLICK" and len(nums) >= 2:
            return sanitize_action(action, {"point": nums[:2]}, image_size=image_size)

        if action == "SCROLL" and len(nums) >= 4:
            return sanitize_action(
                action,
                {"start_point": nums[:2], "end_point": nums[2:4]},
                image_size=image_size,
            )

    if action == "TYPE":
        m = re.search(
            r"(?:text|content|内容|输入|填写)\s*[:=：]\s*['\"]?([^'\"\n]+)",
            text,
            flags=re.I,
        )
        return sanitize_action(action, {"text": m.group(1).strip() if m else ""})

    if action == "OPEN":
        m = re.search(
            r"(?:app_name|app|应用|打开)\s*[:=：]?\s*['\"]?([^'\"\n，,。]+)",
            text,
            flags=re.I,
        )
        return sanitize_action(action, {"app_name": m.group(1).strip() if m else ""})

    if action == "COMPLETE":
        return "COMPLETE", {}

    return None, {}


def _safe_parse_literal(payload: str) -> Any:
    payload = str(payload).strip()

    for loader in (json.loads, ast.literal_eval):
        try:
            return loader(payload)
        except Exception:
            pass

    return payload.strip().strip("'\"")


def _params_from_sequence(action: str, value: Any) -> Dict[str, Any]:
    action = _normalize_action(action) or ""

    if action == "CLICK":
        return {"point": _first_point(value)}

    if action == "SCROLL":
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return {"start_point": value[0], "end_point": value[1]}
        return {}

    if action == "TYPE":
        if isinstance(value, (list, tuple)) and value:
            return {"text": value[0]}
        return {"text": value}

    if action == "OPEN":
        if isinstance(value, (list, tuple)) and value:
            return {"app_name": value[0]}
        return {"app_name": value}

    if action == "COMPLETE":
        return {}

    return {}


def _first_point(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        if len(value) == 2 and all(isinstance(v, (int, float, str)) for v in value):
            return value
        if value:
            return value[0]
    return value


def _coerce_point(
    value: Any,
    image_size: Tuple[int, int] | None = None,
) -> Optional[list[int]]:
    """Normalize a point to 0-1000 integer coordinates.

    Handles three common model mistakes:
    1. 0-1 coordinates, e.g. [0.52, 0.83] -> [520, 830]
    2. 0-100 percentage coordinates, e.g. [52, 83] -> [520, 830]
    3. Obvious pixel coordinates beyond 1000, e.g. y=1800.
    """
    if value is None:
        return None

    if isinstance(value, str):
        nums = re.findall(r"-?\d+(?:\.\d+)?", value)
        if len(nums) >= 2:
            value = [float(nums[0]), float(nums[1])]
        else:
            return None

    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None

    try:
        fx = float(value[0])
        fy = float(value[1])
    except Exception:
        return None

    if fx < 0 or fy < 0:
        return None

    # Case 1: 0-1 normalized coordinates.
    if 0 <= fx <= 1 and 0 <= fy <= 1:
        fx *= 1000
        fy *= 1000

    # Case 2: 0-100 percentage coordinates.
    elif 0 <= fx <= 100 and 0 <= fy <= 100:
        # 模型经常输出 [50, 80] 表示 50%, 80%。
        # 评测要求 0-1000，所以转成 [500, 800]。
        if fx >= 2 or fy >= 2:
            fx *= 10
            fy *= 10

    # Case 3: obvious pixel coordinates.
    elif image_size is not None:
        width, height = image_size
        if width > 0 and height > 0 and (fx > 1000 or fy > 1000):
            # 只有明显超过 1000 时才当像素坐标转归一化；
            # 否则 500/800 这种数既可能是像素，也可能已经是归一化坐标。
            if fx <= width * 1.2 and fy <= height * 1.2:
                fx = fx / width * 1000
                fy = fy / height * 1000

    x = int(round(fx))
    y = int(round(fy))

    x = max(0, min(1000, x))
    y = max(0, min(1000, y))

    return [x, y]


def _fill_missing_text(action: str, params: Dict[str, Any], instruction: str) -> Dict[str, Any]:
    """Infer TYPE content if the model chose TYPE but omitted text."""
    if action != "TYPE":
        return params

    text = params.get("text") or params.get("content") or ""
    if str(text).strip():
        return params

    inferred = infer_text_from_instruction(instruction)
    if inferred:
        params = dict(params)
        params["text"] = inferred

    return params


def infer_text_from_instruction(instruction: str) -> str:
    """Best-effort extraction for common Chinese task wording.

    This is only used when the model selected TYPE but forgot the text.
    It should be conservative to avoid inserting a long task sentence.
    """
    s = instruction or ""
    s = s.strip()

    patterns = [
        r"发布评论[：:](.+)$",
        r"发表评论[：:](.+)$",
        r"评论[：:](.+)$",
        r"输入[：:](.+)$",
        r"填写[：:](.+)$",
        r"搜索[：:](.+)$",
        r"查找[：:](.+)$",

        r"搜索《?([^，。,.、]+)》?",
        r"查找《?([^，。,.、]+)》?",
        r"播放《?([^，。,.、]+)》?",
        r"听《?([^，。,.、]+)》?",
        r"购买《?([^，。,.、]+)》?",
    ]

    for pat in patterns:
        m = re.search(pat, s)
        if m:
            val = m.group(1).strip()
            val = val.strip("《》\"'“”")
            if val:
                return val

    return ""