"""Chainlit UI for Vision-to-Task Agent with editable task details."""
import chainlit as cl
from chainlit.input_widget import Switch
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
import base64
import os
import json
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.routing import Route, Mount

from starlette.staticfiles import StaticFiles
from dotenv import load_dotenv

from tools import store_image_directly
from agent import process_image, resume_with_approval
from database import DB_PATH
from local_storage import LocalStorageClient, UPLOAD_DIR
from log_config import logger
import sqlite3

load_dotenv()


# === DATABASE HELPERS ===
def get_task_details(task_id: int) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT t.*, i.filename FROM tasks t LEFT JOIN images i ON t.image_id = i.id WHERE t.id = ?",
        (task_id,)
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_task_image_b64(image_id: int) -> str | None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT data FROM images WHERE id = ?", (image_id,))
    row = cur.fetchone()
    conn.close()
    return base64.b64encode(row[0]).decode() if row else None


def update_task(task_id: int, data: dict) -> bool:
    conn = sqlite3.connect(DB_PATH)
    try:
        args_json = json.dumps(data.get("arguments", {}), ensure_ascii=False) if data.get("arguments") else None
        conn.execute(
            "UPDATE tasks SET task_type=?, full_name=?, national_code=?, status=?, image_id=?, arguments=? WHERE id=?",
            (data.get("task_type"), data.get("full_name"), data.get("national_code"),
             data.get("status"), data.get("image_id"), args_json, task_id)
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"UPDATE_TASK_ERROR | {e}")
        return False
    finally:
        conn.close()


# === TASK DETAIL PAGE ===
TASK_PAGE_HTML = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>وظیفه #{task_id}</title>
    <style>
        *{{box-sizing:border-box;margin:0;padding:0}}
        body{{font-family:Tahoma,sans-serif;background:linear-gradient(135deg,#1a1a2e,#16213e);min-height:100vh;color:#e0e0e0;padding:20px}}
        .container{{max-width:1200px;margin:0 auto}}
        .grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
        @media(max-width:900px){{.grid{{grid-template-columns:1fr}}}}
        .card{{background:rgba(255,255,255,0.05);border-radius:16px;padding:24px;margin-bottom:20px;border:1px solid rgba(255,255,255,0.1)}}
        h1{{color:#4ade80;margin-bottom:20px}}
        h2{{color:#60a5fa;margin:20px 0 16px}}
        .back-btn{{display:inline-block;padding:10px 20px;background:#3b82f6;color:white;text-decoration:none;border-radius:8px;margin-bottom:20px}}
        table{{width:100%;border-collapse:collapse}}
        th,td{{padding:12px;text-align:right;border-bottom:1px solid rgba(255,255,255,0.1)}}
        th{{color:#9ca3af;width:150px}}
        input,select,textarea{{width:100%;padding:8px 12px;border-radius:6px;border:1px solid rgba(255,255,255,0.2);background:rgba(0,0,0,0.3);color:#f3f4f6}}
        input:disabled,textarea:disabled{{background:rgba(0,0,0,0.5);color:#9ca3af}}
        textarea{{min-height:80px;resize:vertical}}
        .arg-row{{display:flex;gap:10px;margin-bottom:10px}}
        .arg-row input{{flex:1}}
        .arg-row .key{{max-width:200px}}
        .btn{{padding:8px 16px;border-radius:6px;border:none;cursor:pointer}}
        .btn-add{{background:#22c55e;color:white}}
        .btn-del{{background:#ef4444;color:white}}
        .btn-save{{background:#3b82f6;color:white;padding:12px 24px;font-size:16px}}
        .actions{{margin-top:20px;text-align:left}}
        .msg{{padding:12px;border-radius:8px;margin-bottom:16px;display:none}}
        .msg.ok{{background:#22c55e33;border:1px solid #22c55e;color:#4ade80}}
        .msg.err{{background:#ef444433;border:1px solid #ef4444;color:#f87171}}
        .img-box{{text-align:center;margin-top:16px}}
        .img-box img{{max-width:100%;max-height:400px;border-radius:8px}}
        .ocr-field{{margin-bottom:12px}}
        .ocr-field label{{display:block;color:#9ca3af;margin-bottom:4px;font-size:13px}}
        .ocr-section{{background:rgba(251,191,36,0.1);border:1px solid rgba(251,191,36,0.3);border-radius:12px;padding:16px;margin-top:16px}}
    </style>
</head>
<body>
<div class="container">
    <a href="/" class="back-btn">← بازگشت</a>
    <div id="msg" class="msg"></div>
    <h1>📋 وظیفه #{task_id}</h1>
    <div class="grid">
        <div>
            <div class="card">
                <h2>🗃️ رکورد دیتابیس</h2>
                <form id="frm">
                    <table>
                        <tr><th>id</th><td><input value="{task_id}" disabled></td></tr>
                        <tr><th>task_type</th><td><input name="task_type" value="{task_type}"></td></tr>
                        <tr><th>full_name</th><td><input name="full_name" value="{full_name}"></td></tr>
                        <tr><th>national_code</th><td><input name="national_code" value="{national_code}"></td></tr>
                        <tr><th>status</th><td><select name="status">
                            <option value="pending" {s_pend}>pending</option>
                            <option value="completed" {s_comp}>completed</option>
                            <option value="cancelled" {s_canc}>cancelled</option>
                        </select></td></tr>
                        <tr><th>image_id</th><td><input type="number" name="image_id" value="{image_id}"></td></tr>
                        <tr><th>created_at</th><td><input value="{created_at}" disabled></td></tr>
                    </table>
                    <h2>📝 arguments</h2>
                    <div id="args">{args_html}</div>
                    <button type="button" class="btn btn-add" onclick="addArg()">+ افزودن</button>
                    <div class="actions"><button type="submit" class="btn btn-save">💾 ذخیره</button></div>
                </form>
            </div>
        </div>
        <div>
            {ocr_section}
            {img_section}
        </div>
    </div>
</div>
<script>
function addArg(k='',v=''){{
    const d=document.createElement('div');d.className='arg-row';
    d.innerHTML='<input class="key" placeholder="کلید" value="'+k+'"><input placeholder="مقدار" value="'+v+'"><button type="button" class="btn btn-del" onclick="this.parentElement.remove()">✕</button>';
    document.getElementById('args').appendChild(d);
}}
document.getElementById('frm').onsubmit=async e=>{{
    e.preventDefault();const f=e.target,m=document.getElementById('msg');
    const args={{}};document.querySelectorAll('.arg-row').forEach(r=>{{
        const k=r.querySelector('.key').value.trim(),v=r.querySelectorAll('input')[1].value;
        if(k)args[k]=v;
    }});
    try{{
        const res=await fetch('/api/task/{task_id}',{{method:'PUT',headers:{{'Content-Type':'application/json'}},
            body:JSON.stringify({{task_type:f.task_type.value,full_name:f.full_name.value,national_code:f.national_code.value,status:f.status.value,image_id:parseInt(f.image_id.value)||null,arguments:args}})}});
        const j=await res.json();
        m.className='msg '+(j.success?'ok':'err');m.textContent=j.message;m.style.display='block';
        setTimeout(()=>m.style.display='none',3000);
    }}catch(err){{m.className='msg err';m.textContent=err;m.style.display='block';}}
}};
</script>
</body></html>"""

OCR_LABELS = {
    "letter_number": "شماره نامه",
    "letter_date": "تاریخ",
    "sender": "فرستنده",
    "recipient": "گیرنده",
    "subject": "موضوع",
    "body": "متن نامه",
    "attachments": "پیوست‌ها",
    "signature": "امضا",
    "raw_text": "متن کامل"
}


async def task_page(request: Request):
    task_id = int(request.path_params["task_id"])
    task = get_task_details(task_id)
    if not task:
        return HTMLResponse("<h1>یافت نشد</h1>", 404)
    
    args = task.get("arguments")
    args_html = ""
    if args:
        if isinstance(args, str):
            try: args = json.loads(args)
            except: args = {}
        if isinstance(args, dict):
            for k, v in args.items():
                args_html += f'<div class="arg-row"><input class="key" value="{k}"><input value="{v}"><button type="button" class="btn btn-del" onclick="this.parentElement.remove()">✕</button></div>'
    
    # OCR section
    ocr_section = ""
    ocr_data = task.get("ocr_data")
    if ocr_data:
        if isinstance(ocr_data, str):
            try: ocr_data = json.loads(ocr_data)
            except: ocr_data = {}
        if isinstance(ocr_data, dict) and ocr_data:
            ocr_fields = ""
            for k, v in ocr_data.items():
                if v:
                    label = OCR_LABELS.get(k, k)
                    val = ", ".join(v) if isinstance(v, list) else str(v)
                    is_long = k in ("body", "raw_text") or len(str(v)) > 100
                    if is_long:
                        ocr_fields += f'<div class="ocr-field"><label>{label}</label><textarea disabled>{val}</textarea></div>'
                    else:
                        ocr_fields += f'<div class="ocr-field"><label>{label}</label><input value="{val}" disabled></div>'
            if ocr_fields:
                ocr_section = f'<div class="card"><h2>📄 متن استخراج‌شده (OCR)</h2><div class="ocr-section">{ocr_fields}</div></div>'
    
    img_section = ""
    if task.get("image_id"):
        b64 = get_task_image_b64(task["image_id"])
        if b64:
            img_section = f'<div class="card"><h2>🖼️ تصویر</h2><div class="img-box"><img src="data:image/png;base64,{b64}"></div></div>'
    
    s = task.get("status", "pending")
    return HTMLResponse(TASK_PAGE_HTML.format(
        task_id=task["id"], task_type=task.get("task_type") or "", full_name=task.get("full_name") or "",
        national_code=task.get("national_code") or "", image_id=task.get("image_id") or "",
        created_at=task.get("created_at") or "", args_html=args_html, ocr_section=ocr_section, img_section=img_section,
        s_pend="selected" if s=="pending" else "", s_comp="selected" if s=="completed" else "", s_canc="selected" if s=="cancelled" else ""
    ))


async def task_api(request: Request):
    task_id = int(request.path_params["task_id"])
    try:
        data = await request.json()
        if update_task(task_id, data):
            logger.info(f"TASK_UPDATED | id={task_id}")
            return JSONResponse({"success": True, "message": "ذخیره شد ✓"})
        return JSONResponse({"success": False, "message": "خطا"}, 500)
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, 400)


cl.server.app.routes.insert(0, Route("/task/{task_id:int}", task_page))
cl.server.app.routes.insert(0, Route("/api/task/{task_id:int}", task_api, methods=["PUT"]))
cl.server.app.routes.insert(0, Mount("/uploads", app=StaticFiles(directory=UPLOAD_DIR), name="uploads"))


# === CHAINLIT ===
@cl.data_layer
def get_data_layer():
    return SQLAlchemyDataLayer(conninfo="sqlite+aiosqlite:///chat_history.db", storage_provider=LocalStorageClient())

USERS = {"admin": {"password": "admin123", "role": "admin"}}

@cl.password_auth_callback
def auth_callback(username: str, password: str):
    u = USERS.get(username)
    return cl.User(identifier=username, metadata={"role": u["role"]}) if u and u["password"] == password else None


@cl.on_chat_start
async def start():
    s = await cl.ChatSettings([Switch(id="auto", label="تأیید خودکار", initial=False)]).send()
    cl.user_session.set("settings", s)
    await cl.Message(content="👋 **سلام! به دستیار استخراج وظایف خوش آمدید**\n\nیک تصویر از نامه رسمی فارسی آپلود کنید تا اطلاعات را استخراج کنم.").send()


@cl.on_settings_update
async def on_settings(s):
    cl.user_session.set("settings", s)


@cl.on_message
async def main(msg: cl.Message):
    auto = (cl.user_session.get("settings") or {}).get("auto", False)
    
    if not msg.elements:
        await cl.Message(content="⚠️ **لطفاً یک تصویر آپلود کنید**\n\nبرای استخراج وظیفه، باید تصویری از نامه رسمی را ارسال کنید.").send()
        return
    
    img = msg.elements[0]
    with open(img.path, "rb") as f:
        data = f.read()
    
    img_id = store_image_directly(img.name, data)
    b64 = base64.b64encode(data).decode()
    logger.info(f"UI | IMAGE_UPLOAD | filename={img.name} image_id={img_id} size={len(data)} bytes auto={auto}")
    
    await cl.Message(content=f"📥 **تصویر دریافت شد**\n\n• نام فایل: `{img.name}`\n• شناسه تصویر: `{img_id}`\n\n🔄 شروع پردازش...", author="سیستم").send()
    
    # Start graph execution with streaming
    cl.user_session.set("image_id", img_id)
    state, events = await process_image(b64, img_id, img.name)
    
    # Stream events to UI
    for event in events:
        node_name = list(event.keys())[0]
        node_state = event[node_name]
        if not isinstance(node_state, dict):
            continue
        
        if node_name == "ocr":
            ocr_data = node_state.get("ocr_data", {})
            ocr_display = ""
            for k, v in ocr_data.items():
                if v and k != "raw_text":
                    label = OCR_LABELS.get(k, k)
                    val = ", ".join(v) if isinstance(v, list) else str(v)[:100]
                    ocr_display += f"• **{label}:** {val}\n"
            if ocr_display:
                await cl.Message(content=f"📄 **متن استخراجشده:**\n\n{ocr_display}", author="OCR").send()
        
        elif node_name == "extract":
            tasks = node_state.get("extracted_tasks", [])
            await cl.Message(content=f"🔍 **استخراج:** {len(tasks)} وظیفه یافت شد", author="سیستم").send()
        
        elif node_name == "validate":
            v = node_state.get("validation_result", {})
            if v.get("decision") == "approve":
                await cl.Message(content=f"✅ **اعتبارسنجی موفق**", author="اعتبارسنج").send()
            else:
                retry = node_state.get("retry_count", 0)
                await cl.Message(content=f"⚠️ **اعتبارسنجی رد شد** (تلاش {retry+1})\n\n{v.get('reason', '')}", author="اعتبارسنج").send()
        
        elif node_name == "increment_retry":
            await cl.Message(content=f"🔄 **تلاش مجدد...**", author="سیستم").send()
    
    # Check for errors
    if state.get("error"):
        logger.error(f"UI | PIPELINE_ERROR | image_id={img_id} error={state['error']}")
        await cl.Message(content=f"❌ **خطا:** {state['error']}", author="سیستم").send()
        return
    
    # Show extracted tasks
    tasks = state.get("extracted_tasks", [])
    if not tasks:
        logger.warning(f"UI | NO_TASKS | image_id={img_id}")
        await cl.Message(content="⚠️ **وظیفهای یافت نشد**", author="سیستم").send()
        return
    
    for i, t in enumerate(tasks, 1):
        args_str = ""
        if t.get("arguments"):
            args_str = "\n".join(f"  • `{k}`: {v}" for k, v in t["arguments"].items())
        
        task_details = f"**📋 وظیفه {i}**\n\n🔹 **نوع:** {t.get('task_type', '—')}\n🔹 **نام:** {t.get('full_name', '—')}\n🔹 **کد ملی:** {t.get('national_code', '—')}"
        if args_str:
            task_details += f"\n🔹 **آرگومانها:**\n{args_str}"
        
        await cl.Message(content=task_details, author="استخراج").send()
    
    # Human approval (unless auto mode)
    if not auto:
        logger.info(f"UI | AWAITING_APPROVAL | image_id={img_id} tasks={len(tasks)}")
        r = await cl.AskActionMessage(
            content=f"**🔐 تأیید ثبت {len(tasks)} وظیفه در پایگاه داده؟**",
            actions=[cl.Action(name="y", payload={"v":"y"}, label="✅ تأیید"), cl.Action(name="n", payload={"v":"n"}, label="❌ لغو")],
            timeout=86400
        ).send()
        approved = r and r.get("payload", {}).get("v") == "y"
        logger.info(f"UI | APPROVAL_RESULT | image_id={img_id} approved={approved}")
    else:
        approved = True
        logger.info(f"UI | AUTO_APPROVED | image_id={img_id}")
    
    if not approved:
        await cl.Message(content="❌ **لغو شد**").send()
        await resume_with_approval(img_id, False)
        return
    
    # Resume graph with approval
    await cl.Message(content="💾 **ذخیره در پایگاه داده...**", author="سیستم").send()
    final_state, final_events = await resume_with_approval(img_id, True)
    
    # Show results
    stored = final_state.get("final_tasks", [])
    for task_result in stored:
        tid = task_result.get("task_id")
        await cl.Message(content=f"✅ **وظیفه #{tid} ثبت شد**\n\n[📋 مشاهده جزئیات](/task/{tid})", author="سیستم").send()
    
    if final_state.get("error"):
        await cl.Message(content=f"⚠️ **خطاها:** {final_state['error']}", author="سیستم").send()
    
    logger.info(f"UI | COMPLETE | image_id={img_id} stored={len(stored)}")
    await cl.Message(content="✅ **تکمیل شد**", author="سیستم").send()

