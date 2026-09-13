# GIS 路口数据 → Unreal Engine 5

这套脚本把 QGIS 导出的 GeoJSON 图层转换为 UE 编辑器里的 Dynamic Mesh Actor，并能按路面多边形批量创建 Cesium Terrain 裁剪 Polygon。脚本面向编辑器内的项目生成流程，不是独立运行的 GIS 转换器。

> 本仓库包含用户授权公开的实际 GeoJSON 路口图层、当前脚本使用的坐标原点和 UE 材质资产，以及 UE 5.8 工程文件。Saved/Intermediate/缓存、个人 Developer 目录和 `CesiumIonSaaS.uasset` 未纳入；目标电脑需安装 Cesium for Unreal 插件并自行创建或配置 Cesium ion 访问。

## 流程概览

```text
QGIS 图层
  → 检查并导出 GeoJSON（EPSG:32651 或 WGS84 经纬度）
  → 每个图层保存为约定文件名，放在脚本同一目录
  → 检查 project_config.py 中的局部原点、Z、高度、材质
  → 在 UE5 Editor Python 环境运行 build_intersection.py
  → 在 Cesium World Terrain 上准备 Polygon Raster Overlay
  → 运行 build_all_terrain_clips.py，生成并绑定地形裁剪 Polygon
  → 检查生成 Actor、材质、Z 层级和地形裁剪效果
```

`build_intersection.py` 扫描脚本目录顶层的 `*.geojson`，用文件名（不带扩展名）匹配 `LAYER_CONFIG`。例如 `road_surface.geojson` 对应 `road_surface` 配置。没有配置或 `enabled=False` 的图层会跳过。

## 仓库文件

| 文件 | 用途 |
| --- | --- |
| `build_intersection.py` | 唯一的总入口；重载模块、扫描 GeoJSON、按图层与几何类型分派 Builder、输出结果日志 |
| `project_config.py` | 当前项目配置，包含局部原点、图层 Z/高度与 UE 材质路径 |
| `UnrealProject.zip` | 可编辑的完整 UE 工程副本，解压后含 `.uproject`、Config、Content/关卡和材质 |
| `coordinate_utils.py` | 经纬度 / UTM 识别与转换；减去局部原点，映射到 UE 坐标并把米转换为厘米 |
| `geojson_utils.py` | 读取 FeatureCollection、拆分 Polygon / LineString / Point、多部件和 GeometryCollection |
| `polygon_builder.py` | Polygon / MultiPolygon 转 Dynamic Mesh，按配置挤出高度、应用材质 |
| `line_builder.py` | 普通线图层的 Sweep 生成器；道路标线应走专用 Builder |
| `marking_builder.py` | 读取 `mark_type`、`width_m`、`color` 并生成水平 Ribbon 标线 |
| `point_builder.py` | Point / MultiPoint 生成定位球 |
| `build_all_terrain_clips.py` | 从路面/人行道/绿化/交通岛外环生成 Cesium Cartographic Polygon，并批量写入 Terrain Overlay |
| `check_geojson.py` | GeoJSON 基础结构检查脚本 |
| `test_coordinate_utils.py` | 不依赖 UE 的坐标转换基本测试 |

## 准备 QGIS / GeoJSON 输入

1. 在 QGIS 中整理道路面、人行道、绿化带、交通岛、标线、箭头和设施点等图层，几何本身应表达需要在 UE 生成的形状。QGIS 画布样式（颜色、线型、宽度）通常不会成为几何；需要的属性要写进要素属性表。
2. 在 QGIS 用“导出 → 另存为”导出 GeoJSON，并核对导出文件里的坐标数值。RFC 7946 GeoJSON 通常使用 WGS84 经度/纬度；本脚本也兼容以米为单位的 EPSG:32651 Easting/Northing。确保输入与配置原点处于同一地区和基准。不要只根据 QGIS 项目画布 CRS 推断导出文件的实际坐标。
3. 把文件放到本仓库脚本所在目录，命名与配置键一致，例如：
   - `road_surface.geojson`
   - `sidewalk.geojson`
   - `greenbelt.geojson`
   - `traffic_island.geojson`
   - `marking.geojson`
   - `arrow_left_3m.geojson`、`arrow_right_3m.geojson`、`arrow_straight_3m.geojson`
   - `guardrail.geojson`、`road_centerline.geojson`
   - `road_facility.geojson`
4. `marking.geojson` 的 LineString 要素应提供 `mark_type`、`width_m` 属性；可保留 `color` 属性用于生成日志。数据应使用真实数值，例如 `width_m = 0.15`，不可把 QGIS 的显示线宽误认为 GeoJSON 几何宽度。
5. 确认文件结构为 Feature、FeatureCollection 或标准 GeoJSON Geometry。GeoJSON 内的坐标与属性将随公开仓库对外可见。

本仓库目前已包含该路口的输入图层。若替换成其他数据，应检查坐标系与公开权限，并避免提交不应公开的属性字段。

## 坐标转换约定

- WGS84 经纬度会由纯 Python UTM Zone 51N 公式投影；UTM 坐标则按 EPSG:32651 米制坐标直接使用。
- 将 Easting/Northing 减去 `ORIGIN_EASTING` / `ORIGIN_NORTHING`，得到以局部原点为基准的米制坐标。
- UE 映射为 `X = local_easting × 100 cm`、`Y = -local_northing × 100 cm`、`Z = 配置的 z_cm`。也就是 GIS 北向 +Y 映射为 UE 局部 -Y。
- 原点必须是同一 UTM Zone 51N 下准确的 Easting/Northing 米值。仓库内的配置保留当前项目原点；若在别的地区使用，需替换为目标区域原点。
- 自动识别经纬度依赖坐标数值范围，不负责转换 GCJ-02、BD-09 或其他地方坐标系，也不验证 UTM 点是否确实属于 Zone 51N。跨 Zone、跨基准或较大范围数据应先用 QGIS 正确投影。

## UE5 编辑器内生成

启用项目插件：**Python Editor Script Plugin**、**Editor Scripting Utilities** 与 **Geometry Script**。打开对应 UE 项目后，在 Editor Python 环境运行：

```python
exec(open(r"<仓库绝对路径>/build_intersection.py", encoding="utf-8").read())
```

UE Python 仅在 Unreal Editor 中可用，不适用于打包游戏运行时。也可从 Unreal Editor 的 Python 脚本执行工具运行入口文件。

入口先检查文件名配置与 `enabled`，再根据 GeoJSON Geometry 分发到 Polygon、Line 或 Point Builder；`marking.geojson` 会优先进入 `marking_builder.py`，不会交给通用 Sweep 线生成器。每个 Builder 会删除同名旧 Actor 并重建，便于重复运行。生成日志会汇报成功、跳过和失败图层。

## 标线属性与虚线规则

- 连续标线：`mark_type` 不匹配虚线格式时，整条 LineString 连续生成。
- 虚线：格式为 `画线长度-间隔长度`，单位为米，且从每条 LineString 起点开始循环：
  - `1-1` = 画 1 m、空 1 m
  - `2-4` = 画 2 m、空 4 m
  - `4-6` = 画 4 m、空 6 m
- 宽度：优先读取每个 Feature 的 `width_m` 并乘 100 转成 UE cm；缺失或无效时用配置中的 `width_cm` 回退。
- `color` 目前只统计在日志中；外观由配置里挂载的 UE 材质控制。
- 标线生成器沿折线估算法线、左右各偏移宽度的一半，将相邻点连成水平面片，并用 0.2 cm 薄挤出避免纯零厚度表面。Actor 的 `z_cm` 决定整体高度。
- 虚线每条线都从起点重新计距；GeoJSON 如果把逻辑上一条线拆成多个 Feature，虚线相位也会重新开始。

## Z 层级、挤出与材质实例

`z_cm` 是 Actor 的 UE Z 位置；Polygon 的 `height_cm` 是从 Actor 基底向上的挤出高度。标线 Ribbon 也有固定 0.2 cm 的轻薄几何挤出，`thickness_cm` 参数目前只为兼容保留，不控制 Ribbon 厚度。

`project_config.py` 中道路/人行道/岛/绿化/标线高度记录的是当前场景配置，不是通用标准。按目标场景实际地表高程和道路厚度设置，避免相互穿插或产生 Z-fighting。尤其要检查配置中的路面顶面、标线 Z 与 Cesium 地表的位置关系。

批量绑定材质是在每个图层配置中填写 UE 内容浏览器资产路径（例如你项目里实际存在的 Material Instance 路径）。Builder 通过 `unreal.load_asset()` 加载并设置到 Dynamic Mesh Component 的材质槽 0。路径不存在时日志会提示并跳过；`None` 表示不自动挂材质。示例配置故意留空材质路径，避免泄露或假定用户的 UE 资产目录。

## Cesium Terrain clipping

在 UE 场景中需要有标记为 `Cesium World Terrain` 的 Terrain Actor，并在其上添加 **Cesium Polygon Raster Overlay**。先按上述步骤生成 GIS Actor，再运行 `build_all_terrain_clips.py`。

裁剪脚本对 `road_surface`、`sidewalk`、`greenbelt`、`traffic_island` GeoJSON 的 Polygon 外环创建 Cartographic Polygon，向外扩 `CLIP_MARGIN_M = 0.25` 米；它只扩张裁剪边界，不改 GIS Mesh。脚本会清理它生成的同名前缀 Polygon、写入 Overlay 的 `polygons` 列表，配置为裁掉选区内地形并刷新 Overlay。

注意：这是 Cesium 的材质/渲染裁剪，不会修改隐藏区域的碰撞；Polygon Raster Overlay 的材质层也必须与当前 Tileset 材质配置兼容。脚本按 Terrain Actor 标签和组件类名查找对象；如果你的关卡标签或 Cesium 插件版本 API 不同，需要对应调整。当前裁剪脚本只取每个 Polygon 的外环，不保留内洞。

## 换电脑继续工作

克隆或下载本仓库后，解压 `UnrealProject.zip`，进入 `UnrealProject/road-intersection/`，双击 `路口0902.uproject` 即可用 Unreal Engine 5.8 打开项目。该副本包含关卡 `Content/0904.umap`、材质实例、`Config/` 和 `.uproject` 插件启用信息。首次打开时安装兼容版本的 Cesium for Unreal；Python Editor Script、Editor Scripting Utilities 与 Geometry Script 插件也需在项目中启用。出于凭据安全考虑，Cesium ion Server 资产未随包发布；请在新电脑上重新连接 Cesium ion。GeoJSON 与 Python 总入口在仓库根目录，运行时把 `build_intersection.py` 的本地路径传给 UE Editor Python 环境即可。

如果手动迁移而不是克隆仓库，步骤如下：

1. 在 UE 中点 **Save All**，保存关卡和材质，再关闭编辑器。
2. 找到 `.uproject` 所在的工程根目录。本项目入口是 `路口0902.uproject`。
3. 复制 `.uproject`、`Content/`、`Config/`；若有项目自带的 `Source/`、`Plugins/` 或必要的 `Build/`，也一并复制。
4. 不复制 `Saved/`、`Intermediate/`、`DerivedDataCache/`、`Binaries/` 和 `cesium-request-cache.sqlite*` 缓存。把其余工程目录压缩成 ZIP，或放入 Git 仓库。
5. 新电脑安装相同的 UE 版本和 Cesium for Unreal 插件，将 ZIP 解压后双击 `.uproject`。若只迁移个别资产，可在内容浏览器选中资产后用 **Asset Actions → Migrate**，让 UE 一并带上依赖。

本仓库已经按上述原则准备了工程副本；不需要使用 **Package Project**。Package Project 是生成运行时构建包的流程，不能代替可继续编辑的工程源文件。

不要把 Cesium ion Access Token、密码或其他密钥写入公开仓库；在另一台机器上通过 UE 项目设置或本地安全配置重新登录/配置。不要上传 `Saved/`、`Intermediate/`、`DerivedDataCache/`、`Binaries/` 等可再生成的缓存目录。较大的 UE 二进制资源可用 Git LFS 或专用共享存储；公开发布前先确认素材许可与仓库容量限制。

该工程需要 Unreal Engine 5.8，启用 Cesium for Unreal；工程副本没有单独的项目级 Plugins 源码文件夹，目标电脑需另行安装 Cesium 插件。

## 验证与故障排查

在普通 Python 环境可运行基础语法与坐标检查：

```powershell
python -m compileall -q .
python -m unittest test_coordinate_utils
```

这些检查不启动 Unreal Engine，无法验证 UE 版本特定的 Geometry Script 或 Cesium Python API。实际使用时先用测试区域确认坐标轴方向、原点和高度，再检查 UE Output Log 中的材质资产路径及 Cesium Overlay 刷新结果。

常见问题：

- Actor 生成但位置远离路口：原点/CRS/UTM Zone 不一致，或误把 GCJ-02 坐标当成 WGS84。
- 材质未挂载：确认 `/Game/...` 资产路径拼写与实例资产存在。
- 标线成连续线：检查 `mark_type` 是否严格符合 `1-1` 这类格式，是否误走 `line_builder.py`。
- 虚线长度或宽度不对：检查源数据单位为米，并检查 `width_m` 数值。
- 地形没裁掉：检查 Cesium Polygon Raster Overlay 是否挂在目标 Terrain，名称/属性与当前 Cesium 插件版本是否一致。

## 官方参考

- [QGIS：从现有图层另存并重投影](https://docs.qgis.org/3.44/en/docs/user_manual/managing_data_source/create_layers.html)
- [QGIS：GeoJSON 与支持的数据格式](https://docs.qgis.org/testing/en/docs/user_manual/managing_data_source/supported_data.html)
- [Unreal Engine：在编辑器中使用 Python 脚本](https://dev.epicgames.com/documentation/unreal-engine/scripting-the-unreal-editor-using-python)
- [Unreal Engine：Geometry Script 用户指南](https://dev.epicgames.com/documentation/en-us/unreal-engine/geometry-script-users-guide)
- [Cesium for Unreal：使用 Cartographic Polygon 裁剪 Tileset](https://cesium.com/learn/unreal/unreal-clipping/)
- [Cesium for Unreal：Tileset 材质与 Overlay](https://cesium.com/learn/unreal/unreal-edit-materials/)
