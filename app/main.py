from __future__ import annotations

import csv
import io
import logging
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from . import auth, jobs, quotas
from .collector.cities import CITIES, city_name
from .collector.niches import ALL_NICHES, NICHE_GROUPS, RECOMMENDED
from .config import ANTHROPIC_API_KEY, BASE_DIR, PLANS, PUBLIC_PLANS
from .db import get_session, init_db
from .messaging import ANGLES, generate
from .models import Lead, Message, Run, SavedList, Template, User

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s — %(message)s")

app = FastAPI(title="GisFind", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

@app.on_event("startup")
def _startup() -> None:
    init_db()

def require_user(request: Request, db: Session = Depends(get_session)) -> User:
    user = auth.current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Нужен вход")
    return user

def page(request: Request, name: str, user: Optional[User],
         db: Session, **ctx) -> HTMLResponse:
    base = {
        "request": request,
        "user": user,
        "plan": quotas.plan_of(user) if user else None,
        "remaining": quotas.remaining(db, user) if user else 0,
        "claude_on": bool(ANTHROPIC_API_KEY),
    }
    base.update(ctx)
    return templates.TemplateResponse(name, base)

def _lead_dict(lead: Lead, run: Run) -> dict:
    return {
        "org_id": lead.org_id,
        "name": lead.name,
        "extension": lead.extension,
        "rubric": lead.rubric,
        "rating": lead.rating,
        "reviews_count": lead.reviews_count,
        "has_site": lead.has_site,
        "instagram": lead.instagram,
        "city_name": run.city_name,
    }

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_session)):
    user = auth.current_user(request, db)
    if user:
        return RedirectResponse("/search", status_code=303)
    return page(request, "login.html", None, db, mode="login", error=None)

@app.get("/signup", response_class=HTMLResponse)
def signup_form(request: Request, db: Session = Depends(get_session)):
    return page(request, "login.html", None, db, mode="signup", error=None)

@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...),
          db: Session = Depends(get_session)):
    user = auth.get_by_email(db, email)
    if not user or not auth.verify_password(password, user.password_hash):
        return page(request, "login.html", None, db, mode="login",
                    error="Неверная почта или пароль")
    resp = RedirectResponse("/search", status_code=303)
    resp.set_cookie(auth.COOKIE_NAME, auth.make_session(user.id),
                    httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return resp

@app.post("/signup")
def signup(request: Request, email: str = Form(...), password: str = Form(...),
           db: Session = Depends(get_session)):
    if len(password) < 6:
        return page(request, "login.html", None, db, mode="signup",
                    error="Пароль — минимум 6 символов")
    if auth.get_by_email(db, email):
        return page(request, "login.html", None, db, mode="signup",
                    error="Такая почта уже зарегистрирована")
    user = auth.create_user(db, email, password)
    resp = RedirectResponse("/search", status_code=303)
    resp.set_cookie(auth.COOKIE_NAME, auth.make_session(user.id),
                    httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return resp

@app.get("/logout")
def logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(auth.COOKIE_NAME)
    return resp

@app.get("/search", response_class=HTMLResponse)
def search_page(request: Request, db: Session = Depends(get_session)):
    user = auth.current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    runs = db.scalars(
        select(Run).where(Run.user_id == user.id).order_by(desc(Run.id)).limit(12)
    ).all()
    return page(request, "search.html", user, db,
                cities=CITIES, groups=NICHE_GROUPS, all_niches=ALL_NICHES,
                recommended=RECOMMENDED, runs=runs)

@app.post("/search")
def search_start(request: Request, city: str = Form(...), niche: str = Form(...),
                 limit: int = Form(10), hot_only: str = Form(""),
                 db: Session = Depends(get_session)):
    user = auth.current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)

    niche = (niche or "").strip()
    if not niche:
        return RedirectResponse("/search?error=empty", status_code=303)

    limit = max(1, min(int(limit or 10), 100))
    allowed, note = quotas.clamp_request(db, user, limit)
    if allowed <= 0:
        return RedirectResponse("/billing?reason=quota", status_code=303)

    run = jobs.create_and_start(db, user, city, niche, allowed, bool(hot_only))
    suffix = f"?note={note}" if note else ""
    return RedirectResponse(f"/runs/{run.id}{suffix}", status_code=303)

@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(run_id: int, request: Request, note: str = "",
             db: Session = Depends(get_session)):
    user = auth.current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    run = db.get(Run, run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(404, "Сбор не найден")

    leads = db.scalars(select(Lead).where(Lead.run_id == run.id).order_by(
        desc(Lead.is_hot), desc(Lead.rating))).all()
    messages = {m.lead_id: m for m in db.scalars(
        select(Message).where(Message.run_id == run.id)).all()}
    return page(request, "run.html", user, db,
                run=run, leads=leads, messages=messages, angles=ANGLES, note=note)

@app.get("/api/runs/{run_id}/status")
def run_status(run_id: int, request: Request, db: Session = Depends(get_session)):
    user = auth.current_user(request, db)
    if not user:
        raise HTTPException(401)
    run = db.get(Run, run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(404)
    return {
        "status": run.status,
        "stage": run.stage,
        "collected": run.collected,
        "hot": run.hot_count,
        "total_in_city": run.total_in_city,
        "error": run.error,
    }

@app.post("/runs/{run_id}/delete")
def run_delete(run_id: int, request: Request, db: Session = Depends(get_session)):
    user = auth.current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    run = db.get(Run, run_id)
    if run and run.user_id == user.id:
        db.delete(run)
        db.commit()
    return RedirectResponse("/search", status_code=303)

@app.post("/runs/{run_id}/messages")
def make_messages(run_id: int, request: Request, angle: str = Form("auto"),
                  hot_only: str = Form(""), db: Session = Depends(get_session)):
    user = auth.current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    run = db.get(Run, run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(404)

    query = select(Lead).where(Lead.run_id == run.id)
    if hot_only:
        query = query.where(Lead.is_hot.is_(True))
    leads = db.scalars(query).all()
    if not leads:
        return RedirectResponse(f"/runs/{run_id}#messages", status_code=303)

    tpls = db.scalars(select(Template).where(Template.user_id == user.id)).all()
    payload = [_lead_dict(x, run) for x in leads]
    generated = {g["org_id"]: g for g in generate(payload, angle, user, tpls)}

    by_org = {x.org_id: x for x in leads}
    db.execute(delete(Message).where(Message.lead_id.in_([x.id for x in leads])))
    for org_id, item in generated.items():
        lead = by_org.get(org_id)
        if lead:
            db.add(Message(run_id=run.id, lead_id=lead.id, angle=angle,
                           text=item["text"], source=item["source"]))
    db.commit()
    return RedirectResponse(f"/runs/{run_id}#messages", status_code=303)

@app.get("/runs/{run_id}/csv")
def export_csv(run_id: int, request: Request, db: Session = Depends(get_session)):
    user = auth.current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    run = db.get(Run, run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(404)

    leads = db.scalars(select(Lead).where(Lead.run_id == run.id)).all()
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Название", "Уточнение", "Рубрика", "Адрес", "Рейтинг",
                     "Отзывов", "Телефоны", "Email", "Сайт", "Instagram",
                     "WhatsApp", "Telegram", "Без сайта", "Карточка 2ГИС",
                     "Широта", "Долгота"])
    for x in leads:
        writer.writerow([x.name, x.extension, x.rubric, x.address, x.rating or "",
                         x.reviews_count, ", ".join(x.phones), x.email, x.website,
                         x.instagram, x.whatsapp, x.telegram,
                         "да" if x.is_hot else "нет",
                         f"https://2gis.kz/{run.city_slug}/firm/{x.org_id}",
                         x.lat or "", x.lon or ""])
    buf.seek(0)
    fname = f"gisfind-{run.city_slug}-{run.id}.csv"
    return StreamingResponse(
        iter([b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )

@app.get("/api/runs/{run_id}/phones")
def export_phones(run_id: int, request: Request, db: Session = Depends(get_session)):
    user = auth.current_user(request, db)
    if not user:
        raise HTTPException(401)
    run = db.get(Run, run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(404)
    leads = db.scalars(select(Lead).where(Lead.run_id == run.id)).all()
    return JSONResponse({"phones": [p for x in leads for p in x.phones]})

@app.get("/contacts", response_class=HTMLResponse)
def contacts_page(request: Request, q: str = "", db: Session = Depends(get_session)):
    user = auth.current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    stmt = (select(Lead, Run).join(Run, Lead.run_id == Run.id)
            .where(Run.user_id == user.id).order_by(desc(Lead.id)).limit(500))
    rows = db.execute(stmt).all()
    if q:
        needle = q.lower()
        rows = [r for r in rows
                if needle in (r[0].name or "").lower()
                or needle in (r[0].rubric or "").lower()]
    return page(request, "contacts.html", user, db, rows=rows, q=q)

@app.get("/lists", response_class=HTMLResponse)
def lists_page(request: Request, db: Session = Depends(get_session)):
    user = auth.current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    saved = db.scalars(select(SavedList).where(SavedList.user_id == user.id)
                       .order_by(desc(SavedList.id))).all()
    runs = {r.id: r for r in db.scalars(select(Run).where(Run.user_id == user.id)).all()}
    return page(request, "lists.html", user, db, saved=saved, runs=runs)

@app.post("/lists")
def list_save(request: Request, run_id: int = Form(...), name: str = Form(...),
              db: Session = Depends(get_session)):
    user = auth.current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    run = db.get(Run, run_id)
    if run and run.user_id == user.id:
        db.add(SavedList(user_id=user.id, name=name.strip() or run.niche, run_id=run.id))
        db.commit()
    return RedirectResponse("/lists", status_code=303)

@app.get("/templates", response_class=HTMLResponse)
def templates_page(request: Request, db: Session = Depends(get_session)):
    user = auth.current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    items = db.scalars(select(Template).where(Template.user_id == user.id)
                       .order_by(desc(Template.id))).all()
    return page(request, "templates.html", user, db, items=items)

@app.post("/templates")
def template_add(request: Request, title: str = Form(...), url: str = Form(""),
                 note: str = Form(""), db: Session = Depends(get_session)):
    user = auth.current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    db.add(Template(user_id=user.id, title=title.strip(),
                    url=url.strip(), note=note.strip()))
    db.commit()
    return RedirectResponse("/templates", status_code=303)

@app.post("/templates/{tpl_id}/delete")
def template_delete(tpl_id: int, request: Request, db: Session = Depends(get_session)):
    user = auth.current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    tpl = db.get(Template, tpl_id)
    if tpl and tpl.user_id == user.id:
        db.delete(tpl)
        db.commit()
    return RedirectResponse("/templates", status_code=303)

@app.post("/profile")
def profile_save(request: Request, sender_name: str = Form(""),
                 sender_offer: str = Form(""), db: Session = Depends(get_session)):
    user = auth.current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    user.sender_name = sender_name.strip()[:120]
    user.sender_offer = sender_offer.strip()[:255]
    db.commit()
    return RedirectResponse("/templates", status_code=303)

@app.get("/guide", response_class=HTMLResponse)
def guide_page(request: Request, db: Session = Depends(get_session)):
    user = auth.current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    return page(request, "guide.html", user, db)

@app.get("/billing", response_class=HTMLResponse)
def billing_page(request: Request, reason: str = "",
                 db: Session = Depends(get_session)):
    user = auth.current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    return page(request, "billing.html", user, db, plans=PUBLIC_PLANS, reason=reason)

@app.post("/billing")
def billing_set(request: Request, plan: str = Form(...),
                db: Session = Depends(get_session)):
    user = auth.current_user(request, db)
    if not user:
        return RedirectResponse("/", status_code=303)
    if plan in PUBLIC_PLANS:
        user.plan = plan
        db.commit()
    return RedirectResponse("/billing?reason=changed", status_code=303)
