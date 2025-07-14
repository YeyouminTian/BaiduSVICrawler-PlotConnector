## 一、环境准备

### 1. 安装依赖包

在项目根目录下新建 `requirements.txt`，内容如下（如已安装可跳过）：

```txt
pandas
geopandas
shapely
numpy
Pillow
requests
opencv-python
```

安装命令：
```bash
pip install -r requirements.txt
```

---

## 二、准备数据

### 1. 地块数据（矢量数据）将左右的街景图片连接到地块id上
- 推荐格式：文件地理数据库（.gdb），需包含地块ID、地块类型（GH_LAYOUT）等字段。
- 示例路径：`D:/Test/卫星图测试/卫星图测试.gdb`

### 2. 街景点数据（CSV）
- CSV文件需包含街景点的经纬度坐标，推荐字段：`id,X,Y` ，坐标系为WGS84
- 示例内容：
  ```
  id,X,Y
  1,121.4939382,31.27539693
  2,121.4941003,31.27606852
  ...
  ```
- 放在项目根目录下，命名如 `example.csv`

### 3. 百度API Key
- 需注册百度开发者账号，获取“百度地图API”的 `ak`（API Key）
- [百度API控制台](https://lbsyun.baidu.com/apiconsole/key)

---

## 三、文件结构说明

```
项目目录/
│
├─ main.py                # 主程序入口
├─ landuse_utils.py       # 地块数据读取模块
├─ streetview_utils.py    # 街景API与点读取模块
├─ image_utils.py         # 图像处理模块
├─ spatial_analysis.py    # 空间分析与左右判别模块
├─ example.csv            # 示例街景点数据
├─ requirements.txt       # 依赖包列表
└─ output/                # 输出目录（自动生成）
```

---

## 四、如何运行

1. **修改 main.py 里的参数**  
   打开 `main.py`，找到如下部分，根据你的实际数据路径和需求修改参数：

   ```python
   if __name__ == '__main__':
       main(
           landuse_gdb_path='你的地块数据.gdb',
           landuse_layer='landuse',  # 图层名
           landuse_id_col='GH_ZXC_2_I',  # 地块ID字段名
           streetview_csv_path='example.csv',  # 街景点CSV
           baidu_ak='你的百度API Key',
           output_dir='output',
           zoom=3
       )
   ```

2. **运行主程序**
   - 在命令行（PowerShell/Anaconda Prompt）进入项目目录
   - 执行：
     ```bash
     python main.py
     ```

3. **查看输出**
   - 程序会自动下载街景图片，生成在 `output/images/` 文件夹下
   - 匹配结果表格在 `output/streetview_landuse_mapping.csv` 和 `.json` 文件中