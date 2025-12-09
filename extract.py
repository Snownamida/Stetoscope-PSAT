import os
import csv
import json
import time
import base64
import importlib.util
from datetime import datetime
from typing import List, Dict, Any

from openai import OpenAI

# ================= 配置 =================
MODEL_NAME = "gpt-5-mini"
# =======================================

client = OpenAI()

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def load_metadata_from_json(json_path):
    """通用元数据加载逻辑"""
    metadata_map = {}
    if not os.path.exists(json_path):
        return metadata_map
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        content = data.get('content', [])
        for item in content:
            timestamp = item.get('timestamp')
            _id = item.get('id')
            participant = item.get('participant', {})
            if timestamp is None or _id is None: continue
            
            filename = f"{timestamp}_{_id}.jpg"
            # 时间转换
            iso_time = "INVALID"
            try:
                ts_sec = timestamp / 1000.0
                iso_time = datetime.fromtimestamp(ts_sec).isoformat()
            except: pass

            metadata_map[filename] = {
                'time': iso_time,
                'participant_id': participant.get('id'),
                'device_model': participant.get('device_model'),
                'android_version': participant.get('android_version'),
                'screen_width': participant.get('screen_width'),
                'screen_height': participant.get('screen_height')
            }
    except Exception as e:
        print(f"元数据加载警告: {e}")
    return metadata_map

def get_processed_files(csv_file_path):
    """断点续传检查"""
    if not os.path.exists(csv_file_path):
        return set()
    processed = set()
    try:
        with open(csv_file_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader, None) # 跳过表头
            for row in reader:
                if row: processed.add(row[0])
    except: pass
    return processed

def load_schema_module(directory):
    """动态加载子目录下的 schema.py 模块"""
    schema_path = os.path.join(directory, "schema.py")
    if not os.path.exists(schema_path):
        return None
    
    spec = importlib.util.spec_from_file_location("schema_module", schema_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def process_directory(directory):
    """处理单个子目录的核心逻辑"""
    
    # 1. 动态加载该目录的配置 (Schema)
    schema = load_schema_module(directory)
    if not schema:
        return

    print(f"\n======== 正在处理任务目录: {os.path.basename(directory)} ========")
    
    # 路径定义
    json_data_file = os.path.join(directory, 'data.json')
    output_csv = os.path.join(directory, "results.csv")
    
    # 2. 加载元数据
    metadata_map = load_metadata_from_json(json_data_file)
    
    # 3. 获取图片列表
    all_files = [f for f in os.listdir(directory) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    all_files.sort()
    
    processed_files = get_processed_files(output_csv)
    print(f"发现 {len(all_files)} 张图片，已处理 {len(processed_files)} 张。")

    # 4. 确定 CSV 表头 (关键修改部分)
    # 4.1 计算当前代码逻辑期望的完整字段列表
    base_fieldnames = ['filename', 'time', 'participant_id', 'device_model','android_version', 'screen_width', 'screen_height']
    schema_fieldnames = list(schema.ItemModel.model_fields.keys())
    expected_fieldnames = base_fieldnames + schema_fieldnames

    # 4.2 检查文件是否存在，如果存在，读取它实际的表头顺序
    final_fieldnames = expected_fieldnames
    file_exists = os.path.exists(output_csv)

    if file_exists:
        try:
            with open(output_csv, mode='r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                existing_header = next(reader, None)
                if existing_header:
                    # 如果文件有表头，强制使用文件的表头顺序
                    final_fieldnames = existing_header
                    print("检测到现有 CSV，将使用现有表头顺序写入。")
        except Exception as e:
            print(f"读取现有 CSV 表头失败: {e}，将使用默认顺序。")

    # 5. 打开 CSV 准备写入
    # 注意：extrasaction='ignore' 是为了防止 Schema 新增了字段但旧 CSV 没有该列时报错
    with open(output_csv, mode='a', encoding='utf-8-sig', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=final_fieldnames, extrasaction='ignore')
        
        if not file_exists:
            writer.writeheader()

        for filename in all_files:
            if filename in processed_files:
                continue
            
            file_path = os.path.join(directory, filename)
            print(f"  -> 处理: {filename} ... ", end="", flush=True)

            # 准备基础数据
            meta = metadata_map.get(filename, {})
            base_row = {k: meta.get(k) for k in base_fieldnames if k != 'filename'}
            base_row['filename'] = filename

            try:
                base64_img = encode_image(file_path)

                # === 核心调用 ===
                response = client.beta.chat.completions.parse(
                    model=MODEL_NAME,
                    messages=[
                        {"role": "system", "content": schema.SYSTEM_PROMPT},
                        {
                            "role": "user", 
                            "content": [
                                {"type": "text", "text": schema.USER_PROMPT_TEXT},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                            ]
                        },
                    ],
                    response_format=schema.ResponseModel,
                )
                
                parsed_result = response.choices[0].message.parsed
                items_list = getattr(parsed_result, schema.LIST_FIELD_NAME, [])
                if getattr(schema, "SINGLE_ITEM",False):
                    items_list=[items_list]
                
                item_count = 0
                if items_list:
                    for item in items_list:
                        row = base_row.copy()
                        # 将 Pydantic 对象转为 dict 并更新到 row
                        row.update(item.model_dump())
                        
                        # DictWriter 会自动根据 fieldnames 的顺序从 row 字典中取值
                        # 如果 row 中有一些字段在 final_fieldnames 中不存在 (比如 Schema 新增了字段)，
                        # extrasaction='ignore' 会忽略它们，防止崩溃。
                        writer.writerow(row)
                        item_count += 1
                else:
                    writer.writerow(base_row)

                csvfile.flush()
                print(f"提取 {item_count} 条")

            except Exception as e:
                print(f"出错: {e}")
                time.sleep(1)

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 遍历当前目录下的所有子文件夹
    for entry in os.listdir(root_dir):
        full_path = os.path.join(root_dir, entry)
        if os.path.isdir(full_path) and not entry.startswith('.'):
            process_directory(full_path)

if __name__ == "__main__":
    main()