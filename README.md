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

### 1. 地块数据（矢量数据）
- 推荐格式：文件地理数据库（.gdb），需包含地块ID、地块类型（GH_LAYOUT）等字段。
- 示例路径：`D:/Test/卫星图测试/卫星图测试.gdb`

### 2. 道路数据（矢量数据）
- 格式：文件地理数据库（.gdb），图层名称：`road_街景测试范围_0712`
- 用于建立街景点与道路的关联关系

### 3. 街景点数据（CSV）
- CSV文件需包含街景点的经纬度坐标，推荐字段：`id,X,Y` ，坐标系为WGS84
- 示例内容：
  ```
  id,X,Y
  1,121.4939382,31.27539693
  2,121.4941003,31.27606852
  ...
  ```
- 放在项目根目录下，命名如 `example.csv`

### 4. 百度API Key
- 需注册百度开发者账号，获取"百度地图API"的 `ak`（API Key）
- [百度API控制台](https://lbsyun.baidu.com/apiconsole/key)

---

## 三、文件结构说明

```
项目目录/
│
├─ main.py                           # 主程序入口
├─ landuse_utils.py                  # 地块数据读取模块
├─ streetview_utils.py               # 街景API与点读取模块
├─ image_utils.py                    # 图像处理模块
├─ spatial_analysis.py               # 空间分析与左右判别模块
├─ topology_utils.py                 # 拓扑关系处理模块（新增）
├─ example.csv                       # 示例街景点数据
├─ requirements.txt                  # 依赖包列表
└─ output/                           # 输出目录（自动生成）
    ├─ images/                       # 街景图像
    ├─ streetview_landuse_mapping.csv    # 基础关联表
    ├─ landuse_traversal_config.csv      # 地块遍历配置表（新增）
    └─ streetview_multi_landuse_mapping.csv  # 多地块关联表（新增）
```

---

## 四、功能特性

### 1. 基础功能
- 街景图像下载和透视展开
- 左右视图自动生成
- 地块空间关联分析

### 2. 拓扑关系功能（新增）
- **地块-道路-街景点三元关联**：建立完整的三元关系网络
- **按道路分组排序**：实现类似人类视角的有序遍历
- **多地块关联**：同一街景点在不同地块中的位置关系
- **完整编码体系**：图像命名包含地块、道路、街景点信息

### 3. 输出文件说明

**landuse_traversal_config.csv** - 地块遍历配置表
```csv
landuse_id,road_id,road_sequence,streetview_id,point_sequence,filename_L,filename_R
P001,R001,1,S001,1,P001_R001_S001_L.jpg,P001_R001_S001_R.jpg
P001,R001,1,S002,2,P001_R001_S002_L.jpg,P001_R001_S002_R.jpg
```

**streetview_multi_landuse_mapping.csv** - 多地块关联表
```csv
streetview_id,landuse_id,road_id,road_sequence,point_sequence
S001,P001,R001,1,1
S001,P002,R001,3,2
```

---

## 五、如何运行

1. **修改 main.py 里的参数**  
   打开 `main.py`，找到如下部分，根据你的实际数据路径和需求修改参数：

   ```python
   if __name__ == '__main__':
       main(
           landuse_gdb_path='你的地块数据.gdb',
           landuse_layer='landuse',  # 图层名
           landuse_id_col='GH_ZXC_2_I',  # 地块ID字段名
           road_layer='road_街景测试范围_0712',  # 道路图层名
           road_id_col='OBJECTID',  # 道路ID字段名
           streetview_csv_path='example.csv',  # 街景点CSV
           baidu_ak='你的百度API Key',
           output_dir='output',
           zoom=3,
           save_every=50,
           build_topology=True  # 是否构建拓扑关系
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
   - 基础关联结果表格在 `output/streetview_landuse_mapping.csv` 和 `.json` 文件中
   - 拓扑关系配置在 `output/landuse_traversal_config.csv` 中
   - 多地块关联在 `output/streetview_multi_landuse_mapping.csv` 中

---

## 六、图像命名规则

新的图像命名规则包含完整的三元关系信息：

```
P{地块ID}_R{道路ID}_S{街景点ID}_{L/R}.jpg

示例：
P001_R005_S123_L.jpg  # 地块001，道路005，街景点123，左视图
P001_R005_S123_R.jpg  # 地块001，道路005，街景点123，右视图
```

从图像名称可以追溯：
- 地块信息：P001
- 道路信息：R005  
- 街景点信息：S123
- 视角方向：L/R

---

## 七、遍历顺序说明

程序会按照以下逻辑组织街景图像：

1. **按地块分组**：以地块为单位组织所有相关街景点
2. **按道路排序**：地块内的道路按空间角度排序（顺时针）
3. **道路内排序**：每条道路内的街景点按空间顺序排列
4. **生成遍历序列**：形成类似人类绕地块观察的连续序列

这样的组织方式便于：
- 按地块查看街景
- 按道路分组管理
- 实现连续的空间遍历体验