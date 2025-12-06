from dotenv import load_dotenv
import requests
import json
import os
import base64

# 加载 .env 文件中的环境变量
load_dotenv()

# ================= 配置部分 =================
LOGIN_URL = 'https://preserve-3.inrialpes.fr/api/sessions'
DATA_URL = 'https://preserve-3.inrialpes.fr/api/results'
OUTPUT_FILE_NAME = 'data.json' # 完整的聚合数据文件名
IMAGE_DIR_BASE = '.' # 图片和JSON保存的根目录，即脚本运行目录

# 新增：需要处理的 job_id 列表
JOB_IDS_TO_PROCESS = [
    # Classement des résultats
    '210', '220','230','559', '560', '561' ,"563","572",'577', '579', '587', 
    # Compteurs
    '510', '548',"589",
    # Personnalisation des prix
    "110","120","130","545","554","555","557","575","576","578","586",] 

# 登录账户信息
LOGIN_PAYLOAD = {
    "username": os.getenv("PRESERVE_USERNAME"),
    "password": os.getenv("PRESERVE_PASSWORD")
}

# 基础 Headers (模仿浏览器行为)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    'Content-Type': 'application/json',
    'Origin': 'https://preserve-3.inrialpes.fr',
    'Connection': 'keep-alive',
    # 初始 Referer 指向登录页
    'Referer': 'https://preserve-3.inrialpes.fr/users/login' 
}

def save_screenshots(data, base_dir):
    """
    解析数据，提取 Base64 编码的截图，并保存为 JPG 文件。
    保存路径格式：{base_dir}/{timestamp}_{id}.jpg
    
    参数:
        data (dict): 包含 'content' 列表的 JSON 数据
        base_dir (str): 截图保存的目录 (即 ./job_id/)
    """
    if 'content' not in data or not isinstance(data['content'], list):
        print("   警告：数据结构不正确，未找到 'content' 列表。")
        return

    saved_count = 0
    
    for item in data['content']:
        # 确保关键字段存在
        screenshot_b64 = item.get('screenshot')
        job_id = item.get('job_id')
        timestamp = item.get('timestamp')
        _id = item.get('id')

        if screenshot_b64 and job_id is not None and timestamp is not None and _id is not None:
            try:
                # 1. Base64 解码，你的示例 Base64 字符串以 '/9j/' 开头，
                #    是标准的 JPEG/JPG 文件头。
                image_bytes = base64.b64decode(screenshot_b64)
                
                # 2. 构建文件路径 (base_dir 已经包含了 job_id)
                filename = f"{timestamp}_{_id}.jpg"
                file_path = os.path.join(base_dir, filename)

                # 3. 写入文件 (base_dir 已在 main 中创建)
                with open(file_path, 'wb') as f:
                    f.write(image_bytes)
                
                saved_count += 1
            except Exception as e:
                print(f"   错误：处理 ID 为 {_id} 的截图时发生错误: {e}")

    print(f"   成功提取并保存了 {saved_count} 张截图到 {base_dir} 目录中。")


def process_job(session, token, job_id):
    """处理单个 job_id 的分页数据请求、整合、保存 JSON 和提取截图的任务。"""

    all_content = []
    page_id = 0
    page_count = 1 # 初始值，确保循环至少执行一次
    last_response_metadata = {} # 用于保存第一个（或最后一个成功）的响应元数据

    # 构建带有 Authorization 的 Headers，并更新 Referer
    data_headers = HEADERS.copy()
    data_headers['Authorization'] = f"Bearer {token}"
    data_headers['Referer'] = f'https://preserve-3.inrialpes.fr/jobs/{job_id}' # 动态更新 Referer
    
    # URL 参数的基础模板
    params = {
        'page_id': '0', # 每次循环会更新
        'job_id': str(job_id), # 使用当前 job_id
        'order': 'desc',
        'hidden': 'false'
    }

    print("\n2. 正在循环请求所有分页数据...")
    
    while page_id < page_count:
        params['page_id'] = str(page_id)
        
        try:
            print(f"   请求 Job ID {job_id} 的第 {page_id + 1} 页 (page_id={page_id})...")
            
            response_data = session.get(DATA_URL, headers=data_headers, params=params)
            response_data.raise_for_status()
            
            result_json = response_data.json()
            
            # 首次请求时，获取总页数
            if page_id == 0:
                page_count = result_json.get('page_count', 1)
                last_response_metadata = result_json.copy() # 保存元数据
                print(f"   Job ID {job_id} 总共发现 {page_count} 页数据。")
            
            # 累积 content
            current_content = result_json.get('content', [])
            all_content.extend(current_content)
            print(f"   第 {page_id + 1} 页获取 {len(current_content)} 条记录。")

            page_id += 1 # 准备请求下一页
            
        except Exception as e:
            print(f"数据请求 Job ID {job_id} 第 {page_id + 1} 页失败: {e}")
            break # 遇到错误则停止循环

    # 检查是否有获取到的数据
    if not all_content:
        print(f"\n警告：Job ID {job_id} 未获取到任何有效数据，跳过保存。")
        return

    # ----------------------------------------
    # 第三步：整合最终数据并保存到 JSON 文件
    # ----------------------------------------
    
    # 定义输出目录和文件路径
    output_dir = os.path.join(IMAGE_DIR_BASE, str(job_id))
    output_file_path = os.path.join(output_dir, OUTPUT_FILE_NAME)
    
    # 确保目标文件夹存在
    os.makedirs(output_dir, exist_ok=True)

    # 整合 JSON 结构
    final_json = last_response_metadata.copy() 
    final_json['content'] = all_content
    final_json['entity_count'] = len(all_content) 

    print(f"\n3. 正在写入完整的原始数据文件到目录 '{output_dir}' ...")
    
    try:
        with open(output_file_path, 'w', encoding='utf-8') as f:
            json.dump(final_json, f, ensure_ascii=False, indent=4)
            
        print(f"   文件已保存至: {os.path.abspath(output_file_path)}")
    except Exception as e:
        print(f"保存 JSON 文件失败: {e}")
        return
    
    # ----------------------------------------
    # 第四步：提取并保存截图
    # ----------------------------------------
    print("\n4. 正在提取并保存截图...")
    # 传递 output_dir 作为保存截图的基础目录
    save_screenshots(final_json, output_dir)


def main():
    # 使用 Session 保持会话状态
    session = requests.Session()
    
    # ----------------------------------------
    # 第一步：执行登录 (PUT 请求)
    # ----------------------------------------
    print(f"{'='*50}")
    print("开始执行脚本：获取登录凭证")
    print(f"{'='*50}")
    
    print(f"1. 正在尝试登录: {LOGIN_URL} ...")
    
    try:
        response_login = session.put(LOGIN_URL, headers=HEADERS, json=LOGIN_PAYLOAD)
        response_login.raise_for_status() 
        
        login_data = response_login.json()
        token = login_data.get('token') or login_data.get('access_token') or login_data.get('jwt')
        
        if not token:
            print("错误：登录成功但未找到 Token 字段。")
            print("返回数据预览:", json.dumps(login_data, indent=2))
            return

        print(f"   登录成功! 获取到的 Token: {token[:15]}...")

    except Exception as e:
        print(f"登录失败: {e}")
        return
    
    # ----------------------------------------
    # 第二步：循环处理所有 Job ID
    # ----------------------------------------
    
    print(f"\n{'='*50}")
    print(f"开始处理 {len(JOB_IDS_TO_PROCESS)} 个任务：{', '.join(JOB_IDS_TO_PROCESS)}")
    print(f"{'='*50}")

    for job_id in JOB_IDS_TO_PROCESS:
        process_job(session, token, job_id)
        print(f"\n--- Job ID {job_id} 处理完毕 ---")

    print(f"\n{'='*50}")
    print("所有任务处理完成。")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()