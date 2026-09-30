import unreal
import json
import math
import os


# ============================================================
# 1. 项目配置
# ============================================================

# 我们之前生成道路时使用的 EPSG:32651 局部原点
ORIGIN_EASTING = 345478.104486
ORIGIN_NORTHING = 3170937.085305

# 红绿灯蓝图
TRAFFIC_LIGHT_BP = "/Game/assets/信号灯/BP_TrafficLight_01"

# 你刚才手动摆好的标准灯：
# FAC-003，direction=南，Yaw≈20°
SOUTH_YAW = 20.0

# 杆底目前和你手动样板一致
Z_CM = 20.0

# 自动生成Actor名称前缀
AUTO_PREFIX = "AUTO_TL_"

# 如果已经有手工放置的红绿灯，
# 与目标点相距小于这个距离就不重复生成
EXISTING_TOLERANCE_CM = 100.0


# ============================================================
# 2. 自动寻找 road_facility.geojson
# ============================================================

def find_geojson():
    candidates = []

    # 脚本同目录
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        p = os.path.join(script_dir, "road_facility.geojson")
        if os.path.isfile(p):
            candidates.append(p)
    except Exception:
        pass

    # UE工程目录
    try:
        project_dir = unreal.Paths.convert_relative_path_to_full(
            unreal.Paths.project_dir()
        )

        for root, dirs, files in os.walk(project_dir):
            if "road_facility.geojson" in files:
                candidates.append(
                    os.path.join(root, "road_facility.geojson")
                )
    except Exception:
        pass

    if not candidates:
        raise RuntimeError(
            "没有找到 road_facility.geojson。\n"
            "请把它放到脚本同目录，或者 UE 工程目录下面。"
        )

    # 如果存在多个同名文件，使用最近修改的一个
    candidates = list(set(candidates))
    candidates.sort(
        key=lambda x: os.path.getmtime(x),
        reverse=True
    )

    return candidates[0]


# ============================================================
# 3. WGS84 经纬度 → EPSG:32651
#
# 不依赖 pyproj。
# 直接在UE Python里计算 UTM Zone 51N。
# ============================================================

def lonlat_to_utm51(lon, lat):
    # WGS84
    a = 6378137.0
    f = 1.0 / 298.257223563

    e2 = f * (2.0 - f)
    ep2 = e2 / (1.0 - e2)

    k0 = 0.9996

    # UTM Zone 51 中央经线 = 123°
    lon0 = math.radians(123.0)

    phi = math.radians(lat)
    lam = math.radians(lon)

    sin_phi = math.sin(phi)
    cos_phi = math.cos(phi)
    tan_phi = math.tan(phi)

    n = a / math.sqrt(
        1.0 - e2 * sin_phi * sin_phi
    )

    t = tan_phi * tan_phi
    c = ep2 * cos_phi * cos_phi

    aa = cos_phi * (lam - lon0)

    m = a * (
        (1.0
         - e2 / 4.0
         - 3.0 * e2 ** 2 / 64.0
         - 5.0 * e2 ** 3 / 256.0) * phi

        - (3.0 * e2 / 8.0
           + 3.0 * e2 ** 2 / 32.0
           + 45.0 * e2 ** 3 / 1024.0)
        * math.sin(2.0 * phi)

        + (15.0 * e2 ** 2 / 256.0
           + 45.0 * e2 ** 3 / 1024.0)
        * math.sin(4.0 * phi)

        - (35.0 * e2 ** 3 / 3072.0)
        * math.sin(6.0 * phi)
    )

    easting = (
        500000.0
        + k0 * n * (
            aa
            + (1.0 - t + c) * aa ** 3 / 6.0
            + (
                5.0
                - 18.0 * t
                + t * t
                + 72.0 * c
                - 58.0 * ep2
            ) * aa ** 5 / 120.0
        )
    )

    northing = (
        k0 * (
            m
            + n * tan_phi * (
                aa ** 2 / 2.0
                + (
                    5.0
                    - t
                    + 9.0 * c
                    + 4.0 * c * c
                ) * aa ** 4 / 24.0
                + (
                    61.0
                    - 58.0 * t
                    + t * t
                    + 600.0 * c
                    - 330.0 * ep2
                ) * aa ** 6 / 720.0
            )
        )
    )

    return easting, northing


# ============================================================
# 4. 经纬度 → 当前UE路口局部坐标
# ============================================================

def lonlat_to_ue(lon, lat):
    easting, northing = lonlat_to_utm51(lon, lat)

    local_x_m = easting - ORIGIN_EASTING
    local_y_m = northing - ORIGIN_NORTHING

    # 我们之前已经确定：
    #
    # QGIS:
    # +X = 东
    # +Y = 北
    #
    # UE:
    # +X = 东
    # +Y = 南
    #
    ue_x = local_x_m * 100.0
    ue_y = -local_y_m * 100.0

    return ue_x, ue_y


# ============================================================
# 5. direction → 当前路口Yaw
#
# FAC-003 南向已由你手工校准为20°
# 其它方向以90°递增。
# ============================================================

def infer_direction_from_position(x, y):
    """
    direction为空时：
    根据设施相对于路口原点的位置推断灯面朝外方向。
    """

    if abs(x) > abs(y):

        if x >= 0:
            return "东"
        else:
            return "西"

    else:

        if y >= 0:
            return "南"
        else:
            return "北"


def normalize_direction(direction, x, y):

    if direction is None:
        return infer_direction_from_position(x, y)

    direction = str(direction).strip()

    if direction == "":
        return infer_direction_from_position(x, y)

    # 东西表示同一点有东西两个方向。
    # 当前BP只有一个灯头，所以第一版按点位所在侧选择外向灯面。
    if direction == "东西":

        if x >= 0:
            return "东"
        else:
            return "西"

    # 南北同理
    if direction == "南北":

        if y >= 0:
            return "南"
        else:
            return "北"

    return direction


def direction_to_yaw(direction):

    yaw_map = {
        "南": SOUTH_YAW,
        "北": SOUTH_YAW + 180.0,

        "东": SOUTH_YAW + 90.0,
        "西": SOUTH_YAW - 90.0,
    }

    return yaw_map.get(direction, SOUTH_YAW)


# ============================================================
# 6. UE辅助函数
# ============================================================

def is_traffic_light_actor(actor):

    try:
        class_name = actor.get_class().get_name()

        return class_name == "BP_TrafficLight_01_C"

    except Exception:
        return False


def actor_exists_near(actors, target_location):

    for actor in actors:

        if not is_traffic_light_actor(actor):
            continue

        # 自动Actor会先被删除，
        # 所以这里主要检测你手工摆的那一根样板灯
        loc = actor.get_actor_location()

        dx = loc.x - target_location.x
        dy = loc.y - target_location.y

        distance = math.sqrt(
            dx * dx + dy * dy
        )

        if distance <= EXISTING_TOLERANCE_CM:
            return actor

    return None


# ============================================================
# 7. 主程序
# ============================================================

def main():

    unreal.log(
        "========== 自动部署红绿灯开始 =========="
    )

    # --------------------------------------------------------
    # 找GeoJSON
    # --------------------------------------------------------

    geojson_path = find_geojson()

    unreal.log(
        "使用GeoJSON：{}".format(geojson_path)
    )

    with open(
        geojson_path,
        "r",
        encoding="utf-8"
    ) as f:

        data = json.load(f)

    # --------------------------------------------------------
    # 加载红绿灯蓝图
    # --------------------------------------------------------

    traffic_light_class = (
        unreal.EditorAssetLibrary.load_blueprint_class(
            TRAFFIC_LIGHT_BP
        )
    )

    if not traffic_light_class:

        raise RuntimeError(
            "无法加载蓝图：{}".format(
                TRAFFIC_LIGHT_BP
            )
        )

    actor_subsystem = unreal.get_editor_subsystem(
        unreal.EditorActorSubsystem
    )

    # --------------------------------------------------------
    # 删除上一次脚本生成的红绿灯
    #
    # 不删除你手工摆的BP_TrafficLight_01。
    # --------------------------------------------------------

    all_actors = (
        actor_subsystem.get_all_level_actors()
    )

    delete_count = 0

    for actor in list(all_actors):

        try:
            label = actor.get_actor_label()

            if label.startswith(AUTO_PREFIX):

                actor_subsystem.destroy_actor(actor)

                delete_count += 1

        except Exception:
            pass

    unreal.log(
        "删除旧自动红绿灯：{} 个".format(
            delete_count
        )
    )

    # 删除以后重新获取一次
    existing_actors = (
        actor_subsystem.get_all_level_actors()
    )

    # --------------------------------------------------------
    # 开始生成
    # --------------------------------------------------------

    spawned = []
    skipped_existing = []
    skipped_other_type = 0

    with unreal.ScopedEditorTransaction(
        "Auto Spawn Traffic Lights"
    ):

        for feature in data.get(
            "features",
            []
        ):

            props = feature.get(
                "properties",
                {}
            )

            facility_type = props.get(
                "type"
            )

            # 第一版只处理红绿灯
            if facility_type != "红绿灯":

                skipped_other_type += 1
                continue

            facility_id = props.get(
                "id",
                "UNKNOWN"
            )

            raw_direction = props.get(
                "direction"
            )

            geometry = feature.get(
                "geometry",
                {}
            )

            if geometry.get("type") != "Point":

                unreal.log_warning(
                    "{} 不是Point，跳过".format(
                        facility_id
                    )
                )

                continue

            coords = geometry.get(
                "coordinates"
            )

            if not coords or len(coords) < 2:

                unreal.log_warning(
                    "{} 坐标无效，跳过".format(
                        facility_id
                    )
                )

                continue

            lon = float(coords[0])
            lat = float(coords[1])

            # 经纬度 → UE局部坐标
            x, y = lonlat_to_ue(
                lon,
                lat
            )

            location = unreal.Vector(
                x,
                y,
                Z_CM
            )

            # -----------------------------------------------
            # 检查附近是否已有手工放置的标准灯
            # -----------------------------------------------

            existing = actor_exists_near(
                existing_actors,
                location
            )

            if existing:

                skipped_existing.append(
                    (
                        facility_id,
                        existing.get_actor_label()
                    )
                )

                unreal.log(
                    "{} 附近已有红绿灯 {}，不重复生成".format(
                        facility_id,
                        existing.get_actor_label()
                    )
                )

                continue

            # -----------------------------------------------
            # 方向
            # -----------------------------------------------

            direction = normalize_direction(
                raw_direction,
                x,
                y
            )

            yaw = direction_to_yaw(
                direction
            )

            rotation = unreal.Rotator(
                pitch=0.0,
                yaw=yaw,
                roll=0.0
            )

            # -----------------------------------------------
            # Spawn
            # -----------------------------------------------

            actor = actor_subsystem.spawn_actor_from_class(
                traffic_light_class,
                location,
                rotation
            )

            if not actor:

                unreal.log_error(
                    "{} 生成失败".format(
                        facility_id
                    )
                )

                continue

            actor.set_actor_scale3d(
                unreal.Vector(
                    1.0,
                    1.0,
                    1.0
                )
            )

            label = "{}{}_{}".format(
                AUTO_PREFIX,
                facility_id,
                direction
            )

            actor.set_actor_label(
                label
            )

            spawned.append(actor)

            unreal.log(
                "{} | {} | X={:.1f} Y={:.1f} Z={:.1f} | Yaw={:.1f}".format(
                    facility_id,
                    direction,
                    x,
                    y,
                    Z_CM,
                    yaw
                )
            )

    # --------------------------------------------------------
    # 结果
    # --------------------------------------------------------

    unreal.log(
        "======================================"
    )

    unreal.log(
        "新生成红绿灯：{} 个".format(
            len(spawned)
        )
    )

    unreal.log(
        "检测到已有样板灯：{} 个".format(
            len(skipped_existing)
        )
    )

    unreal.log(
        "======================================"
    )

    # 自动选中本次生成的Actor，方便你检查
    if spawned:

        try:
            actor_subsystem.set_selected_level_actors(
                spawned
            )
        except Exception:
            pass

    unreal.log(
        "========== 自动部署完成 =========="
    )


# ============================================================
# 运行
# ============================================================

main()
