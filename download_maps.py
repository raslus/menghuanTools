import os
import requests

BASE_URL = "http://xyq.yzz.cn/map/"
SAVE_DIR = os.path.join(os.path.dirname(__file__), "assets", "maps")

MAPS = {
    "建邺城": "jianye.jpg",
    "东海湾": "donghaiwan.jpg",
    "江南野外": "jiangnanyewai.jpg",
    "长安城": "changan.jpg",
    "大唐国境": "datangguojing.jpg",
    "大唐境外": "datangjingwai.jpg",
    "长寿村": "changshoucun.jpg",
    "长寿郊外": "changshoujiaowai.jpg",
    "傲来国": "aolaiguo.jpg",
    "花果山": "huaguoshan.jpg",
    "月宫": "yuegong.jpg",
    "大唐官府": "datang.jpg",
    "方寸山": "fangcun.jpg",
    "化生寺": "huasheng.jpg",
    "女儿村": "nver.jpg",
    "魔王寨": "mowang.jpg",
    "狮陀岭": "shituo.jpg",
    "地府": "difu.jpg",
    "盘丝洞": "pansi.jpg",
    "龙宫": "longgong.jpg",
    "天宫": "tiangong.jpg",
    "五庄观": "wuzhuang.jpg",
    "普陀山": "putuo.jpg",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def download_maps():
    os.makedirs(SAVE_DIR, exist_ok=True)
    
    for map_name, filename in MAPS.items():
        url = BASE_URL + filename
        save_path = os.path.join(SAVE_DIR, f"{map_name}.jpg")
        
        if os.path.exists(save_path) and os.path.getsize(save_path) > 1000:
            print(f"✓ {map_name} 已存在，跳过")
            continue
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            if response.status_code == 200 and len(response.content) > 1000:
                with open(save_path, "wb") as f:
                    f.write(response.content)
                print(f"✓ {map_name} 下载成功")
            else:
                print(f"✗ {map_name} 下载失败 ({response.status_code})")
        except Exception as e:
            print(f"✗ {map_name} 下载异常: {e}")

if __name__ == "__main__":
    download_maps()
