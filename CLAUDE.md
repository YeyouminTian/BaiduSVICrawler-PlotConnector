# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Maintenance Policy

**重要**：当项目发生任何更新时，必须同步更新此 CLAUDE.md 文件，包括但不限于：
- 新增或修改核心功能
- 算法改进或优化
- 架构变更
- 依赖包更新
- 配置参数调整
- 修复重要的bug或问题
- 新增工具脚本或模块

确保此文件始终反映项目的最新状态，以便未来的 Claude Code 实例能够准确理解项目架构和工作流程。

## Project Overview

百度街景图爬取、展开、获取各视图与地块关联分析工具。该工具实现街景图像下载、透视展开、空间关联分析和拓扑关系构建的完整工作流。

## Project Overview

百度街景图爬取、展开、获取各视图与地块关联分析工具。该工具实现街景图像下载、透视展开、空间关联分析和拓扑关系构建的完整工作流。

## Code Structure

项目采用**模块化架构**，代码组织清晰：

```
├── main.py                    # 主程序入口，整合所有模块
├── geometry_utils.py          # 几何与投影工具
├── landuse_utils.py           # 地块数据读取与处理
├── streetview_utils.py        # 街景数据读取、API调用与下载
├── image_utils.py             # 图像处理（全景展开）
├── spatial_analysis.py        # 空间分析与左右判断算法
├── topology_utils.py          # 拓扑关系构建与排序
├── remap_new_landuse.py       # 地块更新后的重新映射工具
└── fix_image_names.py         # 图像命名修复工具（旧版本）
```

**注意**：`main_merged.py` 是原始的单文件版本，现已重构为模块化的 `main.py`，功能完全一致，推荐使用模块化版本。

## Commands

### 环境设置
```bash
pip install -r requirements.txt
```

### 运行主程序
```bash
python main.py
```

### 地块更新后重新映射
当地块数据更新时，使用 `remap_new_landuse.py` 重新映射街景数据：
```bash
python remap_new_landuse.py
```

**使用场景**：
- 地块边界调整
- 地块ID变更
- 新增或删除地块

**优势**：无需重新下载街景图像，复用已有数据。

## Architecture

### 模块化设计

项目采用模块化架构，各模块职责清晰：

1. **geometry_utils.py** - 几何与投影工具
   - `get_utm_crs()`: 根据经纬度自动计算UTM投影
   - `project_gdf()`: GeoDataFrame投影转换

2. **landuse_utils.py** - 地块数据处理
   - `read_landuse_gdb()`: 读取GDB地块数据，自动计算质心

3. **streetview_utils.py** - 街景数据处理
   - `read_streetview_points()`: 读取街景点CSV
   - `wgs84_to_bd09mc()`: WGS84转百度墨卡托
   - `get_streetview_metadata()`: 获取街景元数据
   - `download_panorama_image()`: 下载全景图（支持重试）

4. **image_utils.py** - 图像处理
   - `equirectangular_to_perspective()`: 全景图转透视图

5. **spatial_analysis.py** - 空间分析核心算法
   - **局部切线法**（推荐）：`determine_side_robust()`, `get_tangent_at_distance()`
   - **纯Heading法**（通用）：`judge_left_right()`
   - 统一接口：`determine_side_strict()`

6. **topology_utils.py** - 拓扑关系处理
   - `build_landuse_topology()`: 构建地块拓扑
   - `generate_final_config()`: 生成遍历配置表
   - `execute_rename()`: 执行图像重命名

7. **main.py** - 主程序
   - 整合所有模块，提供完整的处理流程

### 核心工作流程

1. **数据读取阶段**
   - 读取地块数据（GDB格式）→ `read_landuse_gdb()`
   - 读取道路数据（GDB格式）→ `read_road_gdb()`
   - 读取街景点数据（CSV格式）→ `read_streetview_points()`

2. **坐标系统**
   - 输入：WGS84（经纬度）
   - 百度API：BD09MC（百度墨卡托）
   - 空间分析：UTM投影（自动选择合适的带号）
   - `project_gdf()`: 自动计算UTM投影并转换

3. **街景处理流程**
   - 坐标转换：`wgs84_to_bd09mc()` (WGS84 → BD09MC)
   - 获取元数据：`get_streetview_metadata()` (获取SID和Heading)
   - 下载全景图：`download_panorama_image()` (支持zoom 1-4)
   - 透视展开：`equirectangular_to_perspective()` (生成左右视图)

4. **空间关联算法**

   **方法A：局部切线法（推荐，main_merged.py独有）**
   - 使用道路几何的局部切线方向
   - 将地块质心投影到道路，获取特定位置的切线
   - 自动判断道路流向（同向/反向）
   - 适用场景：弯道、复杂道路几何
   - 核心函数：`determine_side_robust()`, `get_tangent_at_distance()`

   **方法B：纯Heading法（通用）**
   - 使用街景车的Heading方向作为道路方向
   - 不需要道路几何数据
   - 核心函数：`judge_left_right()` (spatial_analysis.py)

   **左右判断原理（叉积法）**：
   ```python
   cross = road_vec[0] * obj_vec[1] - road_vec[1] * obj_vec[0]
   # cross > 0 → 左侧 (L)
   # cross < 0 → 右侧 (R)
   ```

5. **拓扑关系构建**
   - 按地块组织街景点：`build_landuse_topology()`
   - 道路排序：基于地块质心的角度（顺时针/逆时针）
   - 街景点排序：使用相对角度避免跨越0度线问题
   - 生成配置表：`generate_final_config()`

### 图像命名规则

**最终命名格式**：`P{地块ID}_R{道路ID}_S{街景点ID}_{L/R}.jpg`

示例：
- `P001_R005_S123_L.jpg`: 地块001，道路005，街景点123，左视图
- `P001_R005_S123_R.jpg`: 地块001，道路005，街景点123，右视图

**重要**：左右图对应不同的地块，左图对应左侧地块，右图对应右侧地块。

### 关键数据结构

**街景点-道路映射**（sv_road_map）:
```python
{
    'original_id': id_val,
    'x': x,
    'y': y,
    'road_id': nearest_rid,
    'road_distance': min_d
}
```

**拓扑结构**（topology_results）:
```python
{
    'landuse_id': lid,
    'road_sequence': [
        {
            'road_id': rid,
            'sequence': seq_idx,
            'streetview_points': [
                {
                    'streetview_id': sid,
                    'sequence': pt_seq,
                    'x': x,
                    'y': y
                }
            ]
        }
    ]
}
```

### 输出文件

1. **streetview_landuse_mapping.csv**: 基础关联表
   - 字段：id, streetview_id, filename, landuse_id, side, x, y, heading, capture_time, distance

2. **landuse_traversal_config.csv**: 地块遍历配置表
   - 字段：landuse_id, road_id, road_sequence, streetview_id, streetview_sequence, side, filename

3. **images/**: 街景图像目录
   - 临时命名：`{id}_L.jpg`, `{id}_R.jpg`
   - 最终命名：`P{landuse_id}_R{road_id}_S{streetview_id}_{side}.jpg`

## Configuration

主程序参数（main函数）：

**必需参数**：
- `landuse_gdb_path`: 地块数据路径（GDB格式）
- `landuse_layer`: 地块图层名
- `landuse_id_col`: 地块ID字段名
- `road_layer`: 道路图层名
- `road_id_col`: 道路ID字段名
- `streetview_csv_path`: 街景点CSV路径
- `baidu_ak`: 百度地图API密钥

**可选参数**：
- `output_dir`: 输出目录（默认：'output'）
- `zoom`: 街景缩放级别（默认：3，范围1-4）
- `save_every`: 保存间隔（默认：50）
- `build_topology`: 是否构建拓扑（默认：True）
- `traversal_direction`: 遍历方向（'clockwise' 或 'counterclockwise'）
- `distance_threshold`: 距离阈值（默认：100米）
- `search_buffer`: 搜索缓冲区（默认：500米）
- `use_local_tangent`: 使用局部切线法（默认：True，仅main_merged.py）
- `verbose_matching`: 详细匹配日志（默认：False）

## Algorithm Details

### 局部切线法（Local Tangent Method）

**核心思想**：使用道路几何在特定位置的切线方向，而非全局的Heading方向

**算法步骤**：
1. 找到街景点最近的道路
2. 判断道路几何方向与车行方向的关系（同向/反向）
3. 将地块质心投影到道路上，获取投影距离
4. 在投影位置获取道路切线向量
5. 根据道路方向修正切线向量
6. 计算切线向量与地块向量的叉积，判断左右

**优势**：
- 解决弯道问题：每个位置使用局部方向
- 零距离稳健：使用投影点而非街景点本身
- 自动方向修正：道路几何可能反向，自动检测并修正

### 拓扑排序算法

**道路排序**：
- 计算地块质心到各道路质心的角度（正北为0度，顺时针）
- 按指定方向（顺时针/逆时针）排序

**街景点排序**：
- 计算街景点相对于地块质心的角度
- 检测相邻点角度差，处理跨越0度线的情况
- 确保空间连续性

## Development Notes

### 模块化开发规范

**添加新功能**：
1. 确定功能所属模块（如新增空间分析算法 → spatial_analysis.py）
2. 在对应模块中实现功能函数
3. 在 main.py 中调用新函数
4. 更新 CLAUDE.md 文档

**修改现有功能**：
1. 定位功能所在模块
2. 修改模块中的函数实现
3. 确保接口兼容性（参数和返回值）
4. 测试 main.py 是否正常工作
5. 更新 CLAUDE.md 文档

**模块依赖关系**：
```
main.py
  ├── geometry_utils.py
  ├── landuse_utils.py (依赖 geometry_utils)
  ├── streetview_utils.py
  ├── image_utils.py
  ├── spatial_analysis.py
  └── topology_utils.py
```

### 断点续存
- 程序自动检测已处理的街景点（通过mapping CSV）
- 跳过已处理的点，继续未完成的任务

### 坐标系统注意事项
- 地块质心计算使用投影坐标系（UTM），再转回WGS84
- 空间分析在投影坐标系中进行（米制单位）
- 百度API使用BD09MC坐标系

### 性能优化
- 使用空间索引（sindex）加速查询
- 批量处理街景点-道路映射
- 定期保存进度（save_every参数）

### 常见问题

**问题1**：某些街景点未匹配到道路
- 检查 `road_search_buffer` 参数（默认200米）
- 输出警告数量，评估影响

**问题2**：某些街景点未匹配到地块
- 检查 `distance_threshold` 和 `search_buffer` 参数
- 可能是街景点距离地块太远

**问题3**：图像命名不正确
- 运行 `fix_image_names.py` 进行修复（仅适用于旧版本）
- 新版本 main.py 已集成重命名逻辑，直接生成正确命名

### 版本历史

**当前版本（模块化）**：
- `main.py`: 模块化架构，调用各工具模块
- 更易维护、测试和扩展
- 所有改进功能已迁移到对应模块

**历史版本**：
- `main_merged.py`: 单文件版本（已弃用，保留作参考）
- 旧 `main.py`: 早期模块化版本（已被新版本替换）
