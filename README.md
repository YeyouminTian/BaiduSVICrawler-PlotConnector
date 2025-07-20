# 百度街景图爬取、展开、获取各视图与地块关联分析工具

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
tqdm
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
├─ topology_utils.py                 # 拓扑关系处理模块
├─ example.csv                       # 示例街景点数据
├─ requirements.txt                  # 依赖包列表
└─ output/                           # 输出目录（自动生成）
    ├─ images/                       # 街景图像
    ├─ streetview_landuse_mapping.csv    # 基础关联表
    ├─ landuse_traversal_config.csv      # 地块遍历配置表
    └─ streetview_multi_landuse_mapping.csv  # 多地块关联表
```

---

## 四、核心算法原理

### 1. 空间左右判别算法

#### 1.1 基于叉积的左右判别
```python
def judge_left_right(streetview_pt, road_dir, landuse_centroid):
    """
    使用叉积判断地块相对于街景点的左右位置
    
    算法原理：
    1. 计算道路方向向量（基于街景拍摄方向）
    2. 计算地块质心到街景点的向量
    3. 计算叉积：landuse_vec × road_vec
    4. 叉积正负决定左右位置
    """
```

**数学原理**：
- 道路方向向量：`road_vec = [cos(θ), sin(θ)]`
- 地块向量：`landuse_vec = [dx, dy]`
- 叉积：`cross = landuse_vec[0] * road_vec[1] - landuse_vec[1] * road_vec[0]`
- 判断：`cross < 0` 为左侧，`cross > 0` 为右侧

#### 1.2 多地块关联策略
- **最近邻搜索**：找到距离街景点最近的两个地块
- **左右分配**：将两个地块分别分配到左右视图
- **距离优化**：当左右判断冲突时，优先选择距离更近的地块

### 2. 拓扑关系构建算法

#### 2.1 地块-道路-街景点三元关联
```python
def build_landuse_topology(landuse_id, streetview_road_mapping, landuse_gdf, landuse_id_col, streetview_landuse_mapping, traversal_direction='clockwise'):
    """
    为单个地块建立完整的拓扑关系
    
    算法步骤：
    1. 获取地块质心坐标
    2. 收集地块关联的所有街景点
    3. 按道路分组街景点
    4. 计算道路质心并排序
    5. 对道路内街景点排序
    """
```

#### 2.2 道路排序算法
**基于角度的道路排序**：
- 计算地块质心到各道路质心的角度
- 按顺时针或逆时针方向排序
- 实现类似人类绕地块观察的连续序列

**道路内街景点排序**：
- 使用相邻两点的相对角度排序，避免跨越0度线问题
- 计算街景点相对于地块质心的极坐标角度
- 检测并修正跨越0度线的情况，确保空间连续性

#### 2.3 遍历方向控制
- **顺时针遍历**：`traversal_direction='clockwise'`
- **逆时针遍历**：`traversal_direction='counterclockwise'`
- 支持自定义遍历方向，适应不同的分析需求
- 道路排序和街景点排序都遵从统一的遍历方向参数

### 3. 图像处理与透视变换

#### 3.1 全景图像下载
- 使用百度街景API获取全景图像
- 支持不同缩放级别（zoom参数）
- 自动处理坐标系转换（WGS84 → BD09MC）

#### 3.2 透视变换算法
```python
def equirectangular_to_perspective(equirectangular_img, fov_h, fov_v, heading, pitch, out_size):
    """
    等距圆柱投影到透视投影的变换
    
    参数说明：
    - fov_h: 水平视场角（120度）
    - fov_v: 垂直视场角（90度）
    - heading: 水平旋转角度
    - pitch: 垂直旋转角度
    """
```

**变换原理**：
1. 等距圆柱投影坐标转换为球面坐标
2. 应用旋转矩阵（heading + pitch）
3. 透视投影变换
4. 输出指定尺寸的透视图像

---

## 五、功能特性

### 1. 基础功能
- **街景图像下载**：自动下载百度街景全景图像
- **透视展开**：生成左右视图的透视投影图像
- **空间关联**：建立街景点与地块的空间关联关系
- **断点续存**：支持中断后继续处理，避免重复下载

### 2. 高级拓扑功能

#### 2.1 地块-道路-街景点三元关联
- **完整关系网络**：建立地块、道路、街景点的完整关联关系
- **空间索引**：基于地块的特定方向道路与街景索引
- **遍历序列**：生成类似人类视角的有序遍历路径

#### 2.2 智能排序算法
- **道路排序**：按地块质心角度对道路进行排序
- **街景点排序**：使用相邻两点的相对角度排序，避免跨越0度线问题
- **方向控制**：支持顺时针/逆时针遍历方向，完全遵从traversal_direction参数
- **空间连续性**：确保街景点排序反映真实的空间关系，支持跨越0度线的复杂情况


#### 2.3 多地块关联分析
- **左右视图映射**：同一街景点在不同地块中的位置关系
- **交叉验证**：验证街景点与多个地块的关联正确性
- **完整编码体系**：图像命名包含完整的三元关系信息

### 3. 输出文件说明

#### 3.1 landuse_traversal_config.csv - 地块遍历配置表
```csv
landuse_id,road_id,road_sequence,streetview_id,point_sequence,filename_L,filename_R
P001,R001,1,S001,1,P001_R001_S001_L.jpg,P001_R001_S001_R.jpg
P001,R001,1,S002,2,P001_R001_S002_L.jpg,P001_R001_S002_R.jpg
```

**字段说明**：
- `landuse_id`: 地块ID
- `road_id`: 道路ID
- `road_sequence`: 道路在地块中的排序序号
- `streetview_id`: 街景点ID
- `point_sequence`: 街景点在道路中的排序序号
- `filename_L/R`: 左右视图文件名

#### 3.2 streetview_multi_landuse_mapping.csv - 多地块关联表
```csv
streetview_id,landuse_id,road_id,road_sequence,point_sequence
S001,P001,R001,1,1
S001,P002,R001,3,2
```

**功能**：记录同一街景点在不同地块中的位置关系

#### 3.3 streetview_landuse_mapping.csv - 基础关联表
```csv
streetview_id,filename,landuse_id,side,heading,capture_time,x,y,id
S001,P001_R001_S001_L.jpg,P001,L,90.5,2023-01-01 12:00:00,121.4939,31.2754,1
```

**功能**：记录街景点与地块的基础关联关系

---

## 六、如何运行

### 1. 修改配置参数
打开 `main.py`，找到如下部分，根据你的实际数据路径和需求修改参数：

```python
if __name__ == '__main__':
    main(
        landuse_gdb_path='你的地块数据.gdb',        # 地块数据路径
        landuse_layer='landuse',                    # 地块图层名
        landuse_id_col='GH_ZXC_2_I',               # 地块ID字段名
        road_layer='road_街景测试范围_0712',        # 道路图层名
        road_id_col='OBJECTID',                     # 道路ID字段名
        streetview_csv_path='example.csv',          # 街景点CSV
        baidu_ak='你的百度API Key',                 # 百度API密钥
        output_dir='output',                        # 输出目录
        zoom=2,                                     # 街景缩放级别
        save_every=50,                              # 保存间隔
        build_topology=True,                        # 是否构建拓扑关系
        traversal_direction='clockwise'             # 遍历方向 clockwise顺时针，counterclockwise逆时针
    )
```

### 2. 运行主程序
```bash
python main.py
```

### 3. 查看输出结果
- **街景图像**：`output/images/` 文件夹
- **基础关联表**：`output/streetview_landuse_mapping.csv`
- **遍历配置表**：`output/landuse_traversal_config.csv`
- **多地块关联表**：`output/streetview_multi_landuse_mapping.csv`

---

## 七、图像命名规则

### 1. 完整编码体系
```
P{地块ID}_R{道路ID}_S{街景点ID}_{L/R}.jpg

示例：
P001_R005_S123_L.jpg  # 地块001，道路005，街景点123，左视图
P001_R005_S123_R.jpg  # 地块001，道路005，街景点123，右视图
```

### 2. 信息追溯能力
从图像名称可以追溯：
- **地块信息**：P001（地块ID）
- **道路信息**：R005（道路ID）
- **街景点信息**：S123（街景点ID）
- **视角方向**：L/R（左/右视图）

---

## 八、遍历顺序说明

### 1. 组织逻辑
程序按照以下逻辑组织街景图像：

1. **按地块分组**：以地块为单位组织所有相关街景点
2. **按道路排序**：地块内的道路按空间角度排序（顺时针/逆时针）
3. **道路内排序**：每条道路内的街景点按空间顺序排列，使用相邻两点的相对角度排序
4. **生成遍历序列**：形成类似人类绕地块观察的连续序列

### 2. 应用场景
这样的组织方式便于：
- **按地块查看街景**：快速定位特定地块的所有街景
- **按道路分组管理**：分析特定道路的街景特征
- **实现连续的空间遍历体验**：模拟人类观察行为
- **支持空间分析**：为后续的空间分析提供结构化数据