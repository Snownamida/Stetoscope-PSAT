from typing import List, Optional
from pydantic import BaseModel

# 1. 定义单条数据的模型 (ItemModel)
# extract.py 会读取这个类的字段作为 CSV 的动态表头
class ItemModel(BaseModel):
    rank: int
    product_name: Optional[str]
    price: Optional[float]
    rating: Optional[float]
    sold_count:Optional[int]
    discount: Optional[float]

# 2. 定义整体响应模型 (ResponseModel)
class ResponseModel(BaseModel):
    items: List[ItemModel]

# 3. 指定 List 在 ResponseModel 中的字段名
# extract.py 会使用 getattr(result, LIST_FIELD_NAME) 来获取数据列表
LIST_FIELD_NAME = "items"

# 4. 定义 Prompt
SYSTEM_PROMPT = """
你是一个专业的数据提取助手。你的任务是从电商网站的货品列表截图中提取结构化数据。
 product_name : 商品名称。如果截断看不清，返回 null。
 price : 价格数值。如果有原价和折后价，提取红色的/加粗的/较低的折后价格。只提取数字。如果不是欧元转换成欧元
 rank : 该商品在当前截图中的视觉顺序（从上到下，从1开始）。
 rating : 评分（例如 8.5, 9.0）。
 sold_count : 商品销售数量
 discount : 折扣（如果有的话，提取折扣百分比，如果是-15%就是0.15）。
"""

USER_PROMPT_TEXT = "请提取这张图中的所有商品信息"