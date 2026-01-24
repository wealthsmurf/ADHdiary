import os
import uuid
from fastapi import FastAPI, Request, Form, Depends, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Column, Integer, String, Text, create_engine, desc, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# 1. 경로 및 폴더 설정 (이미지 저장용)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 2. DB 설정 (절대 경로 및 WAL 모드 최적화)
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
    id = Column(Integer, primary_key=True, index=True); username = Column(String, unique=True, index=True); password = Column(String)

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

# --- 4. 유틸리티 ---
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

# --- 5. 가입/로그인 (1년 유지 필살기) ---
@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, error: str = None):
    return templates.TemplateResponse("signup.html", {"request": request, "error": error})

@app.post("/signup")
async def signup(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == username).first():
        return RedirectResponse(url="/signup?error=exists", status_code=303)
    db.add(User(username=username, password=password)); db.commit()
    return RedirectResponse(url="/login?error=registered", status_code=303)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username, User.password == password).first()
    if user:
        res = RedirectResponse(url="/", status_code=303)
        one_year = 31536000 # 365일 (초 단위)
        res.set_cookie(key="user_id", value=str(user.id), httponly=True, max_age=one_year, expires=one_year, samesite="lax")
        return res
    return RedirectResponse(url="/login?error=invalid", status_code=303)

@app.get("/logout")
async def logout():
    res = RedirectResponse(url="/login"); res.delete_cookie("user_id"); return res

# --- 6. 메인 및 카테고리별 뷰 ---
@app.get("/", response_class=HTMLResponse)
async def main_page(request: Request, db: Session = Depends(get_db), uid=Depends(get_current_user)):
    if uid is None: return RedirectResponse("/login")
    b = db.query(BookRecord).filter(BookRecord.owner_id == uid).all()
    d = db.query(DietRecord).filter(DietRecord.owner_id == uid).all()
    dy = db.query(DailyRecord).filter(DailyRecord.owner_id == uid).all()
    f = db.query(FoodRecord).filter(FoodRecord.owner_id == uid).all()
    recs = []
    for r in b: recs.append({"id": r.id, "type": "book", "title": f"📖 {r.title}", "date": r.date, "memo": r.memo})
    for r in d: recs.append({"id": r.id, "type": "diet", "title": f"⚖️ {r.weight}kg", "date": r.date, "memo": r.meal})
    for r in dy: recs.append({"id": r.id, "type": "daily", "title": f"{r.emoji} 일상", "date": r.date, "memo": r.memo})
    for r in f: recs.append({"id": r.id, "type": "food", "title": f"🍴 {r.place}", "date": r.date, "memo": r.memo})
    recs.sort(key=lambda x: x['date'] if x['date'] else "", reverse=True)
    return templates.TemplateResponse("index.html", {"request": request, "records": recs})

@app.get("/{category}", response_class=HTMLResponse)
async def category_view(category: str, request: Request, db: Session = Depends(get_db), uid=Depends(get_current_user)):
    if category in ["favicon.ico", "static"]: return HTMLResponse("")
    if not uid: return RedirectResponse("/login")
    models = {"book": BookRecord, "diet": DietRecord, "daily": DailyRecord, "food": FoodRecord}
    if category in models:
        my_records = db.query(models[category]).filter(models[category].owner_id == uid).order_by(desc(models[category].id)).all()
        return templates.TemplateResponse(f"{category}.html", {"request": request, "my_records": my_records})
    return RedirectResponse("/")

# --- 7. 저장 및 삭제 ---
@app.post("/save_book")
async def save_book(title:str=Form(...), date:str=Form(...), memo:str=Form(...), image:UploadFile=File(None), uid=Depends(get_current_user), db:Session=Depends(get_db)):
    img = await save_file(image); db.add(BookRecord(title=title, date=date, memo=memo, image_url=img, owner_id=uid)); db.commit(); return RedirectResponse("/book", 303)

@app.post("/save_diet")
async def save_diet(weight:str=Form(...), meal:str=Form(...), memo:str=Form(...), date:str=Form(...), image:UploadFile=File(None), uid=Depends(get_current_user), db:Session=Depends(get_db)):
    img = await save_file(image); db.add(DietRecord(weight=weight, meal=meal, memo=memo, date=date, image_url=img, owner_id=uid)); db.commit(); return RedirectResponse("/diet", 303)

@app.post("/save_daily")
async def save_daily(emoji:str=Form(...), memo:str=Form(...), date:str=Form(...), image:UploadFile=File(None), uid=Depends(get_current_user), db:Session=Depends(get_db)):
    img = await save_file(image); db.add(DailyRecord(emoji=emoji, memo=memo, date=date, image_url=img, owner_id=uid)); db.commit(); return RedirectResponse("/daily", 303)

@app.post("/save_food")
async def save_food(place:str=Form(...), rating:str=Form(...), memo:str=Form(...), date:str=Form(...), image:UploadFile=File(None), uid=Depends(get_current_user), db:Session=Depends(get_db)):
    img = await save_file(image); db.add(FoodRecord(place=place, rating=rating, memo=memo, date=date, image_url=img, owner_id=uid)); db.commit(); return RedirectResponse("/food", 303)

@app.post("/delete_{type}/{record_id}")
async def delete_rec(type: str, record_id: int, db: Session = Depends(get_db), uid=Depends(get_current_user)):
    models = {"book": BookRecord, "diet": DietRecord, "daily": DailyRecord, "food": FoodRecord}
    target = db.query(models[type]).filter(models[type].id == record_id, models[type].owner_id == uid).first()
    if target: db.delete(target); db.commit()
    return RedirectResponse(f"/{type}", 303)

@app.get("/privacy", response_class=HTMLResponse)
async def privacy_policy():
    return """
    <html>
        <head>
            <title>개인정보처리방침 - ADHDIARY</title>
            <style>
                body { font-family: sans-serif; line-height: 1.6; padding: 20px; color: #333; max-width: 800px; margin: 0 auto; }
                h1 { color: #4A90E2; }
                h2 { margin-top: 30px; border-bottom: 1px solid #eee; padding-bottom: 5px; }
            </style>
        </head>
        <body>
            <h1>개인정보처리방침</h1>
            <p><strong>ADHDIARY</strong>(이하 '앱')는 사용자의 개인정보를 중요시하며, 관련 법령을 준수합니다.</p>
            
            <h2>1. 수집하는 개인정보 항목</h2>
            <p>본 앱은 사용자가 직접 입력하는 다음 정보를 수집합니다.<br>
            - 기록 정보: 책 제목, 다이어트(몸무게, 식단), 일상 메모, 맛집 정보 등</p>
            
            <h2>2. 개인정보의 이용 목적</h2>
            <p>수집된 데이터는 오직 사용자의 원활한 일상 기록 관리 및 앱 내 기능 제공(기록 조회, 통계 등)을 위해서만 사용됩니다.</p>
            
            <h2>3. 개인정보의 보관 및 파기</h2>
            <p>사용자의 데이터는 앱을 삭제하거나 사용자가 직접 삭제를 요청할 때까지 보관됩니다. 삭제 요청 시 지체 없이 파기합니다.</p>
            
            <h2>4. 제3자 제공 및 위탁</h2>
            <p>본 앱은 원칙적으로 사용자의 정보를 외부에 제공하지 않습니다. 다만, 광고 수익화를 위해 카카오 애드핏(Adfit) 서비스를 이용하며, 이 과정에서 식별할 수 없는 기기 정보가 활용될 수 있습니다.</p>
            
            <h2>5. 문의처</h2>
            <p>개인정보 관련 문의사항은 개발자 메일로 연락 부탁드립니다.</p>
            <p>이메일: [wealthsmurf1@gmail.com]</p>
            <p>시행일자: 2026년 1월 23일</p>
        </body>
    </html>
    """


