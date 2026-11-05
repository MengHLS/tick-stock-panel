"""Merge explicit historical limit-up topics as unverified graph evidence."""
from __future__ import annotations

import calendar
import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date

from app.custom.industry_chain.descriptions import NODE_DESCRIPTIONS
from app.custom.industry_chain.models import (
    IndustryChainGraph,
    IndustryChainNode,
    IndustryChainStockLink,
    validate_graph,
)
from app.extensions.contracts import MarketDataRead

SOURCES = (
    ("ext_limit_up_platform", ("date",), ("sector", "keywords")),
    ("limit_board_events", ("trade_date",), ("limit_up_reason",)),
)

NODE_SPECS = {
    "ai-app-other": ("ai-app", "AI 应用综合", "application", 200),
    "ai-science": ("ai-app", "AI for Science", "application", 110),
    "ai-media": ("ai-app", "AI 影视与内容", "application", 50),
    "ai-marketing": ("ai-app", "AI 营销", "application", 60),
    "ai-design": ("ai-app", "AI 设计", "application", 70),
    "ai-finance": ("ai-app", "AI 金融", "application", 80),
    "ai-government": ("ai-app", "AI 政务", "application", 90),
    "ai-game": ("ai-app", "AI 游戏", "application", 100),
    "ai-toy": ("ai-edge", "AI 玩具", "product", 40),
    "ai-agent": ("ai-model", "智能体平台", "product", 30),
    "ai-pcb-support": ("ai-pcb", "AI PCB 配套材料与工具", "product", 10),
    "oc-module-product": ("oc-module", "光模块", "product", 10),
    "oc-cpo": ("oc-module", "CPO", "product", 30),
    "oc-lpo": ("oc-module", "LPO", "product", 40),
    "oc-test": ("oc-network", "光通信测试", "product", 20),
    "oc-other": ("oc-network", "光通信综合", "product", 30),
    "oc-detector": ("oc-chip", "光探测芯片", "product", 20),
    "mlcc-general": ("mlcc-manufacture", "通用 MLCC", "product", 30),
    "pcb-ccl": ("pcb-material", "覆铜板", "product", 10),
    "pcb-copper-foil": ("pcb-material", "铜箔", "product", 20),
    "pcb-glass-fabric": ("pcb-material", "电子布与玻纤布", "product", 30),
    "pcb-resin": ("pcb-material", "树脂、油墨与干膜", "product", 40),
    "pcb-chemicals": ("pcb-material", "电镀与清洗化学品", "product", 50),
    "pcb-material-other": ("pcb-material", "其他材料", "product", 90),
    "pcb-drill": ("pcb-equipment", "钻孔设备与微钻", "product", 10),
    "pcb-exposure": ("pcb-equipment", "曝光与直接成像设备", "product", 20),
    "pcb-plating": ("pcb-equipment", "电镀与清洗设备", "product", 30),
    "pcb-testing": ("pcb-equipment", "检测设备", "product", 40),
    "pcb-equipment-other": ("pcb-equipment", "其他设备", "product", 90),
    "pcb-multilayer": ("pcb-manufacture", "多层板", "product", 10),
    "pcb-hdi": ("pcb-manufacture", "HDI", "product", 20),
    "pcb-high-speed": ("pcb-manufacture", "高频高速板", "product", 30),
    "pcb-substrate": ("pcb-manufacture", "封装基板", "product", 40),
    "pcb-fpc": ("pcb-manufacture", "FPC", "product", 50),
    "semi-parts": ("semi-equipment", "设备零部件与配套", "product", 60),
    "semi-cleanroom": ("semi-fab", "半导体洁净室", "product", 30),
    "bat-solid": ("bat-cell", "固态电池", "product", 30),
    "bat-solid-material": ("bat-material", "固态电池材料", "product", 60),
    "bat-lithium": ("bat-material", "锂资源", "product", 50),
}

RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ai-chip", ("AI芯片", "算力芯片", "GPU", "DCU", "TPU")),
    ("ai-server", ("AI服务器", "AI算力服务器", "液冷服务器")),
    ("ai-memory", ("AI存储", "服务器存储")),
    ("ai-asic", ("AIASIC", "AI芯片定制")),
    ("ai-package", ("AI芯片封装", "高性能计算封装")),
    ("ai-optical", ("AI光模块", "AI光互连", "CPO", "LPO")),
    ("ai-pcb", ("AI服务器PCB", "算力PCB", "AIPCB")),
    ("ai-pcb-support", ("AIPCB微钻", "AIPCB钻针", "AIPCB材料")),
    ("ai-mlcc", ("服务器MLCC", "AIMLCC")),
    ("ai-cooling", ("数据中心液冷", "数据中心温控", "数据中心冷却", "服务器液冷", "液冷服务器")),
    ("ai-power", ("AI服务器电源", "数据中心电源", "数据中心UPS", "服务器电源")),
    ("ai-idc", ("智算中心", "数据中心运营", "IDC运营", "东数西算", "算电协同")),
    ("ai-cloud", ("云算力", "算力租赁", "算力服务", "字节算力", "腾讯算力", "华为算力")),
    ("ai-data", ("AI语料", "AI训练数据", "训练数据标注")),
    ("ai-foundation", ("大模型", "模型服务平台")),
    ("ai-office", ("AI办公",)),
    ("ai-education", ("AI教育", "AI学习机")),
    ("ai-medical", ("AI医疗",)),
    ("ai-security", ("AI安全", "AI内容安全")),
    ("ai-science", ("AI4S", "AI FOR SCIENCE", "AI材料")),
    ("ai-app-other", ("AI应用", "AI视觉", "AI零售", "AI超市", "AI导购", "AI健身", "AI房产", "AI文旅", "AI财税", "AI人力资源", "AI照明")),
    ("ai-device", ("AI手机", "AIPC", "AI电脑")),
    ("ai-glasses", ("AI眼镜",)),
    ("ai-auto", ("智能座舱", "智驾域控")),
    ("ai-media", ("AI漫剧", "AI漫画", "AI短剧", "AI微短剧", "AI影视", "AI视频", "AI出版", "AIGC长剧", "AI传媒")),
    ("ai-marketing", ("AI营销",)),
    ("ai-design", ("AI设计",)),
    ("ai-finance", ("AI金融",)),
    ("ai-government", ("AI政务",)),
    ("ai-game", ("AI游戏",)),
    ("ai-toy", ("AI玩具",)),
    ("ai-agent", ("AI智能体",)),
    ("oc-module-product", ("光模块",)),
    ("oc-cpo", ("CPO",)),
    ("oc-lpo", ("LPO",)),
    ("oc-passive", ("无源光器件",)),
    ("oc-mpo", ("MPO",)),
    ("oc-engine", ("光引擎",)),
    ("oc-laser", ("激光器芯片",)),
    ("oc-detector", ("光探测芯片",)),
    ("oc-preform", ("光纤预制棒",)),
    ("oc-cable", ("光纤光缆",)),
    ("oc-test", ("光通信测试", "光模块测试")),
    ("oc-other", ("光通信",)),
    ("oc-fiber", ("光纤", "光棒", "空芯光纤")),
    ("oc-chip", ("光芯片", "磷化铟")),
    ("oc-transport", ("800G交换机",)),
    ("mlcc-ceramic", ("MLCC粉体", "MLCC陶瓷", "电容陶瓷粉")),
    ("mlcc-electrode", ("MLCC镍粉", "MLCC电极")),
    ("mlcc-general", ("MLCC",)),
    ("pcb-ccl", ("覆铜板", "CCL")),
    ("pcb-copper-foil", ("PCB铜箔", "HVLP铜箔", "电子铜箔")),
    ("pcb-glass-fabric", ("电子布", "玻纤布", "玻璃纤维布")),
    ("pcb-resin", ("高速树脂", "PTFE", "CBF", "M9材料", "PCB油墨", "干膜")),
    ("pcb-chemicals", ("PCB化学品", "电镀液", "显影液", "清洗剂")),
    ("pcb-drill", ("PCB微钻", "钻针", "钻孔设备")),
    ("pcb-exposure", ("曝光设备", "直接成像", "LDI")),
    ("pcb-plating", ("电镀设备", "清洗设备")),
    ("pcb-testing", ("PCB检测", "PCB测试")),
    ("pcb-equipment-other", ("PCB设备", "PCB专用设备")),
    ("pcb-material-other", ("PCB材料",)),
    ("pcb-hdi", ("HDI",)),
    ("pcb-high-speed", ("高速PCB", "高频高速板", "算力PCB", "AI服务器PCB")),
    ("pcb-substrate", ("封装基板", "IC载板")),
    ("pcb-fpc", ("FPC", "柔性电路板", "柔性板")),
    ("pcb-multilayer", ("PCB", "印制电路板", "线路板", "多层板")),
    ("semi-eda", ("EDA",)),
    ("semi-ip", ("半导体IP", "芯片IP")),
    ("semi-compute", ("AI芯片", "算力芯片", "GPU", "DCU", "CPU", "TPU")),
    ("semi-memory", ("存储芯片", "DRAM", "NORFlash", "NANDFlash", "HBM", "长鑫存储")),
    ("semi-interface", ("内存接口芯片", "DDR接口", "PCIe")),
    ("semi-analog", ("模拟芯片",)),
    ("semi-power", ("功率半导体", "功率器件", "IGBT", "MOSFET")),
    ("semi-mcu", ("MCU",)),
    ("semi-wafer", ("半导体硅片", "硅晶圆")),
    ("semi-chemicals", ("抛光液", "湿电子化学品", "电子湿化学品")),
    ("semi-resist", ("光刻胶",)),
    ("semi-gas", ("电子特气", "电子气体", "电子大宗气体", "高纯气体")),
    ("semi-etch", ("刻蚀设备", "刻蚀机")),
    ("semi-deposition", ("薄膜沉积设备",)),
    ("semi-clean", ("半导体清洗设备", "晶圆清洗")),
    ("semi-inspection", ("半导体量测", "晶圆检测")),
    ("semi-foundry", ("晶圆代工",)),
    ("semi-advanced", ("先进封装", "Chiplet", "CoWoS")),
    ("semi-test", ("芯片测试", "芯片封测", "存储封测", "半导体封测")),
    ("semi-material", ("半导体材料",)),
    ("semi-equipment", ("半导体设备",)),
    ("semi-parts", ("半导体零部件", "半导体设备零部件")),
    ("semi-cleanroom", ("半导体洁净室",)),
    ("bat-cathode", ("正极材料",)),
    ("bat-anode", ("负极材料",)),
    ("bat-separator", ("锂电隔膜", "电池隔膜")),
    ("bat-electrolyte", ("电解液",)),
    ("bat-power", ("动力电池", "锂电池", "圆柱锂电", "新能源锂电池")),
    ("bat-storage", ("储能电池",)),
    ("bat-solid", ("固态电池",)),
    ("bat-solid-material", ("固态电池材料", "固态电解质", "硫化锂")),
    ("bat-lithium", ("锂矿", "碳酸锂", "氢氧化锂")),
    ("ne-pv-polysilicon", ("多晶硅", "硅料")),
    ("ne-pv-wafer", ("光伏硅片", "单晶硅片", "硅片")),
    ("ne-pv-cell-product", ("光伏电池片", "电池片")),
    ("ne-pv-module", ("光伏组件",)),
    ("ne-pv-perovskite", ("钙钛矿电池", "钙钛矿")),
    ("ne-pv-glass", ("光伏玻璃",)),
    ("ne-pv-film", ("光伏胶膜", "POE胶膜", "EVA胶膜")),
    ("ne-pv-frame", ("光伏边框",)),
    ("ne-pv-equipment", ("光伏设备", "光伏电池设备")),
    ("ne-pv-inverter", ("光伏逆变器", "组串式逆变器", "逆变器")),
    ("ne-pv-tracker", ("光伏支架",)),
    ("ne-pv-epc", ("光伏电站", "光伏EPC", "光伏运营", "光伏发电")),
    ("ne-wind-blade", ("风电叶片",)),
    ("ne-wind-drivetrain", ("风电齿轮箱", "风电轴承", "风电主轴")),
    ("ne-wind-components", ("风电零部件",)),
    ("ne-wind-generator", ("风力发电机", "风电变流器")),
    ("ne-wind-onshore", ("陆上风电", "陆上风机")),
    ("ne-wind-offshore", ("海上风机",)),
    ("ne-wind-offshore-application", ("海上风电", "海风")),
    ("ne-wind-tower", ("风电塔筒", "塔筒", "风电桩基", "单桩")),
    ("ne-wind-cable", ("海缆", "海底电缆", "海风海缆")),
    ("ne-wind-construction", ("海上风电施工", "风电运维", "风电运营", "风电主机", "风电机组件", "风电塔架")),
    ("ne-storage-lithium", ("锂电储能", "储能锂电池")),
    ("ne-storage-flow", ("液流电池", "钒电池")),
    ("ne-storage-sodium", ("钠离子电池", "钠电池")),
    ("ne-storage-air", ("压缩空气储能",)),
    ("ne-storage-pcs", ("储能PCS", "储能变流器")),
    ("ne-storage-bms", ("储能BMS", "储能EMS", "电池管理系统")),
    ("ne-storage-thermal", ("储能温控", "储能消防")),
    ("ne-storage-system", ("储能系统集成", "储能系统", "数据中心配储", "储能布局", "储能并购", "储能")),
    ("ne-storage-operation", ("储能电站运营", "独立储能")),
    ("ne-hydrogen-electrolyzer", ("电解槽", "电解水制氢")),
    ("ne-hydrogen", ("氢能", "氢能源")),
    ("ne-hydrogen-green", ("绿氢", "制氢项目")),
    ("ne-hydrogen-cylinder", ("储氢瓶", "储氢罐", "氢瓶")),
    ("ne-hydrogen-station", ("加氢站",)),
    ("ne-hydrogen-fuelcell", ("氢燃料电池", "燃料电池")),
    ("ne-hydrogen-truck", ("氢能重卡", "氢能源重卡")),
    ("ne-grid-uhv", ("特高压",)),
    ("ne-grid-transformer", ("变压器",)),
    ("ne-grid-switch", ("开关设备", "断路器", "GIS")),
    ("ne-grid-smart", ("智能电网", "电网自动化")),
    ("ne-grid-equipment", ("电网设备",)),
    ("ne-grid-vpp", ("虚拟电厂",)),
    ("ne-grid-cable", ("电力电缆", "充电桩电缆")),
    ("ne-grid-charger", ("充电桩",)),
    ("ne-grid-swap", ("换电站", "重卡换电", "换电")),
    ("cs-alloy", ("高温合金", "钛合金")),
    ("cs-composite", ("碳纤维", "复合材料")),
    ("cs-copper", ("铜合金",)),
    ("cs-rf", ("T/R芯片", "T/R组件", "相控阵芯片")),
    ("cs-attitude", ("星敏感器",)),
    ("cs-additive", ("金属3D打印", "3D打印")),
    ("cs-rocket-engine", ("火箭发动机",)),
    ("cs-solid-rocket", ("固体火箭",)),
    ("cs-sat-assembly", ("卫星总装", "卫星制造")),
    ("cs-constellation", ("卫星互联网", "低轨星座")),
    ("cs-remote-data", ("卫星遥感", "遥感数据")),
    ("cs-rtk", ("高精度定位", "RTK")),
    ("cs-nav", ("北斗",)),
    ("cs-terminal", ("卫星终端", "卫星天线")),
    ("rb-harmonic", ("谐波减速器",)),
    ("rb-rv", ("RV减速器",)),
    ("rb-ball-screw", ("滚珠丝杠",)),
    ("rb-roller-screw", ("行星滚柱丝杠",)),
    ("rb-servo", ("伺服电机", "伺服系统")),
    ("rb-hollow-cup", ("空心杯电机",)),
    ("rb-joint", ("关节模组", "一体化关节")),
    ("rb-vision", ("3D视觉", "机器视觉")),
    ("rb-force", ("力传感器", "力矩传感器")),
    ("rb-tactile", ("电子皮肤", "触觉传感器")),
    ("rb-imu", ("IMU", "惯性传感器")),
    ("rb-dexterous-hand", ("灵巧手",)),
    ("rb-embodied", ("具身智能", "VLA")),
    ("rb-humanoid", ("人形机器人",)),
    ("rb-multi-joint", ("工业机器人",)),
    ("rb-cobot", ("协作机器人",)),
    ("nev-casting", ("一体化压铸",)),
    ("nev-suspension", ("空气悬架", "CDC")),
    ("nev-brake-steer", ("线控制动", "线控转向")),
    ("nev-fast-charge", ("800V", "超快充", "4C快充", "6C快充")),
    ("nev-ad", ("智能驾驶", "自动驾驶")),
    ("nev-cockpit", ("智能座舱",)),
    ("nev-hv-connector", ("高压连接器",)),
    ("nev-heat-pump", ("热泵", "电子膨胀阀")),
    ("bat-cathode-lfp", ("磷酸铁锂",)),
    ("bat-cathode-ncm", ("三元正极", "三元材料")),
    ("bat-cathode-sodium", ("钠电正极",)),
    ("bat-anode-graphite", ("人造石墨",)),
    ("bat-anode-silicon", ("硅碳负极", "硅氧负极")),
    ("bat-anode-hard-carbon", ("硬碳",)),
    ("bat-separator-wet", ("湿法隔膜",)),
    ("bat-separator-dry", ("干法隔膜",)),
    ("bat-separator-coated", ("涂覆隔膜",)),
    ("bat-electrolyte-lipf6", ("六氟磷酸锂",)),
    ("bat-electrolyte-lifsi", ("LiFSI", "双氟磺酰亚胺锂")),
    ("bat-electrolyte-additive", ("电解液添加剂",)),
    ("bat-foil", ("锂电铜箔", "电池铝箔")),
    ("bat-can", ("电池结构件", "电池壳体")),
    ("bat-conductive", ("导电剂", "碳纳米管")),
    ("bat-equipment", ("锂电设备", "电池设备")),
    ("bat-equip-front", ("涂布机", "辊压机", "分切机")),
    ("bat-equip-back", ("化成设备", "分容设备")),
    ("bat-bms", ("电池管理系统", "BMS")),
    ("bat-thermal", ("电池热管理",)),
    ("bat-recycle", ("电池回收", "退役电池")),
    ("bat-recycle-material", ("材料再生", "梯次利用")),
    ("bat-solid", ("固态电池",)),
    ("bat-solid-material", ("固态电解质", "硫化锂")),
    ("bat-sodium", ("钠离子电池", "钠电池")),
    ("bat-4680", ("4680", "大圆柱")),
    ("bat-composite-foil", ("复合集流体", "复合铜箔")),
    ("bat-ctp", ("CTP", "CTC", "刀片电池")),
)

RULE_EXCLUSIONS = {
    "ai-chip": ("芯片封装", "芯片定制", "芯片测试"),
    "semi-compute": ("芯片封装", "芯片定制", "芯片测试"),
    "ai-server": ("服务器电源", "服务器PCB", "服务器测试"),
    "oc-module-product": ("光模块测试", "光模块PCB", "光模块电源", "光模块芯片"),
    "bat-solid": ("固态电池材料", "固态电解质"),
    "bat-cathode": ("磷酸铁锂", "三元正极", "三元材料", "钠电正极"),
    "bat-anode": ("人造石墨", "硅碳负极", "硅氧负极", "硬碳"),
    "bat-separator": ("湿法隔膜", "干法隔膜", "涂覆隔膜"),
    "bat-electrolyte": ("六氟磷酸锂", "LiFSI", "双氟磺酰亚胺锂", "电解液添加剂"),
    "cs-nav": ("高精度定位", "RTK"),
    "cs-solid-rocket": ("火箭发动机",),
    "pcb-copper-foil": ("锂电铜箔", "电池铜箔", "复合铜箔"),
    "ne-wind-offshore": ("海缆", "海底电缆", "海风海缆"),
    "ne-wind-offshore-application": ("海缆", "海底电缆", "海风海缆"),
    "ne-grid-charger": ("充电桩电缆",),
}


@dataclass(frozen=True)
class PoolObservation:
    day: date
    symbol: str
    name: str
    source: str
    text: str


def _merge_generated_note(existing: str, generated: str) -> str:
    """Replace prior generated evidence blocks while preserving user notes."""
    parts = [part.strip() for part in existing.split("\n\n") if part.strip()]
    merged = []
    replaced = False
    for part in parts:
        if part.startswith("[涨停题材合并 "):
            if not replaced:
                merged.append(generated.strip())
                replaced = True
            continue
        merged.append(part)
    if not replaced:
        merged.append(generated.strip())
    return "\n\n".join(merged)


def three_month_start(end: date) -> date:
    month_index = end.year * 12 + end.month - 1 - 3
    year, month = divmod(month_index, 12)
    month += 1
    return date(year, month, min(end.day, calendar.monthrange(year, month)[1]))


def read_pool_observations(
    market_data: MarketDataRead, start: date, end: date,
) -> tuple[list[PoolObservation], dict]:
    if start > end:
        raise ValueError("开始日期不能晚于结束日期")
    observations = []
    coverage = {"sources": [], "excluded_break_only_rows": 0, "excluded_date_rows": 0}
    for source, date_fields, text_fields in SOURCES:
        dataset = f"ext_data/{source}/timeseries"
        days = market_data.dataset_partition_dates(dataset, start, end)
        eligible = 0
        rows = 0
        topic_rows = 0
        topic_days = []
        for day in days:
            frame = market_data.read_dataset_partition(dataset, day)
            for row in frame.to_dicts():
                rows += 1
                raw_date = next((row.get(field) for field in date_fields if row.get(field)), None)
                try:
                    observed_day = date.fromisoformat(str(raw_date)[:10])
                except ValueError:
                    observed_day = None
                if observed_day != day or not start <= day <= end:
                    coverage["excluded_date_rows"] += 1
                    continue
                if source == "limit_board_events" and row.get("in_limit_up_pool") != 1:
                    coverage["excluded_break_only_rows"] += 1
                    continue
                text = "+".join(str(row.get(field) or "") for field in text_fields).strip("+")
                observations.append(PoolObservation(
                    day=day,
                    symbol=str(row.get("symbol") or "").strip().upper(),
                    name=str(row.get("name") or "").strip(),
                    source=source,
                    text=text,
                ))
                eligible += 1
                if text:
                    topic_rows += 1
                    topic_days.append(day)
        coverage["sources"].append({
            "id": source, "partition_count": len(days), "rows": rows, "eligible_rows": eligible,
            "first_date": str(min(days)) if days else None,
            "last_date": str(max(days)) if days else None,
            "topic_rows": topic_rows,
            "first_topic_date": str(min(topic_days)) if topic_days else None,
            "last_topic_date": str(max(topic_days)) if topic_days else None,
        })
    return observations, coverage


def _normalize_name(name: str) -> str:
    normalized = re.sub(r"^(?:\*?ST|S\*?ST)|[\s*＊]", "", name.upper())
    return re.sub(r"-(?:UW|WD|U|W|D)$", "", normalized)


def _matched_terms(text: str, terms: tuple[str, ...], exclusions: tuple[str, ...] = ()) -> set[str]:
    matched = set()
    for token in re.split(r"[+＋、，,;；|/\n]", text):
        compact = re.sub(r"\s+", "", token)
        if re.search(r"不涉及|未涉及|不生产|未布局|暂无|没有", compact):
            continue
        if any(exclusion.upper() in compact.upper() for exclusion in exclusions):
            continue
        for term in terms:
            pattern = re.escape(term)
            if term.isascii():
                pattern = rf"(?<![a-zA-Z]){pattern}(?![a-zA-Z])"
            if re.search(pattern, compact, re.IGNORECASE):
                matched.add(term)
    return matched


def _refine_ai_server_hits(text: str, hits: dict[str, set[str]]) -> None:
    if "ai-server" not in hits:
        return
    compact = re.sub(r"\s+", "", text).upper()

    def add(node_id: str, term: str) -> None:
        hits.setdefault(node_id, set()).add(term)

    if any(term in compact for term in ("覆铜板", "铜箔", "CBF", "钻针")):
        add("ai-pcb-support", "PCB材料")
    elif "MLCC镍粉" in compact:
        add("ai-mlcc-material", "MLCC镍粉")
    elif "电极箔" in compact:
        add("ai-passive-material", "电极箔")
    elif "MLCC" in compact:
        add("ai-mlcc", "服务器MLCC")
    elif "电容" in compact:
        add("ai-passive", "服务器电容")
    elif "交换机" in compact:
        add("ai-switch", "数据中心交换机")
    elif any(term in compact for term in ("液冷", "散热")):
        add("ai-cooling", "液冷散热")
    elif any(term in compact for term in ("电源", "UPS")):
        add("ai-power", "服务器电源")
    elif any(term in compact for term in ("测试", "检测")):
        add("ai-server-test", "服务器测试")
    elif any(term in compact for term in ("结构件", "连接器", "机箱")):
        add("ai-server-structure", "服务器结构件")
    elif any(term in compact for term in ("加速卡", "SIP")):
        add("ai-server-board", "服务器板卡")
    elif any(term in compact for term in ("PCB", "HDI")):
        add("ai-pcb", "服务器PCB")
    elif any(term in compact for term in ("光模块", "光芯片")):
        add("ai-optical", "光互连")
    else:
        add("ai-server-other", "AI服务器")

    hits.pop("ai-server", None)


def _apply_ai_hardware_context(text: str, hits: dict[str, set[str]]) -> None:
    compact = re.sub(r"\s+", "", text).upper()

    def add(node_id: str, term: str) -> None:
        hits.setdefault(node_id, set()).add(term)

    if any(term in compact for term in ("HVLP铜箔", "高速树脂(M9)", "M9材料", "PTFE", "CBF")):
        add("ai-pcb-support", "高速PCB材料")
        if "HVLP" in compact or "铜箔" in compact:
            add("pcb-copper-foil", "HVLP铜箔")
        elif "PTFE" in compact or "CBF" in compact or "M9" in compact:
            add("pcb-resin", "高速PCB树脂")

    ai_context = any(
        term in compact
        for term in ("AI服务器", "服务器", "AI硬件", "算力", "数据中心", "智算", "英伟达", "NVIDIA", "AMD", "昇腾", "HBM", "GPU")
    )
    if not ai_context:
        return
    pcb_supply_terms = (
        "覆铜板", "铜箔", "电子布", "微钻", "钻针", "钻孔", "树脂", "PTFE", "CBF",
        "油墨", "干膜", "化学品",
    )
    if any(term in compact for term in pcb_supply_terms):
        add("ai-pcb-support", "AI PCB材料")
        if "覆铜板" in compact:
            add("pcb-ccl", "AI服务器覆铜板")
        elif "铜箔" in compact:
            add("pcb-copper-foil", "AI服务器铜箔")
        elif "电子布" in compact:
            add("pcb-glass-fabric", "AI服务器电子布")
        elif any(term in compact for term in ("微钻", "钻针", "钻孔")):
            add("pcb-drill", "AI服务器PCB微钻")
        elif any(term in compact for term in ("树脂", "PTFE", "CBF")):
            add("pcb-resin", "AI服务器PCB树脂")
        elif any(term in compact for term in ("油墨", "干膜")):
            add("pcb-resin", "AI服务器PCB油墨")
        elif "化学品" in compact:
            add("pcb-chemicals", "AI服务器PCB化学品")
    elif any(term in compact for term in ("PCB", "HDI")):
        add("ai-pcb", "AI服务器PCB")
        add("pcb-hdi" if "HDI" in compact else "pcb-high-speed", "AI服务器PCB")
    if any(term in compact for term in ("液冷", "散热", "热管理", "冷却")):
        add("ai-cooling", "AI液冷散热")
    if any(term in compact for term in ("电源", "UPS")):
        add("ai-power", "AI服务器电源")
    if "交换机" in compact:
        add("ai-switch", "数据中心交换机")
    if "MLCC" in compact:
        add("ai-mlcc", "服务器MLCC")
    if "电极箔" in compact:
        add("ai-passive-material", "电容电极箔")
    elif any(term in compact for term in ("电容", "薄膜电容")):
        add("ai-passive", "服务器电容")


def merge_pool_observations(
    graph: IndustryChainGraph,
    observations: list[PoolObservation],
    instrument_names: dict[str, str],
    start: date,
    end: date,
) -> tuple[IndustryChainGraph, dict]:
    if start > end:
        raise ValueError("开始日期不能晚于结束日期")
    updated = validate_graph(graph).model_copy(deep=True)
    nodes = {node.id: node for node in updated.nodes}
    pairs = {(link.node_id, link.symbol): link for link in updated.stock_links}
    evidence = defaultdict(list)
    terms_by_pair = defaultdict(set)
    audit = []
    review = []
    unmatched = Counter()
    report = {
        "start": str(start), "end": str(end), "input_records": len(observations),
        "matched_records": 0, "unmatched_records": 0,
        "added_nodes": 0, "added_links": 0, "enriched_links": 0, "note_capacity_skips": 0,
        "review": review, "evidence": audit,
    }
    for observation in observations:
        record = {
            "date": str(observation.day), "symbol": observation.symbol,
            "name": observation.name, "source": observation.source, "text": observation.text,
        }
        if not start <= observation.day <= end:
            review.append({**record, "reason": "outside_window"})
            continue
        if not observation.text.strip():
            report["unmatched_records"] += 1
            unmatched["（无题材）"] += 1
            continue
        canonical_name = instrument_names.get(observation.symbol)
        if canonical_name is None:
            review.append({**record, "reason": "unknown_symbol"})
            continue
        if not observation.name or _normalize_name(observation.name) != _normalize_name(canonical_name):
            review.append({**record, "reason": "name_conflict", "current_name": canonical_name})
            continue
        hits = {}
        for node_id, terms in RULES:
            matches = _matched_terms(observation.text, terms, RULE_EXCLUSIONS.get(node_id, ()))
            if matches:
                hits[node_id] = matches
        _apply_ai_hardware_context(observation.text, hits)
        _refine_ai_server_hits(observation.text, hits)
        if "ai-pcb-support" in hits:
            hits.pop("ai-pcb", None)
        if "pcb-multilayer" in hits and any(
            node_id.startswith("pcb-") and node_id != "pcb-multilayer"
            for node_id in hits
        ):
            hits.pop("pcb-multilayer", None)
        if "pcb-material-other" in hits and any(
            node_id in hits for node_id in (
                "pcb-ccl", "pcb-copper-foil", "pcb-glass-fabric", "pcb-resin", "pcb-chemicals",
            )
        ):
            hits.pop("pcb-material-other", None)
        if "pcb-equipment-other" in hits and any(
            node_id in hits for node_id in (
                "pcb-drill", "pcb-exposure", "pcb-plating", "pcb-testing",
            )
        ):
            hits.pop("pcb-equipment-other", None)
        if "ai-app-other" in hits and any(
            node in hits for node in (
                "ai-office", "ai-education", "ai-medical", "ai-security", "ai-media",
                "ai-marketing", "ai-design", "ai-finance", "ai-government", "ai-game",
                "ai-toy", "ai-agent", "ai-science",
            )
        ):
            hits.pop("ai-app-other", None)
        if "oc-other" in hits and any(
            node in hits for node in (
                "oc-module-product", "oc-cpo", "oc-lpo", "oc-passive", "oc-mpo",
                "oc-engine", "oc-laser", "oc-detector", "oc-preform", "oc-cable",
                "oc-test", "oc-transport", "oc-fiber", "oc-chip",
            )
        ):
            hits.pop("oc-other", None)
        if "oc-fiber" in hits and any(node in hits for node in ("oc-preform", "oc-cable")):
            hits.pop("oc-fiber", None)
        if "semi-material" in hits and any(
            node in hits for node in ("semi-wafer", "semi-chemicals", "semi-resist", "semi-gas")
        ):
            hits.pop("semi-material", None)
        if "semi-equipment" in hits and any(
            node in hits for node in (
                "semi-etch", "semi-deposition", "semi-clean", "semi-inspection", "semi-parts",
            )
        ):
            hits.pop("semi-equipment", None)
        if "ne-hydrogen" in hits and any(
            node in hits for node in (
                "ne-hydrogen-electrolyzer", "ne-hydrogen-green", "ne-hydrogen-cylinder",
                "ne-hydrogen-station", "ne-hydrogen-fuelcell", "ne-hydrogen-truck",
            )
        ):
            hits.pop("ne-hydrogen", None)
        if "ne-storage-system" in hits and any(
            node in hits for node in (
                "ne-storage-lithium", "ne-storage-flow", "ne-storage-sodium",
                "ne-storage-air", "ne-storage-pcs", "ne-storage-bms",
                "ne-storage-thermal", "ne-storage-operation",
            )
        ):
            hits.pop("ne-storage-system", None)
        if "ai-mlcc-material" in hits:
            hits.pop("ai-mlcc", None)
        if "ai-passive-material" in hits:
            hits.pop("ai-passive", None)
        if "mlcc-ceramic" in hits or "mlcc-electrode" in hits:
            hits.pop("mlcc-general", None)
        if not hits:
            report["unmatched_records"] += 1
            unmatched[observation.text or "（无题材）"] += 1
            continue
        report["matched_records"] += 1
        for node_id, terms in hits.items():
            if node_id not in nodes and node_id in NODE_SPECS:
                parent_id, name, kind, order = NODE_SPECS[node_id]
                parent = nodes.get(parent_id)
                if parent is not None:
                    node = IndustryChainNode(
                        id=node_id, chain_id=parent.chain_id, parent_id=parent_id,
                        name=name, kind=kind, order=order,
                        description=NODE_DESCRIPTIONS.get(node_id, ""),
                    )
                    updated.nodes.append(node)
                    nodes[node_id] = node
                    report["added_nodes"] += 1
            if node_id not in nodes:
                review.append({**record, "reason": "missing_target", "node_id": node_id})
                continue
            pair = (node_id, observation.symbol)
            evidence[pair].append(observation)
            terms_by_pair[pair].update(terms)
            audit.append({**record, "node_id": node_id, "terms": sorted(terms)})
    marker = f"[涨停题材合并 {start}..{end}]"
    for pair, items in sorted(evidence.items()):
        node_id, symbol = pair
        days = sorted({item.day for item in items})
        sources = sorted({item.source for item in items})
        recent = sorted(set((item.day, item.source, item.text) for item in items), reverse=True)[:4]
        terms = sorted(terms_by_pair[pair], key=lambda term: (-len(term), term))
        note = "\n".join([
            marker,
            f"首次 {days[0]}；最近 {days[-1]}；{len(days)} 个交易日；{len(items)} 条来源记录。",
            f"扩展数据：{', '.join(sources)}",
            f"匹配题材：{'、'.join(terms)}",
            "历史涨停题材线索，未核验当前主营、产品或供货关系。",
            *(f"{day} [{source}] {text[:220]}" for day, source, text in recent),
        ])[:1800]
        link = pairs.get(pair)
        if link is not None:
            combined = _merge_generated_note(link.note, note)
            if combined == link.note:
                continue
            if len(combined) > 2000:
                report["note_capacity_skips"] += 1
                continue
            link.note = combined
            report["enriched_links"] += 1
            continue
        identity = hashlib.sha256(f"{node_id}|{symbol}".encode()).hexdigest()[:24]
        link = IndustryChainStockLink(
            id=f"pool-{identity}", node_id=node_id, symbol=symbol,
            reason_short=f"涨停题材：{terms[0][:15]}",
            note=note, evidence_status="pending",
            basis="theme_clue",
            sort_order=max((item.sort_order for item in updated.stock_links if item.node_id == node_id), default=0) + 10,
        )
        updated.stock_links.append(link)
        pairs[pair] = link
        report["added_links"] += 1
    report["unmatched_topics"] = [
        {"text": text, "count": count} for text, count in unmatched.most_common()
    ]
    report["matched_stocks"] = len({symbol for _, symbol in evidence})
    return validate_graph(updated), report
