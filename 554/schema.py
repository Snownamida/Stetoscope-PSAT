from typing import List, Optional
from pydantic import BaseModel

# 1. 定义单条数据的模型 (ItemModel)
# extract.py 会读取这个类的字段作为 CSV 的动态表头
class ItemModel(BaseModel):
    trip_date : Optional[str]
    departure : Optional[str]
    destination : Optional[str]
    departure_time : Optional[str]
    destination_time : Optional[str]
    price: Optional[float]

# 2. 定义整体响应模型 (ResponseModel)
class ResponseModel(BaseModel):
    items: List[ItemModel]

# 3. 指定 List 在 ResponseModel 中的字段名
# extract.py 会使用 getattr(result, LIST_FIELD_NAME) 来获取数据列表
LIST_FIELD_NAME = "items"

# 4. 定义 Prompt
SYSTEM_PROMPT = """
你是一个专业的数据提取助手。你的任务是从Flixbus网站的行程列表截图中提取结构化数据。
 trip_date : 行程日期（MM-DD)
 departure : 出发地
 destination : 目的地
 departure_time : 出发时间（HH:mm）
 destination_time : 到达时间（HH:mm）
 price : 价格数值。如果有原价和折后价，提取红色的/加粗的/较低的折后价格。只提取数字。如果不是欧元转换成欧元
"""

USER_PROMPT_TEXT = "请提取这张图中的所有行程信息"