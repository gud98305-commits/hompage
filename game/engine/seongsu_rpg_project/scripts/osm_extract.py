# OSMnx 실패 시 구글맵 스크린샷을 A담당에게 전달

import osmnx as ox
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ── 설정 ───────────────────────────────────────────────
LAT = 37.5445        # 성수동 연무장길 일대 중심 위도
LON = 127.0565       # 중심 경도
RADIUS = 300         # 반경 (미터)

OUTPUT_IMAGE   = "seongsu_osm_grid.png"
OUTPUT_GEOJSON = "seongsu_buildings.geojson"

# ── 데이터 추출 ─────────────────────────────────────────
print("[1/4] 도로 네트워크 추출 중...")
G = ox.graph_from_point((LAT, LON), dist=RADIUS, network_type="all")

print("[2/4] 건물 footprint 추출 중...")
buildings = ox.features_from_point(
    (LAT, LON),
    tags={"building": True},
    dist=RADIUS,
)

# ── 시각화 ─────────────────────────────────────────────
print("[3/4] 시각화 렌더링 중...")
fig, ax = plt.subplots(figsize=(10, 10), facecolor="white")
ax.set_facecolor("white")

# 건물: 회색
buildings.plot(ax=ax, color="#888888", alpha=0.9, zorder=2)

# 도로: 검은색
nodes, edges = ox.graph_to_gdfs(G)
edges.plot(ax=ax, color="#222222", linewidth=0.8, zorder=3)

ax.set_axis_off()
plt.title("성수동 연무장길 일대 (반경 300m)", fontsize=14, pad=10)
plt.tight_layout()

fig.savefig(OUTPUT_IMAGE, dpi=150, bbox_inches="tight", facecolor="white")
print(f"[완료] 이미지 저장: {OUTPUT_IMAGE}")

# ── GeoJSON 저장 ────────────────────────────────────────
print("[4/4] 건물 GeoJSON 저장 중...")
# geometry 컬럼만 포함된 GeoDataFrame 저장
buildings_geo = buildings[["geometry"]].copy()
buildings_geo.to_file(OUTPUT_GEOJSON, driver="GeoJSON")
print(f"[완료] GeoJSON 저장: {OUTPUT_GEOJSON}")

plt.show()
