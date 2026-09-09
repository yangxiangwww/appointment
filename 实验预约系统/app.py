import os
import sqlite3
import socket
from datetime import datetime, date, timedelta
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
import io

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reservations.db")

app = FastAPI(title="换能器设备实验预约系统", description="实验室单台换能器专用预约排期管理系统")

# ----------------- 数据库初始化 -----------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT NOT NULL,
            contact TEXT DEFAULT '',
            reserve_date TEXT NOT NULL,  -- YYYY-MM-DD
            start_time TEXT NOT NULL,    -- HH:MM
            end_time TEXT NOT NULL,      -- HH:MM
            purpose TEXT DEFAULT '',
            pin TEXT DEFAULT '',         -- 4位数字修改防误碰口令，为空则任意修改
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 实验人员表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 初始化默认实验人员
    default_members = ["向阳", "邓斌", "朱书铔", "周邱玲", "李成相", "何忮芮"]
    for m in default_members:
        cursor.execute("INSERT OR IGNORE INTO members (name) VALUES (?)", (m,))

    conn.commit()
    conn.close()

init_db()

# ----------------- 数据模型 -----------------
class MemberCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="人员姓名")

class ReservationCreate(BaseModel):
    user_name: str = Field(..., min_length=1, max_length=50, description="预约人姓名")
    contact: Optional[str] = Field("", max_length=50, description="联系方式/工位(可选)")
    reserve_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="预约日期 YYYY-MM-DD")
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="开始时间 HH:MM")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="结束时间 HH:MM")
    purpose: Optional[str] = Field("", max_length=200, description="实验项目/样品类型说明")
    pin: Optional[str] = Field("", max_length=10, description="修改PIN码(选填)")

class ReservationUpdate(BaseModel):
    user_name: str = Field(..., min_length=1, max_length=50, description="预约人/变更后人员")
    contact: Optional[str] = Field("", max_length=50, description="联系方式/工位(可选)")
    reserve_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="预约日期 YYYY-MM-DD")
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="开始时间 HH:MM")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="结束时间 HH:MM")
    purpose: Optional[str] = Field("", max_length=200, description="实验项目/说明")
    pin: Optional[str] = Field("", max_length=10, description="验证原PIN码或新设PIN码")

# ----------------- 冲突检测通用算法 -----------------
def check_time_conflict(conn, reserve_date: str, start_time: str, end_time: str, exclude_id: Optional[int] = None):
    """
    检查同一天是否存在时间重叠：
    两时间段 [startA, endA] 与 [startB, endB] 重叠的充要条件：
    startA < endB 且 endA > startB
    """
    if start_time >= end_time:
        raise HTTPException(status_code=400, detail="开始时间必须早于结束时间！")

    cursor = conn.cursor()
    query = """
        SELECT id, user_name, start_time, end_time, purpose
        FROM reservations
        WHERE reserve_date = ?
          AND start_time < ?
          AND end_time > ?
    """
    params = [reserve_date, end_time, start_time]

    if exclude_id is not None:
        query += " AND id != ?"
        params.append(exclude_id)

    cursor.execute(query, params)
    conflicts = cursor.fetchall()
    if conflicts:
        conflict_list = [
            f"{c['user_name']} ({c['start_time']}~{c['end_time']})"
            for c in conflicts
        ]
        raise HTTPException(
            status_code=409,
            detail=f"时间冲突！该时段已被以下同学预约：{', '.join(conflict_list)}，请调整时间。"
        )

# ----------------- 接口定义 -----------------

@app.get("/api/members")
def list_members():
    """获取所有可用实验人员"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM members ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r["id"], "name": r["name"]} for r in rows]

@app.post("/api/members")
def add_member(data: MemberCreate):
    """添加新实验人员并持久化"""
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="人员姓名不能为空！")
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO members (name) VALUES (?)", (name,))
        conn.commit()
        new_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        cursor.execute("SELECT id FROM members WHERE name = ?", (name,))
        existing = cursor.fetchone()
        new_id = existing["id"] if existing else 0
    conn.close()
    return {"status": "success", "id": new_id, "name": name}

@app.get("/api/system-info")
def get_system_info():
    """获取本机信息和IP，用于局域网与域名展示"""
    ip_list = []
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127."):
                ip_list.append(ip)
    except Exception:
        pass
    return {
        "equipment_name": "超声/水听换能器设备",
        "current_date": date.today().isoformat(),
        "lan_ips": ip_list,
        "default_port": 8000,
        "domain_recommendation": "手机访问推荐使用实验室分配的域名（例如 http://your-domain:8000），避免局域网 IP 变更"
    }

@app.get("/api/reservations")
def list_reservations(
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD")
):
    """获取预约列表，支持按日期范围过滤"""
    conn = get_db()
    cursor = conn.cursor()
    if start_date and end_date:
        cursor.execute(
            """
            SELECT id, user_name, contact, reserve_date, start_time, end_time, purpose, (pin != '') as has_pin, created_at
            FROM reservations
            WHERE reserve_date >= ? AND reserve_date <= ?
            ORDER BY reserve_date ASC, start_time ASC
            """,
            (start_date, end_date)
        )
    else:
        cursor.execute(
            """
            SELECT id, user_name, contact, reserve_date, start_time, end_time, purpose, (pin != '') as has_pin, created_at
            FROM reservations
            ORDER BY reserve_date ASC, start_time ASC
            """
        )
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "user_name": r["user_name"],
            "contact": r["contact"],
            "reserve_date": r["reserve_date"],
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "purpose": r["purpose"],
            "has_pin": bool(r["has_pin"]),
            "created_at": r["created_at"]
        })
    return result

@app.post("/api/reservations")
def create_reservation(data: ReservationCreate):
    """创建新预约"""
    conn = get_db()
    # 冲突校验
    check_time_conflict(conn, data.reserve_date, data.start_time, data.end_time)

    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO reservations (user_name, contact, reserve_date, start_time, end_time, purpose, pin)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (data.user_name.strip(), data.contact.strip(), data.reserve_date, data.start_time, data.end_time, data.purpose.strip(), data.pin.strip())
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()

    return {"status": "success", "id": new_id, "message": "换能器设备预约成功！"}

@app.put("/api/reservations/{reservation_id}")
def update_reservation(reservation_id: int, data: ReservationUpdate):
    """灵活修改实验时间、修改/转让实验人员、更新内容"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
    record = cursor.fetchone()
    if not record:
        conn.close()
        raise HTTPException(status_code=404, detail="未找到该预约记录！")

    # 如果原记录设置了PIN码，修改时必须匹配
    existing_pin = record["pin"]
    if existing_pin and existing_pin.strip():
        if data.pin.strip() != existing_pin.strip() and data.pin.strip() != "admin888":
            conn.close()
            raise HTTPException(status_code=403, detail="修改密码(PIN)不正确，无法修改！若忘记密码请联系管理员(管理口令: admin888)。")

    # 冲突检测（排除自己）
    check_time_conflict(conn, data.reserve_date, data.start_time, data.end_time, exclude_id=reservation_id)

    # 保留原 PIN 或允许更新
    new_pin = data.pin.strip() if data.pin.strip() and data.pin.strip() != "admin888" else existing_pin

    cursor.execute(
        """
        UPDATE reservations
        SET user_name = ?, contact = ?, reserve_date = ?, start_time = ?, end_time = ?, purpose = ?, pin = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (data.user_name.strip(), data.contact.strip(), data.reserve_date, data.start_time, data.end_time, data.purpose.strip(), new_pin, reservation_id)
    )
    conn.commit()
    conn.close()

    return {"status": "success", "message": "预约修改成功！已同步更新实验人员与时段。"}

@app.delete("/api/reservations/{reservation_id}")
def delete_reservation(reservation_id: int, pin: Optional[str] = Query("")):
    """取消/删除预约，释放设备"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
    record = cursor.fetchone()
    if not record:
        conn.close()
        raise HTTPException(status_code=404, detail="未找到该预约记录！")

    existing_pin = record["pin"]
    if existing_pin and existing_pin.strip():
        if (pin or "").strip() != existing_pin.strip() and (pin or "").strip() != "admin888":
            conn.close()
            raise HTTPException(status_code=403, detail="取消密码(PIN)不正确！若忘记密码请输入管理员口令: admin888")

    cursor.execute("DELETE FROM reservations WHERE id = ?", (reservation_id,))
    conn.commit()
    conn.close()

    return {"status": "success", "message": "预约已取消，设备时段已释放。"}

@app.get("/api/export/text")
def export_text_summary(
    start_date: str = Query(..., description="起始日期 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期 YYYY-MM-DD")
):
    """一键生成适合微信/QQ群发送的格式化排班文本"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT reserve_date, start_time, end_time, user_name, contact, purpose
        FROM reservations
        WHERE reserve_date >= ? AND reserve_date <= ?
        ORDER BY reserve_date ASC, start_time ASC
        """,
        (start_date, end_date)
    )
    records = cursor.fetchall()
    conn.close()

    # 按星期组织
    weekday_map = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

    lines = []
    lines.append(f"📢【换能器设备使用排期表】")
    lines.append(f"📅 周期：{start_date} 至 {end_date}")
    lines.append("─────────────────────")

    # 按天归类
    day_dict = {}
    cur = start_dt
    while cur <= end_dt:
        day_dict[cur.isoformat()] = []
        cur += timedelta(days=1)

    for r in records:
        d = r["reserve_date"]
        if d in day_dict:
            day_dict[d].append(r)

    total_count = 0
    for d_str, r_list in day_dict.items():
        d_obj = datetime.strptime(d_str, "%Y-%m-%d").date()
        w_str = weekday_map[d_obj.weekday()]
        if r_list:
            lines.append(f"📌 {d_str} ({w_str})：")
            for r in r_list:
                total_count += 1
                purpose_txt = f" [{r['purpose']}]" if r['purpose'] else ""
                lines.append(f"  • {r['start_time']} - {r['end_time']}  {r['user_name']}{purpose_txt}")
        else:
            lines.append(f"⚪ {d_str} ({w_str})：全天无预约(空闲)")

    lines.append("─────────────────────")
    lines.append(f"共计 {total_count} 个实验预约时段。请大家按时实验，规范操作，爱护设备！")
    return {"text": "\n".join(lines)}

@app.get("/api/export/excel")
def export_excel(
    start_date: str = Query(..., description="起始日期 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期 YYYY-MM-DD")
):
    """导出 Excel 格式排班表"""
    import pandas as pd
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT reserve_date, start_time, end_time, user_name, purpose, created_at
        FROM reservations
        WHERE reserve_date >= ? AND reserve_date <= ?
        ORDER BY reserve_date ASC, start_time ASC
        """,
        (start_date, end_date)
    )
    records = cursor.fetchall()
    conn.close()

    weekday_map = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}

    data_list = []
    for r in records:
        d_obj = datetime.strptime(r["reserve_date"], "%Y-%m-%d").date()
        data_list.append({
            "实验日期": r["reserve_date"],
            "星期": weekday_map[d_obj.weekday()],
            "开始时间": r["start_time"],
            "结束时间": r["end_time"],
            "预约人": r["user_name"],
            "实验内容/说明": r["purpose"],
            "预约提交时间": r["created_at"]
        })

    df = pd.DataFrame(data_list)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="换能器设备预约排期")
    output.seek(0)

    filename = f"换能器预约排班_{start_date}_至_{end_date}.xlsx"
    from urllib.parse import quote
    encoded_filename = quote(filename)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
    )

# ----------------- 静态资源挂载 -----------------
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def read_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "换能器预约系统正在启动中..."}

# ----------------- 兼容 Hugging Face 免费免绑卡模式 -----------------
try:
    import gradio as gr
    with gr.Blocks(title="换能器设备实验预约") as demo:
        gr.HTML("""
        <div style="text-align:center; padding: 20px;">
          <h3>正在跳转至预约系统...</h3>
          <p><a href="/">若未跳转，请点击此处进入</a></p>
        </div>
        <script>window.location.href = '/';</script>
        """)
    app = gr.mount_gradio_app(app, demo, path="/_gradio")
except Exception:
    pass

if __name__ == "__main__":
    import uvicorn
    hostname = socket.gethostname()
    all_ips = []
    try:
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127."):
                all_ips.append(ip)
    except Exception:
        pass

    # 优先读取云端环境变量 PORT (Hugging Face 默认为 7860)，本地默认为 8000
    port = int(os.environ.get("PORT", 7860 if "SPACE_ID" in os.environ else 8000))

    print("=" * 66)
    print("🔬 换能器设备实验预约系统 · 手机版与电脑版已就绪！")
    print("=" * 66)
    print(f"💻 电脑本机浏览器访问：  http://localhost:{port}")
    if all_ips:
        for ip in all_ips:
            print(f"📱 手机/平板浏览器访问：  http://{ip}:{port}  (连接同一WiFi即可)")
    print("💡 提示：在网页右上角点击【📱 扫码访问】，可直接用微信扫码打开！")
    print("=" * 66)
    uvicorn.run(app, host="0.0.0.0", port=port)
