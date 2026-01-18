import os
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import Column, Integer, String, Text, create_engine, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# 1. DB 설정
SQLALCHEMY_DATABASE_URL = "sqlite:///./adhdiary.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. DB 모델 정의 (HTML 변수와 매칭되도록 설계)
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)

class BookRecord(Base):
    __tablename__ = "book_records"
    id = Column(Integer, primary_key=True); title = Column(String); date = Column(String); memo = Column(Text); owner_id = Column(Integer)

class DietRecord(Base):
    __tablename__ = "diet_records"
    id = Column(Integer, primary_key=True); weight = Column(String); meal = Column(String); memo = Column(Text); date = Column(String); owner_id = Column(Integer)

class DailyRecord(Base):
    __tablename__ = "daily_records"
    id = Column(Integer, primary_key=True); emoji = Column(String); memo = Column(Text); date = Column(String); owner_id = Column(Integer)

class FoodRecord(Base):
    __tablename__ = "food_records"
    id = Column(Integer, primary_key=True); place = Column(String); rating = Column(String); memo = Column(Text); date = Column(String); owner_id = Column(Integer)

Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# 3. 유저 인증 헬퍼
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def get_current_user(request: Request):
    uid = request.cookies.get("user_id")
    return int(uid) if uid else None

# 4. 로그인 / 회원가입 (알림 로직 포함)
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username, User.password == password).first()
    if user:
        res = RedirectResponse(url="/", status_code=303)
        res.set_cookie(key="user_id", value=str(user.id), httponly=True)
        return res
    return RedirectResponse(url="/login?error=invalid", status_code=303)

@app.post("/signup")
async def signup(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == username).first():
        return RedirectResponse(url="/signup?error=exists", status_code=303)
    db.add(User(username=username, password=password)); db.commit()
    return RedirectResponse(url="/login?error=registered", status_code=303)

# 5. [중요] 메인 페이지 (HTML 변수명 record.title, record.type 등 완벽 일치)
@app.get("/", response_class=HTMLResponse)
async def main_page(request: Request, db: Session = Depends(get_db), user_id=Depends(get_current_user)):
    if user_id is None: return RedirectResponse(url="/login")
    
    books = db.query(BookRecord).filter(BookRecord.owner_id == user_id).all()
    diets = db.query(DietRecord).filter(DietRecord.owner_id == user_id).all()
    dailies = db.query(DailyRecord).filter(DailyRecord.owner_id == user_id).all()
    foods = db.query(FoodRecord).filter(FoodRecord.owner_id == user_id).all()
    
    all_recs = []
    for r in books: all_recs.append({"id": r.id, "type": "book", "title": f"📖 {r.title}", "date": r.date})
    for r in diets: all_recs.append({"id": r.id, "type": "diet", "title": f"⚖️ {r.weight}kg 기록", "date": r.date})
    for r in dailies: all_recs.append({"id": r.id, "type": "daily", "title": f"{r.emoji} 일상 기록", "date": r.date})
    for r in foods: all_recs.append({"id": r.id, "type": "food", "title": f"🍴 {r.place}", "date": r.date})
    
    all_recs.sort(key=lambda x: x['date'] if x['date'] else "", reverse=True)
    return templates.TemplateResponse("index.html", {"request": request, "records": all_recs})

# 6. [중요] 모달 데이터를 위한 JSON API (HTML의 openModal 함수 대응)
@app.get("/{type}/{record_id}")
async def get_record_detail(type: str, record_id: int, db: Session = Depends(get_db), user_id=Depends(get_current_user)):
    models = {"book": BookRecord, "diet": DietRecord, "daily": DailyRecord, "food": FoodRecord}
    if type not in models: raise HTTPException(status_code=404)
    
    r = db.query(models[type]).filter(models[type].id == record_id, models[type].owner_id == user_id).first()
    if not r: raise HTTPException(status_code=404)
    
    # HTML 모달에서 기대하는 필드 구성
    title = ""
    if type == "book": title = f"📖 {r.title}"
    elif type == "diet": title = f"⚖️ {r.weight}kg 기록"
    elif type == "daily": title = f"{r.emoji} 일상"
    elif type == "food": title = f"🍴 {r.place}"
    
    memo = r.memo if r.memo else "메모가 없습니다."
    return JSONResponse({"title": title, "date": r.date, "memo": memo})

# 7. 카테고리별 저장/상세 페이지/삭제 (기존 로직 유지)
@app.post("/save_{type}")
async def save_any(type: str, request: Request, db: Session = Depends(get_db), uid=Depends(get_current_user)):
    form = await request.form()
    if type == "book": db.add(BookRecord(title=form.get("title"), date=form.get("date"), memo=form.get("memo"), owner_id=uid))
    elif type == "diet": db.add(DietRecord(weight=form.get("weight"), meal=form.get("meal"), memo=form.get("memo"), date=form.get("date"), owner_id=uid))
    elif type == "daily": db.add(DailyRecord(emoji=form.get("emoji"), memo=form.get("memo"), date=form.get("date"), owner_id=uid))
    elif type == "food": db.add(FoodRecord(place=form.get("place"), rating=form.get("rating"), memo=form.get("memo"), date=form.get("date"), owner_id=uid))
    db.commit()
    return RedirectResponse(f"/{type}", 303)

@app.post("/delete_{type}/{record_id}")
async def delete_rec(type: str, record_id: int, db: Session = Depends(get_db), uid=Depends(get_current_user)):
    models = {"book": BookRecord, "diet": DietRecord, "daily": DailyRecord, "food": FoodRecord}
    target = db.query(models[type]).filter(models[type].id == record_id, models[type].owner_id == uid).first()
    if target: db.delete(target); db.commit()
    return RedirectResponse("/", 303)

@app.get("/{category}", response_class=HTMLResponse)
async def cat_view(category: str, request: Request, db: Session = Depends(get_db), uid=Depends(get_current_user)):
    if category in ["favicon.ico", "static"]: return HTMLResponse("")
    if not uid: return RedirectResponse("/login")
    models = {"book": BookRecord, "diet": DietRecord, "daily": DailyRecord, "food": FoodRecord}
    if category in models:
        recs = db.query(models[category]).filter(models[category].owner_id == uid).order_by(desc(models[category].id)).all()
        return templates.TemplateResponse(f"{category}.html", {"request": request, "my_records": recs})
    return RedirectResponse("/")
