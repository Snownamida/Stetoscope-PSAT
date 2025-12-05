import os
import base64
import csv
import json
import time
from typing import List, Optional
from pydantic import BaseModel
from openai import OpenAI
from datetime import datetime # 导入 datetime 模块

# ================= 配置部分 =================
IMAGE_DIR = os.path.dirname(os.path.abspath(__file__))   # 图片和 JSON 所在的目录
OUTPUT_CSV = os.path.join(IMAGE_DIR,"results.csv") # 最终 CSV 输出路径
JSON_DATA_FILE = os.path.join(IMAGE_DIR, 'data.json') # data.json 的路径
MODEL_NAME = "gpt-5-mini"
# ===========================================

client = OpenAI()

# -----------------------
# 定义 Structured Output Schema
# -----------------------

class Hotel(BaseModel):
    position: int
    hotel_name: Optional[str]
    price: Optional[float]
    rating: Optional[float]
    is_ad: bool

class HotelList(BaseModel):
    hotels: List[Hotel]

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def analyze_image_with_structured_output(base64_image):
    """使用 Structured Output 的方式提取酒店信息"""

    system_prompt = """
你是一个专业的数据提取助手。你的任务是从 Booking.com 的酒店列表截图中提取结构化数据。
 hotel_name : 旅馆名称。如果截断看不清，返回 null。
 price : 价格数值。如果有原价和折后价，提取红色的/加粗的/较低的折后价格。只提取数字。
 position : 该旅馆在当前截图中的视觉顺序（从上到下，从1开始）。
 is_ad : 是否是广告/推广（检查是否有 "Pub", "Ad", "Sponsored", "Promoted", "推广" 等标签）。
 rating : 评分（例如 8.5, 9.0）。
"""

    user_content = [
        {"type": "input_text", "text": "请提取这张图中的所有旅馆信息"},
        {
            "type": "input_image",
            "image_url": f"data:image/jpeg;base64,{base64_image}"
        },
    ]

    response = client.responses.parse(
        model=MODEL_NAME,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        text_format=HotelList
    )

    return response.output_parsed

def load_metadata_from_json(json_path):
    """
    加载 data.json 文件，并创建一个以文件名为键的元数据查找字典。
    """
    metadata_map = {}
    if not os.path.exists(json_path):
        print(f"警告：元数据文件未找到: {json_path}")
        return metadata_map

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        content = data.get('content', [])
        
        for item in content:
            timestamp = item.get('timestamp')
            _id = item.get('id')
            participant = item.get('participant', {})

            if timestamp is None or _id is None:
                continue

            # 1. 构建文件名 (与 spider.py 保持一致)
            filename = f"{timestamp}_{_id}.jpg"
            
            # 2. 转换时间戳
            iso_time = "INVALID_TIMESTAMP"
            try:
                # 将毫秒转换为秒
                ts_sec = timestamp / 1000.0
                dt_obj = datetime.fromtimestamp(ts_sec)
                iso_time = dt_obj.isoformat()
            except Exception as e:
                print(f"时间戳转换失败 (Timestamp: {timestamp}): {e}")

            # 3. 存储元数据
            metadata_map[filename] = {
                'time': iso_time,
                'participant_id': participant.get('id'),
                'device_model': participant.get('device_model'),
                'android_version': participant.get('android_version'),
                'screen_width': participant.get('screen_width'),
                'screen_height': participant.get('screen_height')
            }
            
    except Exception as e:
        print(f"加载或解析 {json_path} 失败: {e}")
    
    return metadata_map

# -----------------------
# 断点续传：读取已处理的文件
# -----------------------
def get_processed_files(csv_file_path):
    if not os.path.exists(csv_file_path):
        return set()

    processed = set()
    try:
        with open(csv_file_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader, None) # 跳过表头
            for row in reader:
                if row:
                    processed.add(row[0]) # [0] 是 filename
    except Exception as e:
        print(f"读取 CSV 失败: {e}")

    return processed


# -----------------------
# 主程序
# -----------------------
def main():

    if not os.path.exists(IMAGE_DIR):
        print(f"错误：目录 '{IMAGE_DIR}' 不存在。")
        return

    # 1. 加载元数据
    print(f"正在从 {JSON_DATA_FILE} 加载元数据...")
    metadata_map = load_metadata_from_json(JSON_DATA_FILE)
    print(f"成功加载 {len(metadata_map)} 条元数据记录。")

    # 2. 准备图片文件列表
    all_files = [f for f in os.listdir(IMAGE_DIR)
                 if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    all_files.sort()

    processed_files = get_processed_files(OUTPUT_CSV)
    print(f"总 {len(all_files)} 张图，已处理 {len(processed_files)} 张。")

    file_exists = os.path.exists(OUTPUT_CSV)

    # 3. 打开 CSV 并定义新的表头
    with open(OUTPUT_CSV, mode='a', encoding='utf-8-sig', newline='') as csvfile:
        # 定义新的字段名，包含元数据
        fieldnames = [
            'filename', 'time', 
            'position', 'hotel_name', 'price', 'rating', 'is_ad',
            'participant_id', 'device_model', 'android_version', 
            'screen_width', 'screen_height'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        # 4. 循环处理文件
        for filename in all_files:
            if filename in processed_files:
                continue

            file_path = os.path.join(IMAGE_DIR, filename)
            print(f"正在处理: {filename} ...", end="", flush=True)

            # 4.1. 获取元数据
            # 使用 .get(filename, {}) 确保即使没有元数据也不会崩溃
            metadata = metadata_map.get(filename, {})

            # 4.2. 准备基础行数据（包含元数据）
            base_row = {
                'filename': filename,
                'time': metadata.get('time'),
                'participant_id': metadata.get('participant_id'),
                'device_model': metadata.get('device_model'),
                'android_version': metadata.get('android_version'),
                'screen_width': metadata.get('screen_width'),
                'screen_height': metadata.get('screen_height')
            }

            try:
                base64_img = encode_image(file_path)

                # 4.3. 调用 API 解析图像
                result: HotelList = analyze_image_with_structured_output(base64_img)

                hotel_count = 0

                if result and result.hotels:
                    for hotel in result.hotels:
                        # 复制基础行
                        hotel_row = base_row.copy()
                        # 更新酒店特定数据
                        hotel_row.update({
                            'position': hotel.position,
                            'hotel_name': hotel.hotel_name,
                            'price': hotel.price,
                            'rating': hotel.rating,
                            'is_ad': hotel.is_ad,
                        })
                        writer.writerow(hotel_row)
                        hotel_count += 1
                else:
                    # 即使没有找到酒店，也写入包含元数据的基础行
                    no_data_row = base_row.copy()
                    no_data_row['hotel_name'] = 'NO_DATA_FOUND'
                    writer.writerow(no_data_row)

                csvfile.flush()
                print(f" 完成，提取 {hotel_count} 条。")

            except Exception as e:
                print(f"\n处理 {filename} 出错：{e}")
                time.sleep(1)

    print("\n所有图片处理完成！")


if __name__ == "__main__":
    main()