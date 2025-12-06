from typing import List, Optional
from pydantic import BaseModel

# 1. 定义单条数据的模型 (ItemModel)
# extract.py 会读取这个类的字段作为 CSV 的动态表头
class ItemModel(BaseModel):
    hotel_name: Optional[str]
    rating: Optional[float]
    review_count: Optional[int]

# 2. 定义整体响应模型 (ResponseModel)
class ResponseModel(BaseModel):
    hotels: List[ItemModel]

# 3. 指定 List 在 ResponseModel 中的字段名
# extract.py 会使用 getattr(result, LIST_FIELD_NAME) 来获取数据列表
LIST_FIELD_NAME = "hotels"

# 4. 定义 Prompt
SYSTEM_PROMPT = """
你是一个专业的数据提取助手。你的任务是从 Booking.com 的酒店列表截图中提取结构化数据。
 hotel_name : 旅馆名称。如果截断看不清，返回 null。
 rating : 评分（例如 8.5, 9.0）。
 review_count : 评论数量。
"""

USER_PROMPT_TEXT = "请提取这张图中的所有旅馆信息"