import os
import sqlite3
import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

DB_FILE = os.getenv("DB_FILE", "devices.db")
ADMIN_ROUTE = os.getenv("ADMIN_ROUTE", "panel_x7k9m2")


def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                model TEXT,
                status INTEGER DEFAULT 1,
                last_seen TIMESTAMP,
                tag TEXT DEFAULT ''
            )
        """)
        # Migration: add tag column for existing databases
        try:
            conn.execute("ALTER TABLE devices ADD COLUMN tag TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # Column already exists


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)


# --- API for the App ---

@app.get("/check/{device_id}")
async def check_device(device_id: str, model: str = "Unknown Device"):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM devices WHERE device_id = ?", (device_id,))
        result = cursor.fetchone()

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if result is None:
            cursor.execute(
                "INSERT INTO devices (device_id, model, last_seen) VALUES (?, ?, ?)",
                (device_id, model, now),
            )
            conn.commit()
            return {"access": True}

        cursor.execute(
            "UPDATE devices SET last_seen = ?, model = ? WHERE device_id = ?",
            (now, model, device_id),
        )
        conn.commit()
        return {"access": bool(result[0])}


# --- Admin Dashboard ---

@app.get(f"/{ADMIN_ROUTE}", response_class=HTMLResponse)
async def admin_panel():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM devices ORDER BY last_seen DESC")
        rows = cursor.fetchall()

    table_rows = ""
    for r in rows:
        device_id = r[0]
        model = r[1]
        status = r[2]
        last_seen = r[3]
        tag = r[4] if len(r) > 4 and r[4] else ""
        status_text = "ACTIVE" if status else "BLOCKED"
        status_class = "active" if status else "blocked"
        btn_text = "Block" if status else "Unblock"
        btn_class = "btn-block" if status else "btn-unblock"
        escaped_tag = tag.replace('"', '&quot;')
        table_rows += f"""
            <tr>
                <td>{device_id[:12]}...</td>
                <td>
                    <span class="tag-display" id="tag-text-{device_id[:8]}">{tag or '<span style="color:#999">No tag</span>'}</span>
                    <form class="tag-form" id="tag-form-{device_id[:8]}" action="/{ADMIN_ROUTE}/tag/{device_id}" method="post" style="display:none">
                        <input type="text" name="tag" value="{escaped_tag}" placeholder="e.g. Juan's iPad" class="tag-input" />
                        <button type="submit" class="btn-save">Save</button>
                        <button type="button" class="btn-cancel" onclick="toggleTag('{device_id[:8]}', false)">✕</button>
                    </form>
                    <button class="btn-edit" onclick="toggleTag('{device_id[:8]}', true)" id="tag-btn-{device_id[:8]}">✎</button>
                </td>
                <td>{model}</td>
                <td><span class="status {status_class}">{status_text}</span></td>
                <td>{last_seen}</td>
                <td><a href="/{ADMIN_ROUTE}/toggle/{device_id}"><button class="{btn_class}">{btn_text}</button></a></td>
            </tr>
        """

    return f"""
    <html>
    <head>
        <title>Kill Switch Dashboard</title>
        <style>
            body {{ font-family: -apple-system, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; background: #f5f5f5; }}
            h1 {{ color: #333; }}
            table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
            th, td {{ padding: 12px 16px; text-align: left; border-bottom: 1px solid #eee; }}
            th {{ background: #333; color: #fff; }}
            .status {{ padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
            .active {{ background: #e6f4ea; color: #1e7e34; }}
            .blocked {{ background: #fde8e8; color: #c62828; }}
            button {{ padding: 6px 16px; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; }}
            .btn-block {{ background: #ef5350; color: #fff; }}
            .btn-unblock {{ background: #66bb6a; color: #fff; }}
            button:hover {{ opacity: 0.85; }}
            .tag-form {{ display: inline-flex; align-items: center; gap: 4px; }}
            .tag-input {{ padding: 4px 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px; width: 140px; }}
            .btn-edit {{ background: none; border: none; cursor: pointer; font-size: 16px; padding: 2px 6px; color: #666; }}
            .btn-edit:hover {{ color: #333; }}
            .btn-save {{ background: #66bb6a; color: #fff; padding: 4px 10px; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: 600; }}
            .btn-cancel {{ background: #eee; color: #666; padding: 4px 8px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }}
        </style>
    </head>
    <body>
        <h1>Remote Kill Switch Dashboard</h1>
        <table>
            <tr><th>Device ID</th><th>Tag</th><th>Model</th><th>Status</th><th>Last Seen</th><th>Action</th></tr>
            {table_rows}
        </table>
        <script>
        function toggleTag(id, show) {{
            document.getElementById('tag-text-' + id).style.display = show ? 'none' : '';
            document.getElementById('tag-form-' + id).style.display = show ? 'inline-flex' : 'none';
            document.getElementById('tag-btn-' + id).style.display = show ? 'none' : '';
            if (show) document.querySelector('#tag-form-' + id + ' input').focus();
        }}
        </script>
    </body>
    </html>
    """


@app.post(f"/{ADMIN_ROUTE}/tag/{{device_id}}")
async def tag_device(device_id: str, tag: str = Form("")):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "UPDATE devices SET tag = ? WHERE device_id = ?",
            (tag.strip(), device_id),
        )
        conn.commit()
    return RedirectResponse(url=f"/{ADMIN_ROUTE}", status_code=303)


@app.get(f"/{ADMIN_ROUTE}/toggle/{{device_id}}")
async def toggle_device(device_id: str):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "UPDATE devices SET status = 1 - status WHERE device_id = ?",
            (device_id,),
        )
        conn.commit()
    return RedirectResponse(url=f"/{ADMIN_ROUTE}")
