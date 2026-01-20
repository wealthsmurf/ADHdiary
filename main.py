import os
import uuid
from fastapi import FastAPI, Request, Form, Depends, HTTPException, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Column, Integer, String, Text, create_engine, desc, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# 1. 경로 설정 및 폴더 생성
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 2. DB 설정 (SQLite WAL 모드로 성능 최적화)
SQLALCHEMY_DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'adhdiary.db')}"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

with engine.connect() as connection:
    connection.execute(text("PRAGMA journal_mode=WAL;"))
    connection.execute(text("PRAGMA synchronous=NORMAL;"))

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- 3. 데이터 모델 정의 ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)

class BookRecord(Base):
    __tablename__ = "book_records"
    id = Column(Integer, primary_key=True); title = Column(String); date = Column(String); memo = Column(Text); image_url = Column(String); owner_id = Column(Integer)

class DietRecord(Base):
    __tablename__ = "diet_records"
    id = Column(Integer, primary_key=True); weight = Column(String); meal = Column(String); memo = Column(Text); date = Column(String); image_url = Column(String); owner_id = Column(Integer)

class DailyRecord(Base):
    __tablename__ = "daily_records"
    id = Column(Integer, primary_key=True); emoji = Column(String); memo = Column(Text); date = Column(String); image_url = Column(String); owner_id = Column(Integer)

class FoodRecord(Base):
    __tablename__ = "food_records"
    id = Column(Integer, primary_key=True); place = Column(String); rating = Column(String); memo = Column(Text); date = Column(String); image_url = Column(String); owner_id = Column(Integer)

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- 4. 유틸리티 함수 ---
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def get_current_user(request: Request):
    uid = request.cookies.get("user_id")
    return int(uid) if uid else None

async def save_file(file: UploadFile):
    if not file or not file.filename: return None
    try:
        await file.seek(0)
        contents = await file.read()
        if not contents: return None
        filename = f"{uuid.uuid4()}.jpg"
        path = os.path.join(UPLOAD_DIR, filename)
        with open(path, "wb") as f: f.write(contents)
        return f"/static/uploads/{filename}"
    except: return None
    finally: await file.close()

# --- 5. 라우팅 (회원가입/로그인/기록) ---

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, error: str = None):
    return templates.TemplateResponse("signup.html", {"request": request, "error": error})

@app.post("/signup")
async def signup(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == username).first():
        return RedirectResponse(url="/signup?error=exists", status_code=303)
    db.add(User(username=username, password=password))
    db.commit()
    return RedirectResponse(url="/login?error=registered", status_code=303)

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

@app.get("/logout")
async def logout():
    res = RedirectResponse(url="/login")
    res.delete_cookie("user_id")
    return res

@app.get("/", response_class=HTMLResponse)
async def main_page(request: Request, db: Session = Depends(get_db), user_id=Depends(get_current_user)):
    if user_id is None: return RedirectResponse(url="/login")
    
    # 각 카테고리 데이터 통합
    b = db.query(BookRecord).filter(BookRecord.owner_id == user_id).all()
    d = db.query(DietRecord).filter(DietRecord.owner_id == user_id).all()
    dy = db.query(DailyRecord).filter(DailyRecord.owner_id == user_id).all()
    f = db.query(FoodRecord).filter(FoodRecord.owner_id == user_id).all()
    
    recs = []
    for r in b: recs.append({"id": r.id, "type": "book", "title": f"📖 {r.title}", "date": r.date, "memo": r.memo, "img": r.image_url})
    for r in d: recs.append({"id": r.id, "type": "diet", "title": f"⚖️ {r.weight}kg", "date": r.date, "memo": r.meal, "img": r.image_url})
    for r in dy: recs.append({"id": r.id, "type": "daily", "title": f"{r.emoji} 일상", "date": r.date, "memo": r.memo, "img": r.image_url})
    for r in f: recs.append({"id": r.id, "type": "food", "title": f"🍴 {r.place}", "date": r.date, "memo": r.memo, "img": r.image_url})
    
    recs.sort(key=lambda x: x['date'] if x['date'] else "", reverse=True)
    return templates.TemplateResponse("index.html", {"request": request, "records": recs})

# --- 저장 API들 ---
@app.post("/save_book")
async def save_book(title:str=Form(...), date:str=Form(...), memo:str=Form(...), image:UploadFile=File(None), uid=Depends(get_current_user), db:Session=Depends(get_db)):
    if not uid: return RedirectResponse("/login", 303)
    img = await save_file(image)
    db.add(BookRecord(title=title, date=date, memo=memo, image_url=img, owner_id=uid)); db.commit()
    return RedirectResponse("/", 303)

@app.post("/save_diet")
async def save_diet(weight:str=Form(...), meal:str=Form(...), memo:str=Form(...), date:str=Form(...), image:UploadFile=File(None), uid=Depends(get_current_user), db:Session=Depends(get_db)):
    if not uid: return RedirectResponse("/login", 303)
    img = await save_file(image)
    db.add(DietRecord(weight=weight, meal=meal, memo=memo, date=date, image_url=img, owner_id=uid)); db.commit()
    return RedirectResponse("/", 303)

@app.post("/save_daily")
async def save_daily(emoji:str=Form(...), memo:str=Form(...), date:str=Form(...), image:UploadFile=File(None), uid=Depends(get_current_user), db:Session=Depends(get_db)):
    if not uid: return RedirectResponse("/login", 303)
    img = await save_file(image)
    db.add(DailyRecord(emoji=emoji, memo=memo, date=date, image_url=img, owner_id=uid)); db.commit()
    return RedirectResponse("/", 303)

@app.post("/save_food")
async def save_food(place:str=Form(...), rating:str=Form(...), memo:str=Form(...), date:str=Form(...), image:UploadFile=File(None), uid=Depends(get_current_user), db:Session=Depends(get_db)):
    if not uid: return RedirectResponse("/login", 303)
    img = await save_file(image)
    db.add(FoodRecord(place=place, rating=rating, memo=memo, date=date, image_url=img, owner_id=uid)); db.commit()
    return RedirectResponse("/", 303)

@app.post("/delete_{type}/{record_id}")
async def delete_rec(type: str, record_id: int, db: Session = Depends(get_db), uid=Depends(get_current_user)):
    models = {"book": BookRecord, "diet": DietRecord, "daily": DailyRecord, "food": FoodRecord}
    target = db.query(models[type]).filter(models[type].id == record_id, models[type].owner_id == uid).first()
    if target: db.delete(target); db.commit()
    return RedirectResponse("/", 303)
