import os
import socket
from datetime import datetime, date, timedelta
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
import io

# ----------------- 数据库连接（优先 PostgreSQL，本地用 SQLite） -----------------
DATABASE_URL = os.environ.get("DATABASE_URL", "")  # Render 注入的 PostgreSQL 连接串

if DATABASE_URL:
    # ── 云端 PostgreSQL 模式 ──
    import psycopg2
    import psycopg2.extras

    def get_db():
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        return conn

    def _ph():
        return "%s"

    PG_MODE = True
else:
    # ── 本地 SQLite 模式（开发调试用）──
    import sqlite3
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reservations.db")

    def get_db():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _ph():
        return "?"

    PG_MODE = False


def dict_row(cursor, row):
    """将一行数据转为字典，兼容 PostgreSQL 与 SQLite"""
    if PG_MODE:
        cols = [desc[0] for desc in cursor.description]
        return dict(zip(cols, row))
    else:
        return dict(row)


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    if PG_MODE:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id SERIAL PRIMARY KEY,
                user_name TEXT NOT NULL,
                contact TEXT DEFAULT '',
                reserve_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                purpose TEXT DEFAULT '',
                pin TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        default_members = ["向阳", "邓斌", "朱书铔", "周邱玲", "李成相", "何忮芮"]
        for m in default_members:
            cursor.execute(
                "INSERT INTO members (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                (m,)
            )
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT NOT NULL,
                contact TEXT DEFAULT '',
                reserve_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                purpose TEXT DEFAULT '',
                pin TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        default_members = ["向阳", "邓斌", "朱书铔", "周邱玲", "李成相", "何忮芮"]
        for m in default_members:
            cursor.execute("INSERT OR IGNORE INTO members (name) VALUES (?)", (m,))

    conn.commit()
    conn.close()


app = FastAPI(title="换能器设备实验预约系统", description="实验室单台换能器专用预约排期管理系统")

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
def check_time_conflict(conn, reserve_date: str, start_time: str, end_time: str, exclude_id=None):
    if start_time >= end_time:
        raise HTTPException(status_code=400, detail="开始时间必须早于结束时间！")

    cursor = conn.cursor()
    ph = _ph()

    query = f"""
        SELECT id, user_name, start_time, end_time, purpose
        FROM reservations
        WHERE reserve_date = {ph}
          AND start_time < {ph}
          AND end_time > {ph}
    """
    params = [reserve_date, end_time, start_time]

    if exclude_id is not None:
        query += f" AND id != {ph}"
        params.append(exclude_id)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conflicts = [dict_row(cursor, r) for r in rows]

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
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM members ORDER BY id ASC")
    rows = cursor.fetchall()
    result = [dict_row(cursor, r) for r in rows]
    conn.close()
    return result

@app.post("/api/members")
def add_member(data: MemberCreate):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="人员姓名不能为空！")
    conn = get_db()
    cursor = conn.cursor()
    ph = _ph()
    try:
        if PG_MODE:
            cursor.execute(
                f"INSERT INTO members (name) VALUES ({ph}) ON CONFLICT (name) DO NOTHING RETURNING id",
                (name,)
            )
            row = cursor.fetchone()
            if row:
                new_id = row[0]
            else:
                cursor.execute(f"SELECT id FROM members WHERE name = {ph}", (name,))
                new_id = cursor.fetchone()[0]
        else:
            cursor.execute(f"INSERT OR IGNORE INTO members (name) VALUES ({ph})", (name,))
            if cursor.lastrowid:
                new_id = cursor.lastrowid
            else:
                cursor.execute(f"SELECT id FROM members WHERE name = {ph}", (name,))
                new_id = cursor.fetchone()["id"]
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"添加失败：{str(e)}")
    conn.close()
    return {"status": "success", "id": new_id, "name": name}

@app.get("/api/system-info")
def get_system_info():
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
        "domain_recommendation": "手机访问推荐使用实验室分配的域名"
    }

@app.get("/api/reservations")
def list_reservations(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None)
):
    conn = get_db()
    cursor = conn.cursor()
    ph = _ph()
    if start_date and end_date:
        cursor.execute(
            f"""
            SELECT id, user_name, contact, reserve_date, start_time, end_time, purpose,
                   CASE WHEN pin != '' THEN 1 ELSE 0 END as has_pin, created_at
            FROM reservations
            WHERE reserve_date >= {ph} AND reserve_date <= {ph}
            ORDER BY reserve_date ASC, start_time ASC
            """,
            (start_date, end_date)
        )
    else:
        cursor.execute(
            """
            SELECT id, user_name, contact, reserve_date, start_time, end_time, purpose,
                   CASE WHEN pin != '' THEN 1 ELSE 0 END as has_pin, created_at
            FROM reservations
            ORDER BY reserve_date ASC, start_time ASC
            """
        )
    rows = cursor.fetchall()
    result = []
    for r in rows:
        d = dict_row(cursor, r)
        result.append({
            "id": d["id"],
            "user_name": d["user_name"],
            "contact": d.get("contact", ""),
            "reserve_date": d["reserve_date"],
            "start_time": d["start_time"],
            "end_time": d["end_time"],
            "purpose": d.get("purpose", ""),
            "has_pin": bool(d["has_pin"]),
            "created_at": str(d["created_at"])
        })
    conn.close()
    return result

@app.post("/api/reservations")
def create_reservation(data: ReservationCreate):
    conn = get_db()
    check_time_conflict(conn, data.reserve_date, data.start_time, data.end_time)
    cursor = conn.cursor()
    ph = _ph()
    if PG_MODE:
        cursor.execute(
            f"""
            INSERT INTO reservations (user_name, contact, reserve_date, start_time, end_time, purpose, pin)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}) RETURNING id
            """,
            (data.user_name.strip(), data.contact.strip(), data.reserve_date, data.start_time, data.end_time, data.purpose.strip(), data.pin.strip())
        )
        new_id = cursor.fetchone()[0]
    else:
        cursor.execute(
            f"""
            INSERT INTO reservations (user_name, contact, reserve_date, start_time, end_time, purpose, pin)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            """,
            (data.user_name.strip(), data.contact.strip(), data.reserve_date, data.start_time, data.end_time, data.purpose.strip(), data.pin.strip())
        )
        new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"status": "success", "id": new_id, "message": "换能器设备预约成功！"}

@app.put("/api/reservations/{reservation_id}")
def update_reservation(reservation_id: int, data: ReservationUpdate):
    conn = get_db()
    cursor = conn.cursor()
    ph = _ph()
    cursor.execute(f"SELECT * FROM reservations WHERE id = {ph}", (reservation_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="未找到该预约记录！")
    record = dict_row(cursor, row)

    existing_pin = record.get("pin", "")
    if existing_pin and existing_pin.strip():
        if data.pin.strip() != existing_pin.strip() and data.pin.strip() != "admin888":
            conn.close()
            raise HTTPException(status_code=403, detail="修改密码(PIN)不正确，无法修改！若忘记密码请联系管理员(管理口令: admin888)。")

    check_time_conflict(conn, data.reserve_date, data.start_time, data.end_time, exclude_id=reservation_id)

    new_pin = data.pin.strip() if data.pin.strip() and data.pin.strip() != "admin888" else existing_pin

    cursor.execute(
        f"""
        UPDATE reservations
        SET user_name = {ph}, contact = {ph}, reserve_date = {ph}, start_time = {ph},
            end_time = {ph}, purpose = {ph}, pin = {ph}, updated_at = CURRENT_TIMESTAMP
        WHERE id = {ph}
        """,
        (data.user_name.strip(), data.contact.strip(), data.reserve_date, data.start_time, data.end_time, data.purpose.strip(), new_pin, reservation_id)
    )
    conn.commit()
    conn.close()
    return {"status": "success", "message": "预约修改成功！已同步更新实验人员与时段。"}

@app.delete("/api/reservations/{reservation_id}")
def delete_reservation(reservation_id: int, pin: Optional[str] = Query("")):
    conn = get_db()
    cursor = conn.cursor()
    ph = _ph()
    cursor.execute(f"SELECT * FROM reservations WHERE id = {ph}", (reservation_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="未找到该预约记录！")
    record = dict_row(cursor, row)

    existing_pin = record.get("pin", "")
    if existing_pin and existing_pin.strip():
        if (pin or "").strip() != existing_pin.strip() and (pin or "").strip() != "admin888":
            conn.close()
            raise HTTPException(status_code=403, detail="取消密码(PIN)不正确！若忘记密码请输入管理员口令: admin888")

    cursor.execute(f"DELETE FROM reservations WHERE id = {ph}", (reservation_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "预约已取消，设备时段已释放。"}

@app.get("/api/export/text")
def export_text_summary(
    start_date: str = Query(...),
    end_date: str = Query(...)
):
    conn = get_db()
    cursor = conn.cursor()
    ph = _ph()
    cursor.execute(
        f"""
        SELECT reserve_date, start_time, end_time, user_name, contact, purpose
        FROM reservations
        WHERE reserve_date >= {ph} AND reserve_date <= {ph}
        ORDER BY reserve_date ASC, start_time ASC
        """,
        (start_date, end_date)
    )
    rows = cursor.fetchall()
    records = [dict_row(cursor, r) for r in rows]
    conn.close()

    weekday_map = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

    lines = []
    lines.append("📢【换能器设备使用排期表】")
    lines.append(f"📅 周期：{start_date} 至 {end_date}")
    lines.append("─────────────────────")

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
    start_date: str = Query(...),
    end_date: str = Query(...)
):
    from openpyxl import Workbook
    conn = get_db()
    cursor = conn.cursor()
    ph = _ph()
    cursor.execute(
        f"""
        SELECT reserve_date, start_time, end_time, user_name, purpose, created_at
        FROM reservations
        WHERE reserve_date >= {ph} AND reserve_date <= {ph}
        ORDER BY reserve_date ASC, start_time ASC
        """,
        (start_date, end_date)
    )
    rows = cursor.fetchall()
    records = [dict_row(cursor, r) for r in rows]
    conn.close()

    weekday_map = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}
    wb = Workbook()
    ws = wb.active
    ws.title = "换能器预约排期"
    ws.append(["实验日期", "星期", "开始时间", "结束时间", "预约人", "实验内容/说明", "预约提交时间"])
    for r in records:
        d_obj = datetime.strptime(r["reserve_date"], "%Y-%m-%d").date()
        ws.append([
            r["reserve_date"],
            weekday_map[d_obj.weekday()],
            r["start_time"],
            r["end_time"],
            r["user_name"],
            r.get("purpose", ""),
            str(r["created_at"])
        ])

    output = io.BytesIO()
    wb.save(output)
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

    port = int(os.environ.get("PORT", 8000))
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
