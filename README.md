# 百度街景图爬取、展开、获取各视图与地块关联分析工具

## 核心功能

- **街景图像爬取**：自动下载百度街景全景图像
- **四种视图方向**：左视图(L)、右视图(R)、前视图(F)、后视图(B)
- **灵活的爬取模式**：可单独爬取地块视图、道路视图或全部视图
- **空间关联分析**：建立街景点与地块的空间关联关系
- **智能拓扑构建**：生成有序的地块-道路-街景点遍历序列

## 视图说明

| 视图 | 方向 | 关联对象 | 用途 |
|------|------|----------|------|
| **左视图 (L)** | 垂直于道路，指向左侧 | 地块 | 地块分析、用地识别 |
| **右视图 (R)** | 垂直于道路，指向右侧 | 地块 | 地块分析、用地识别 |
| **前视图 (F)** | 沿道路前进方向 | 道路 | 道路景观、设施分析 |
| **后视图 (B)** | 沿道路后退方向 | 道路 | 道路景观、设施分析 |

**三种爬取模式**：
- `block_only`: 仅爬取左右视图（地块关联）
- `street_only`: 仅爬取前后视图（道路景观）
- `all`: 爬取所有视图（完整数据）

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

### 3. 街景点数据

**方式一：从GDB读取（推荐）**
- 直接使用GDB文件中的点要素图层
- 无需单独导出CSV，简化数据准备流程
- 自动提取WGS84坐标
- 示例：`example.gdb` 包含 `svi_point` 图层

**方式二：从CSV读取**
- CSV文件需包含街景点的经纬度坐标，推荐字段：`id,X,Y`，坐标系为WGS84
- 示例内容：
  ```
  id,X,Y
  1,121.4939382,31.27539693
  2,121.4941003,31.27606852
  ...
  ```
- 放在项目根目录下，命名如 `example.csv`

**推荐使用GDB方式**，更加便捷高效。

### 4. 百度API Key
- 需注册百度开发者账号，获取"百度地图API"的 `ak`（API Key）
- [百度API控制台](https://lbsyun.baidu.com/apiconsole/key)

**配置方式**：
1. 复制项目根目录下的 `.env.example` 文件为 `.env`
   ```bash
   cp .env.example .env
   ```
2. 编辑 `.env` 文件，填入你的 API Key：
   ```
   BAIDU_AK=your_baidu_api_key_here
   ```
3. 程序会自动从 `.env` 文件读取 API Key

**注意**：`.env` 文件已添加到 `.gitignore`，不会被提交到 git 仓库，保护你的 API Key 安全。

---

## 三、文件结构说明

### 模块化架构

```
项目目录/
│
├─ main.py                           # 模块化主程序
│
├─ geometry_utils.py                 # 几何与投影工具
├─ block_utils.py                    # 地块数据读取模块
├─ streetview_utils.py               # 街景API与点读取模块
├─ image_utils.py                    # 图像处理模块
├─ spatial_analysis.py               # 空间分析与左右判别模块（局部切线法）
├─ topology_utils.py                 # 拓扑关系处理模块
│
├─ remap_new_block.py                # 地块更新后的重新映射工具
│
├─ example.gdb                       # 示例地理数据库 ⭐
│   ├─ block                         # 地块图层（Block_ID）
│   ├─ road                          # 道路图层（Road_ID）
│   └─ svi_point                     # 街景点图层（Svi_ID）
├─ example.csv                       # 示例街景点数据（CSV格式）
├─ requirements.txt                 # 依赖包列表
├─ README.md                        # 项目文档
│
└─ output/                          # 输出目录（自动生成）
    ├─ images/
    │   ├─ block/                  # 地块相关视图（左右）
    │   │   ├─ P001_R005_S123_L.jpg
    │   │   └─ P001_R005_S123_R.jpg
    │   └─ street/                   # 道路相关视图（前后）
    │       ├─ R005_S123_F.jpg
    │       └─ R005_S123_B.jpg
    ├─ streetview_block_mapping.csv    # 地块关联表（左右视图）
    ├─ streetview_road_views.csv          # 道路视图记录表（前后视图）
    ├─ block_traversal_config.csv       # 地块遍历配置表
    └─ streetview_multi_block_mapping.csv  # 多地块关联表
```

### 模块职责

- **geometry_utils.py**: UTM投影计算与坐标转换
- **block_utils.py**: 读取GDB地块数据，计算质心
- **streetview_utils.py**: 百度API调用、坐标转换、街景下载
- **image_utils.py**: 全景图透视展开
- **spatial_analysis.py**: 空间关联算法（局部切线法 + 纯Heading法）
- **topology_utils.py**: 拓扑关系构建、排序与图像重命名

---

## 四、核心算法原理

### 1. 空间左右判别

程序提供两种左右判别算法：

| 算法 | 适用场景 | 说明 |
|------|----------|------|
| **局部切线法**（默认） | 弯道、复杂道路 | 使用道路几何的局部切线方向，适合高精度需求 |
| **纯Heading法** | 直线道路、简单场景 | 使用街景拍摄方向，计算简单快速 |

**切换方式**：设置 `use_local_tangent=True/False`

### 2. 拓扑关系

- 按地块组织街景点，按道路分组
- 道路和街景点按空间角度排序，形成连续的遍历序列
- 支持顺时针/逆时针遍历方向

### 3. 图像处理

- 百度街景全景图下载，支持缩放级别1-4
- 全景图展开为四个方向的透视视图（L/R/F/B）
- 自动坐标系转换（WGS84 → 百度墨卡托）

---

## 五、功能特性

### 1. 基础功能
- **街景图像下载**：自动下载百度街景全景图像
- **四种视图展开**：生成左、右、前、后四个方向的透视投影图像
- **灵活爬取模式**：
  - `block_only`: 仅左右视图，用于地块分析
  - `street_only`: 仅前后视图，用于道路景观
  - `all`: 全部视图，完整数据采集
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

#### 3.1 目录结构
```
output/
├── images/
│   ├── block/              # 地块相关视图（左右）
│   │   ├── P001_R005_S123_L.jpg
│   │   └── P001_R005_S123_R.jpg
│   └── street/               # 道路相关视图（前后）
│       ├── R005_S123_F.jpg
│       └── R005_S123_B.jpg
├── streetview_block_mapping.csv    # 地块关联表（左右视图）
├── streetview_road_views.csv          # 道路视图记录表（前后视图）
├── block_traversal_config.csv       # 地块遍历配置表
└── streetview_multi_block_mapping.csv  # 多地块关联表
```

#### 3.2 streetview_block_mapping.csv - 地块关联表（左右视图）
```csv
streetview_id,filename,block_id,side,heading,capture_time,x,y,id
S001,P001_R001_S001_L.jpg,P001,L,90.5,2023-01-01 12:00:00,121.4939,31.2754,1
S001,P002_R001_S001_R.jpg,P002,R,90.5,2023-01-01 12:00:00,121.4939,31.2754,1
```

**功能**：记录左右视图与地块的关联关系

#### 3.3 streetview_road_views.csv - 道路视图记录表（前后视图）
```csv
road_id,streetview_id,filename,view_type,heading,x,y,capture_time
005,123,R005_S123_F.jpg,F,90.5,121.4939,31.2754,2024-01-01
005,123,R005_S123_B.jpg,B,270.5,121.4939,31.2754,2024-01-01
```

**功能**：记录前后视图的道路关联信息

#### 3.4 block_traversal_config.csv - 地块遍历配置表
```csv
block_id,road_id,road_sequence,streetview_id,point_sequence,filename_L,filename_R
P001,R001,1,S001,1,P001_R001_S001_L.jpg,P001_R001_S001_R.jpg
P001,R001,1,S002,2,P001_R001_S002_L.jpg,P001_R001_S002_R.jpg
```

**字段说明**：
- `block_id`: 地块ID
- `road_id`: 道路ID
- `road_sequence`: 道路在地块中的排序序号
- `streetview_id`: 街景点ID
- `point_sequence`: 街景点在道路中的排序序号
- `filename_L/R`: 左右视图文件名

#### 3.5 streetview_multi_block_mapping.csv - 多地块关联表
```csv
streetview_id,block_id,road_id,road_sequence,point_sequence
S001,P001,R001,1,1
S001,P002,R001,3,2
```

**功能**：记录同一街景点在不同地块中的位置关系

---

## 六、如何运行

### 1. 修改配置参数

打开 `main.py`，找到如下部分，根据你的实际数据路径和需求修改参数：

#### 方式一：使用GDB街景点图层（推荐）

```python
if __name__ == '__main__':
    main(
        block_gdb_path='example.gdb',              # GDB数据路径
        block_layer='block',                       # 地块图层名
        block_id_col='Block_ID',                   # 地块ID字段名
        road_layer='road',                         # 道路图层名
        road_id_col='Road_ID',                     # 道路ID字段名
        streetview_gdb_layer='svi_point',          # 街景点图层名
        streetview_id_col='Svi_ID',                # 街景点ID字段名
        baidu_ak='你的百度API Key',                 # 百度API密钥
        output_dir='output',                       # 输出目录
        zoom=3,                                    # 街景缩放级别
        save_every=50,                             # 保存间隔
        build_topology=True,                       # 是否构建拓扑关系
        traversal_direction='clockwise',           # 遍历方向
        view_mode='all'                            # 视图模式
    )
```

#### 方式二：使用CSV街景点文件

```python
if __name__ == '__main__':
    main(
        block_gdb_path='你的地块数据.gdb',          # GDB数据路径
        block_layer='block',                       # 地块图层名
        block_id_col='Block_ID',                   # 地块ID字段名
        road_layer='road',                         # 道路图层名
        road_id_col='Road_ID',                     # 道路ID字段名
        streetview_csv_path='example.csv',         # 街景点CSV文件
        baidu_ak='你的百度API Key',                 # 百度API密钥
        output_dir='output',                       # 输出目录
        zoom=3,                                    # 街景缩放级别
        save_every=50,                             # 保存间隔
        build_topology=True,                       # 是否构建拓扑关系
        traversal_direction='clockwise',           # 遍历方向
        view_mode='all'                            # 视图模式
    )
```

**参数说明**：
- `streetview_gdb_layer` 和 `streetview_csv_path` **二选一**
- GDB方式：街景点与地块、道路在同一GDB中
- CSV方式：适合已有CSV街景点数据的情况

#### 参数完整说明表

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `block_gdb_path` | str | 必填 | 地块GDB文件路径 |
| `block_layer` | str | 必填 | 地块图层名称 |
| `block_id_col` | str | 必填 | 地块ID字段名 |
| `road_layer` | str | 必填 | 道路图层名称 |
| `road_id_col` | str | 必填 | 道路ID字段名 |
| `streetview_gdb_layer` | str | 可选 | 街景点GDB图层名（与CSV二选一） |
| `streetview_id_col` | str | 必填 | 街景点ID字段名 |
| `streetview_csv_path` | str | 可选 | 街景点CSV文件路径（与GDB二选一） |
| `baidu_ak` | str | 必填 | 百度地图API密钥 |
| `output_dir` | str | 'output' | 输出目录 |
| `zoom` | int | 3 | 街景缩放级别(1-4)，值越大越清晰 |
| `save_every` | int | 50 | 每处理N个点保存一次进度 |
| `build_topology` | bool | True | 是否构建拓扑关系 |
| `traversal_direction` | str | 'clockwise' | 遍历方向：'clockwise'(顺时针) 或 'counterclockwise'(逆时针) |
| `view_mode` | str | 'all' | 视图模式：'block_only'(仅左右)、'street_only'(仅前后)、'all'(全部) |
| `test_limit` | int | None | 测试模式，指定只处理前N个点，调试用 |
| `distance_threshold` | float | 100 | 街景点与地块的最大距离阈值(米) |
| `search_buffer` | float | 500 | 街景点搜索道路的缓冲区半径(米) |
| `use_local_tangent` | bool | True | 是否使用局部切线法(推荐)，False则使用纯Heading法 |
| `verbose_matching` | bool | False | 是否输出详细的匹配日志 |

**view_mode 参数说明**：
- `'block_only'`: 仅爬取左右视图，用于地块分析
- `'street_only'`: 仅爬取前后视图，用于道路景观分析
- `'all'`: 爬取所有视图，获取完整数据

### 2. 运行主程序
```bash
python main.py
```

### 3. 查看输出结果
- **地块视图图像**：`output/images/block/` 文件夹（左右视图）
- **道路视图图像**：`output/images/street/` 文件夹（前后视图）
- **地块关联表**：`output/streetview_block_mapping.csv`（左右视图）
- **道路视图记录表**：`output/streetview_road_views.csv`（前后视图）
- **遍历配置表**：`output/block_traversal_config.csv`
- **多地块关联表**：`output/streetview_multi_block_mapping.csv`

### 4. 地块数据更新后的重新映射

当你的地块数据发生更新（边界调整、ID变更等），无需重新爬取街景图像：

```bash
python remap_new_block.py
```

**修改配置**：
```python
main(
    new_block_path='新地块.gdb',      # 新地块数据
    new_block_layer='new_blocks',
    old_output_dir='svi_251206',        # 旧输出目录
    new_output_dir='svi_251207',        # 新输出目录
    use_local_tangent=True
)
```

**优势**：
- 复用已有街景图像，节省时间
- 使用相同的匹配算法，保证一致性
- 自动生成新的拓扑关系和配置表

---

## 七、图像命名规则

### 1. 左右视图（地块关联）
```
P{地块ID}_R{道路ID}_S{街景点ID}_{L/R}.jpg

示例：
P001_R005_S123_L.jpg  # 地块001，道路005，街景点123，左视图
P001_R005_S123_R.jpg  # 地块001，道路005，街景点123，右视图
```

### 2. 前后视图（道路视图）
```
R{道路ID}_S{街景点ID}_{F/B}.jpg

示例：
R005_S123_F.jpg  # 道路005，街景点123，前视图
R005_S123_B.jpg  # 道路005，街景点123，后视图
```

### 3. 信息追溯能力
从图像名称可以追溯：

**左右视图**：
- **地块信息**：P001（地块ID）
- **道路信息**：R005（道路ID）
- **街景点信息**：S123（街景点ID）
- **视角方向**：L/R（左/右视图）

**前后视图**：
- **道路信息**：R005（道路ID）
- **街景点信息**：S123（街景点ID）
- **视角方向**：F/B（前/后视图）

### 4. 左右图对应关系
**重要**：每个街景点的左图和右图对应不同的地块：
- **左图**：对应街景点左侧的地块
- **右图**：对应街景点右侧的地块
- **前后图**：不关联地块，仅表示道路方向
- **唯一性**：命名确保了一一对应关系

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